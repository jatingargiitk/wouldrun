"""GitHub Actions filter-pattern matching and ordered ``!`` negation.

Implements the "Filter pattern cheat sheet" from
https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#filter-pattern-cheat-sheet

* ``*``   zero or more characters, not ``/``
* ``**``  zero or more of any character
* ``?``   zero or one of the preceding character
* ``+``   one or more of the preceding character
* ``[]``  one character from the listed characters / ranges (a-z, A-Z, 0-9)
* ``!``   at the start of a pattern negates earlier positive patterns
* ``\\x`` matches the literal character x

One deliberate reading of the docs: ``**/`` also matches "no directory", because
the documented examples say ``**/docs/**`` matches ``docs/hello.md`` and
``**/README.md`` matches ``README.md``.
"""

import re
from functools import lru_cache

_CLASS_OK = re.compile(r"^[A-Za-z0-9\-]+$")


@lru_cache(maxsize=2048)
def compile_glob(pattern):
    """Translate one GitHub filter pattern (without a leading ``!``) to a regex."""
    atoms = []  # each atom is a regex fragment so ?/+ can wrap the previous one
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "\\" and i + 1 < n:
            atoms.append(re.escape(pattern[i + 1]))
            i += 2
        elif c == "*":
            j = i
            while j < n and pattern[j] == "*":
                j += 1
            if j - i >= 2:
                if j < n and pattern[j] == "/":
                    atoms.append("(?:.*/)?")
                    j += 1
                else:
                    atoms.append(".*")
            else:
                atoms.append("[^/]*")
            i = j
        elif c in "?+" and atoms:
            atoms[-1] = "(?:%s)%s" % (atoms[-1], c)
            i += 1
        elif c == "[":
            end = pattern.find("]", i + 2)
            body = pattern[i + 1:end] if end != -1 else None
            if body and _CLASS_OK.match(body):
                atoms.append("[%s]" % body)
                i = end + 1
            else:
                atoms.append(re.escape(c))
                i += 1
        else:
            atoms.append(re.escape(c))
            i += 1
    return re.compile("".join(atoms), re.DOTALL)


def glob_match(pattern, name):
    """True if the whole of ``name`` matches ``pattern`` (no negation handling)."""
    return compile_glob(pattern).fullmatch(name) is not None


def is_negative(pattern):
    return pattern.startswith("!")


def only_negative(patterns):
    """True when a list has patterns but none without ``!`` (GitHub rejects this)."""
    return bool(patterns) and all(is_negative(p) for p in patterns)


def evaluate_patterns(patterns, name):
    """Evaluate an ordered include/exclude list against one name.

    Returns ``(included, deciding_pattern)``. Later patterns win: a matching
    ``!`` pattern after a positive match excludes, a matching positive pattern
    after a negative one includes again. ``deciding_pattern`` is the last
    pattern that changed the outcome, or ``None`` if nothing matched.
    """
    included = False
    decider = None
    for pat in patterns:
        if is_negative(pat):
            if included and glob_match(pat[1:], name):
                included = False
                decider = pat
        elif glob_match(pat, name):
            included = True
            decider = pat
    return included, decider


def first_match(patterns, name):
    """First plain pattern (no ``!``) matching ``name``, for ``-ignore`` lists."""
    for pat in patterns:
        if glob_match(pat, name):
            return pat
    return None
