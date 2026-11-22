"""Small git helpers: changed files and push commit counts."""

import subprocess


class GitError(Exception):
    pass


def _git(repo, *args):
    try:
        proc = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True)
    except FileNotFoundError:
        raise GitError("git is not installed or not on PATH")
    if proc.returncode != 0:
        cmd = [a for a in args if a not in ("-c", "core.quotepath=off") and not a.startswith("-")][0]
        err = proc.stderr.strip().splitlines()
        raise GitError("git %s failed: %s" % (cmd, err[0] if err else "exit %d" % proc.returncode))
    return proc.stdout


def changed_files(repo, base, head, three_dot):
    """``git diff --name-only BASE...HEAD`` (pull requests) or ``BASE..HEAD`` (pushes).

    -z keeps unusual file names intact. Renames are reported as delete + add,
    like the file list GitHub filters against.
    """
    rng = "%s%s%s" % (base, "..." if three_dot else "..", head)
    out = _git(repo, "-c", "core.quotepath=off", "diff", "--name-only", "--no-renames", "-z", rng, "--")
    return [f for f in out.split("\0") if f]


def commit_count(repo, base, head):
    return int(_git(repo, "rev-list", "--count", "%s..%s" % (base, head)).strip())


def current_branch(repo):
    try:
        name = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    except GitError:
        return None
    return None if name == "HEAD" else name
