import pytest

from wouldrun.globs import evaluate_patterns, first_match, glob_match, only_negative

# (pattern, name, expected) -- every row below comes from the examples in GitHub's
# "Filter pattern cheat sheet" tables (branches/tags and file paths) and the
# `on.push` / `paths` sections of the workflow syntax docs.
CHEAT_SHEET = [
    # branches and tags
    ("feature/*", "feature/my-branch", True),
    ("feature/*", "feature/your-branch", True),
    ("feature/*", "feature/beta-a/my-branch", False),
    ("feature/**", "feature/beta-a/my-branch", True),
    ("feature/**", "feature/your-branch", True),
    ("feature/**", "feature/mona/the/octocat", True),
    ("main", "main", True),
    ("main", "main2", False),
    ("releases/mona-the-octocat", "releases/mona-the-octocat", True),
    ("*", "main", True),
    ("*", "releases", True),
    ("*", "releases/10", False),
    ("**", "all/the/branches", True),
    ("**", "every/tag", True),
    ("*feature", "mona-feature", True),
    ("*feature", "feature", True),
    ("*feature", "ver-10-feature", True),
    ("v2*", "v2", True),
    ("v2*", "v2.0", True),
    ("v2*", "v2.9", True),
    ("v2*", "xv2", False),
    ("v[12].[0-9]+.[0-9]+", "v1.10.1", True),
    ("v[12].[0-9]+.[0-9]+", "v2.0.0", True),
    ("v[12].[0-9]+.[0-9]+", "v3.0.0", False),
    ("Octo*", "Octocat", True),
    ("releases/**-alpha", "releases/beta/3-alpha", True),
    ("releases/**-alpha", "releases/10-alpha", True),
    ("releases/**-alpha", "releases/10", False),
    ("v1.*", "v1.9.1", True),
    ("v1.*", "v1.9", True),
    ("v1.*", "v10", False),
    # file paths
    ("*", "README.md", True),
    ("*", "server.rb", True),
    ("*", "docs/a.md", False),
    ("*.jsx?", "page.js", True),
    ("*.jsx?", "page.jsx", True),
    ("*.jsx?", "page.jsxx", False),
    ("**", "all/the/files.md", True),
    ("*.js", "app.js", True),
    ("*.js", "index.js", True),
    ("*.js", "js/index.js", False),
    ("**.js", "index.js", True),
    ("**.js", "js/index.js", True),
    ("**.js", "src/js/app.js", True),
    ("docs/*", "docs/README.md", True),
    ("docs/*", "docs/file.txt", True),
    ("docs/*", "docs/mona/octocat.txt", False),
    ("docs/**", "docs/README.md", True),
    ("docs/**", "docs/mona/octocat.txt", True),
    ("docs/**", "other/docs/x", False),
    ("docs/**/*.md", "docs/README.md", True),
    ("docs/**/*.md", "docs/mona/hello-world.md", True),
    ("docs/**/*.md", "docs/a/markdown/file.md", True),
    ("docs/**/*.md", "docs/a.txt", False),
    ("**/docs/**", "docs/hello.md", True),
    ("**/docs/**", "dir/docs/my-file.txt", True),
    ("**/docs/**", "space/docs/plan/space.doc", True),
    ("**/docs/**", "mydocs/x", False),
    ("**/README.md", "README.md", True),
    ("**/README.md", "js/README.md", True),
    ("**/README.md", "js/README.mdx", False),
    ("**/*src/**", "a/src/app.js", True),
    ("**/*src/**", "my-src/code/js/app.js", True),
    ("**/*-post.md", "my-post.md", True),
    ("**/*-post.md", "path/their-post.md", True),
    ("**/migrate-*.sql", "migrate-10909.sql", True),
    ("**/migrate-*.sql", "db/migrate-v1.0.sql", True),
    ("**/migrate-*.sql", "db/sept/migrate-v1.sql", True),
    ("sub-project/**", "sub-project/index.js", True),
    ("sub-project/**", "sub-project/src/index.js", True),
    # classes, escapes, '+'
    ("[CB]at", "Cat", True),
    ("[CB]at", "Bat", True),
    ("[CB]at", "Rat", False),
    ("[1-2]00", "100", True),
    ("[1-2]00", "200", True),
    ("[1-2]00", "300", False),
    ("[0-9a-z]x", "qx", True),
    ("C\\+\\+", "C++", True),
    ("C\\+\\+", "CC", False),
    ("ab+c", "abbbc", True),
    ("ab+c", "ac", False),
    ("colou?r", "color", True),
    ("colou?r", "colour", True),
    ("colou?r", "colouur", False),
    ("a.b", "axb", False),
    ("a!b", "a!b", True),
]


@pytest.mark.parametrize("pattern,name,expected", CHEAT_SHEET)
def test_cheat_sheet(pattern, name, expected):
    assert glob_match(pattern, name) is expected


# Ordered negation, from the docs' "including and excluding" examples.
@pytest.mark.parametrize(
    "patterns,name,included,decider",
    [
        (["releases/**", "!releases/**-alpha"], "releases/10", True, "releases/**"),
        (["releases/**", "!releases/**-alpha"], "releases/beta/mona", True, "releases/**"),
        (["releases/**", "!releases/**-alpha"], "releases/10-alpha", False, "!releases/**-alpha"),
        (["releases/**", "!releases/**-alpha"], "releases/beta/3-alpha", False, "!releases/**-alpha"),
        (["releases/**", "!releases/**-alpha"], "main", False, None),
        (["sub-project/**", "!sub-project/docs/**"], "sub-project/index.js", True, "sub-project/**"),
        (["sub-project/**", "!sub-project/docs/**"], "sub-project/docs/readme.md", False, "!sub-project/docs/**"),
        (["*.md", "!README.md"], "hello.md", True, "*.md"),
        (["*.md", "!README.md"], "README.md", False, "!README.md"),
        (["*.md", "!README.md"], "docs/hello.md", False, None),
        # a later positive pattern re-includes
        (["*.md", "!README.md", "README*"], "hello.md", True, "*.md"),
        (["*.md", "!README.md", "README*"], "README.md", True, "README*"),
        (["*.md", "!README.md", "README*"], "README.doc", True, "README*"),
        # a negative pattern before any positive match does nothing
        (["!README.md", "*.md"], "README.md", True, "*.md"),
    ],
)
def test_ordered_negation(patterns, name, included, decider):
    assert evaluate_patterns(patterns, name) == (included, decider)


def test_only_negative():
    assert only_negative(["!a", "!b"])
    assert not only_negative(["a", "!b"])
    assert not only_negative([])


def test_first_match():
    assert first_match(["a/**", "b/**"], "b/x") == "b/**"
    assert first_match(["a/**"], "c") is None
