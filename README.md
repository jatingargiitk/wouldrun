# wouldrun

Will this push or pull request trigger my GitHub Actions workflows? And if a workflow
does not run, which filter stopped it?

`wouldrun` reads `.github/workflows/*.yml`, takes an event, a ref and the changed files,
and prints one verdict per workflow with the filter that decided it:

* `RUNS`
* `SKIPPED`: a `branches` / `tags` / `paths` filter excluded it
* `NOT-TRIGGERED-BY-EVENT`: the event isn't in `on:`, or the activity `types` don't match
* `INCONCLUSIVE`: it needs input you did not give (changed files, ref, activity type), or the diff is too large to be sure
* `INVALID`: the workflow breaks a documented rule (for example `branches` together with `branches-ignore`) or doesn't parse

It can also flag the classic trap where a **required status check comes from a workflow that
path filters skip**, so the PR waits forever on "Expected — Waiting for status to be reported".

## Install

Python 3.9+ and one dependency, [PyYAML](https://pypi.org/project/PyYAML/). Not on PyPI; install from GitHub:

```sh
pip install git+https://github.com/jatingargiitk/wouldrun
# or
pipx install git+https://github.com/jatingargiitk/wouldrun
```

`git` must be on `PATH` only if you use `--base/--head`.

## Usage

The examples below use the sample workflows in [`examples/repo`](examples/repo/.github/workflows).
Every output block is produced by running the command shown; CI re-runs them and fails if the README drifts
(`python scripts/check_readme.py`). Text output folds workflows that don't mention the event into one line; use `-v` to list them.

### A docs-only pull request

```console
$ wouldrun --repo examples/repo -e pull_request -r main --files docs/guide.md README.md --required test --required build-docs
wouldrun: pull_request (synchronize), base branch main, 2 changed files

SKIPPED  .github/workflows/ci.yml  "CI"
         paths: no changed file matched ['src/**', '!src/docs/**']
           docs/guide.md: no pattern includes it
           README.md: no pattern includes it
SKIPPED  .github/workflows/docs.yml  "Docs"
         paths-ignore: every changed file matched ['docs/**', '**.md']
           docs/guide.md matched 'docs/**'
           README.md matched '**.md'
NOT-TRIGGERED-BY-EVENT  4 workflows do not list 'pull_request' in `on:` (--verbose lists them): broken.yml, labeler.yml, nightly.yml, release.yml

required checks:
  STRANDED   test (.github/workflows/ci.yml)
             SKIPPED: paths: no changed file matched ['src/**', '!src/docs/**']
             the PR would sit at "Expected — Waiting for status to be reported" and could not merge
  STRANDED   build-docs (.github/workflows/docs.yml)
             SKIPPED: paths-ignore: every changed file matched ['docs/**', '**.md']
             the PR would sit at "Expected — Waiting for status to be reported" and could not merge
```

For a pull request, `--ref` is the **base** branch (that is what `branches` matches against).
`test` and `build-docs` are job names, which is what a branch protection rule stores as the required check.
Both workflows are skipped here, so wouldrun exits with status 1.

### A push to a release branch

```console
$ wouldrun --repo examples/repo -e push -r release/1.2 --files src/app.py src/docs/x.md
wouldrun: push, branch release/1.2, 2 changed files

INVALID  .github/workflows/broken.yml  "Broken"
         on.push: cannot use both `branches` and `branches-ignore` for `push`
RUNS     .github/workflows/ci.yml  "CI"
         branches: 'release/**' matched branch 'release/1.2'
           paths: src/app.py matched 'src/**'
SKIPPED  .github/workflows/release.yml  "Release"
         only tags/tags-ignore is defined, so branch pushes do not run it (branch 'release/1.2')
NOT-TRIGGERED-BY-EVENT  3 workflows do not list 'push' in `on:` (--verbose lists them): docs.yml, labeler.yml, nightly.yml
```

### A tag push

```console
$ wouldrun --repo examples/repo -e push --tag -r v1.2.3
wouldrun: push, tag v1.2.3

INVALID  .github/workflows/broken.yml  "Broken"
         on.push: cannot use both `branches` and `branches-ignore` for `push`
SKIPPED  .github/workflows/ci.yml  "CI"
         only branches/branches-ignore is defined, so tag pushes do not run it (tag 'v1.2.3')
RUNS     .github/workflows/release.yml  "Release"
         tags: 'v[0-9]+.[0-9]+.[0-9]+' matched tag 'v1.2.3'
NOT-TRIGGERED-BY-EVENT  3 workflows do not list 'push' in `on:` (--verbose lists them): docs.yml, labeler.yml, nightly.yml
```

Branch filters never run for tags and tag filters never run for branches, so `ci.yml` says why it stays quiet.

### Activity types

```console
$ wouldrun --repo examples/repo -e pull_request -r main -t closed --files src/a.py
wouldrun: pull_request (closed), base branch main, 1 changed file

NOT-TRIGGERED-BY-EVENT  .github/workflows/ci.yml  "CI"
                        types (default): closed not in ['opened', 'synchronize', 'reopened']
NOT-TRIGGERED-BY-EVENT  .github/workflows/docs.yml  "Docs"
                        types (default): closed not in ['opened', 'synchronize', 'reopened']
NOT-TRIGGERED-BY-EVENT  4 workflows do not list 'pull_request' in `on:` (--verbose lists them): broken.yml, labeler.yml, nightly.yml, release.yml
```

Without `-t`, a pull request is evaluated as `synchronize` (a push to the PR branch). The defaults for
`pull_request` / `pull_request_target` are `opened`, `synchronize`, `reopened`.

### A real git diff

Instead of `--files`, give `--base` and `--head` and wouldrun runs `git diff --name-only` itself:
three dots (`BASE...HEAD`) for pull requests and two dots (`BASE..HEAD`) for pushes, which are the comparisons
GitHub documents for path filters. [`examples/git-demo.sh`](examples/git-demo.sh) builds a throwaway repository
with a docs-only branch and runs this:

```console
$ bash examples/git-demo.sh
wouldrun: pull_request (synchronize), base branch main, 2 changed files

SKIPPED  .github/workflows/ci.yml  "CI"
         paths: no changed file matched ['src/**', '!src/docs/**']
           README.md: no pattern includes it
           docs/guide.md: no pattern includes it
SKIPPED  .github/workflows/docs.yml  "Docs"
         paths-ignore: every changed file matched ['docs/**', '**.md']
           README.md matched '**.md'
           docs/guide.md matched 'docs/**'
NOT-TRIGGERED-BY-EVENT  4 workflows do not list 'pull_request' in `on:` (--verbose lists them): broken.yml, labeler.yml, nightly.yml, release.yml

required checks:
  STRANDED   test (.github/workflows/ci.yml)
             SKIPPED: paths: no changed file matched ['src/**', '!src/docs/**']
             the PR would sit at "Expected — Waiting for status to be reported" and could not merge
```

You can also pipe a list: `git diff --name-only origin/main...HEAD | wouldrun -e pull_request -r main --files -`.

### JSON

```console
$ wouldrun --repo examples/solo -e pull_request -r main --files README.md --format json
{
  "event": "pull_request",
  "activity": "synchronize",
  "ref": {
    "kind": "branch",
    "name": "main"
  },
  "changed_files": [
    "README.md"
  ],
  "workflows": [
    {
      "file": ".github/workflows/lint.yml",
      "name": "Lint",
      "status": "SKIPPED",
      "reason": "paths: no changed file matched ['**.py']",
      "details": [
        "README.md: no pattern includes it"
      ]
    }
  ],
  "required_checks": [],
  "expected": []
}
```

### Options

| Option | Meaning |
| --- | --- |
| `-e, --event` | `push` (default), `pull_request`, `pull_request_target`, `workflow_dispatch`, `schedule`, or any other event name |
| `-r, --ref` | Branch (for PRs: the base branch) or a full `refs/heads/…` / `refs/tags/…`. Defaults to the current branch for `push`; for PRs, to `--base` without an `origin/` prefix |
| `--tag` | Treat a short `--ref` as a tag (push only) |
| `-t, --type` | Activity type, e.g. `opened`, `closed`, `labeled` |
| `--base`, `--head` | Compute changed files with `git diff --name-only` (`--head` defaults to `HEAD`) |
| `--files PATH…` | Changed files given directly; `-` reads one path per line from stdin |
| `--required CHECK` | A required status check name; repeatable. Exit 1 if its workflow would not run |
| `--expect-run NAME` | A workflow file name or `name:` that must `RUN`; repeatable. Exit 1 otherwise |
| `-v, --verbose` | Text output folds workflows that don't mention the event into one line; this lists each one |
| `--format text\|json` | Output format |
| `--color auto\|always\|never` | Colour is on only for a terminal (and off if `NO_COLOR` is set) under `auto` |
| `--repo DIR` | Repository root (default `.`) |

Exit status: `0` normally, `1` if a `--required` check would be stranded or an `--expect-run` workflow would not run,
`2` for a usage or git error.

## What it implements

From GitHub's documentation:

* [`on.<push|pull_request|pull_request_target>.<branches|tags|branches-ignore|tags-ignore>`](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushbranchestagsbranches-ignoretags-ignore)
  and [`…<paths|paths-ignore>`](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
* the [filter pattern cheat sheet](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#filter-pattern-cheat-sheet):
  `*`, `**`, `?`, `+`, `[]`, `\` escapes, and `!` negation where **the order matters** (a later match wins).
  [`tests/test_globs.py`](tests/test_globs.py) is a table built from the examples in those docs.
* `branches` and `branches-ignore` (and `tags` / `tags-ignore`) cannot be combined, and a list with only `!` patterns is
  not allowed: reported as `INVALID`.
* Defining only `tags`/`tags-ignore` means branch pushes don't run the workflow, and the reverse. Path filters are not evaluated for tag pushes.
* `branches` and `paths` must both pass. `paths` uses every changed file with ordered negation; `paths-ignore` runs if any file is not ignored.
  No changed files means no run.
* Pull request filters match the base branch; activity `types` default to `opened`, `synchronize`, `reopened`.
* `on:` as a string, a list, or a map. PyYAML implements YAML 1.1, where a bare `on` key becomes the boolean `True`;
  wouldrun uses a loader that only treats `true`/`false` as booleans, so `on` stays a key.
* Diff limits from the docs: a push of more than 1,000 commits always runs; if a diff has more than 3,000 files and the filter matches none of the first 3,000,
  the result is `INCONCLUSIVE` (GitHub would not run it, but wouldrun can't know the order GitHub returns files in).
* Required checks: a workflow skipped by [branch, path or commit-message filtering](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
  leaves its checks "Pending", and a pull request that requires them is blocked. The same is documented under "Handling skipped but required checks" in
  [troubleshooting required status checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks).
  Check names are matched against job `name:` (or the job id), including `name (matrix, values)` and `${{ … }}` placeholders and `caller / job` for reusable workflows.

One interpretation to be aware of: the docs list `**/docs/**` as matching `docs/hello.md` and `**/README.md` as matching `README.md`, so wouldrun lets a `**/` prefix match zero directories.

## What it can't see

* **Job-level `if:` expressions are not evaluated.** A workflow reported as `RUNS` can still have jobs that are skipped by `if:`.
* Commit-message skip markers (`[skip ci]` and friends) and repository / organisation settings (disabled workflows, Actions permissions, approval for first-time contributors).
* Whether a PR from a fork gets secrets or a read-only token; `pull_request_target` runs the workflow from the base branch, which wouldrun does not model (it evaluates the workflow files you point it at).
* For events other than `push`, `pull_request` and `pull_request_target`, only `types` is checked; `workflow_dispatch` and `schedule` are reported as `RUNS` without looking at inputs or whether a cron time has arrived. `workflow_run`, `merge_group`, `release` and other filters are not evaluated.
* Required checks are found by name inside your workflow files. Checks from other apps, or names built from expressions wouldrun can't resolve, show up as `NOT FOUND`.
* The exact set of files GitHub computes for a push (force pushes, new branches, the 1,000-commit and timeout cases). You give it a file list; it does not guess one.
* Reusable workflows (`workflow_call`) and composite actions are not followed.

## Development

```sh
pip install -e '.[test]'
pytest
python scripts/check_readme.py
```

MIT licensed, see [LICENSE](LICENSE).
