import argparse
import os
import sys

from . import __version__
from . import evaluate as ev
from . import gitutil, report
from .workflow import load_workflows

EVENT_HELP = "push, pull_request, pull_request_target, workflow_dispatch, schedule (or any other event name)"


def build_parser():
    p = argparse.ArgumentParser(
        prog="wouldrun",
        description="Will this push/PR trigger my GitHub Actions workflows? "
                    "Prints RUNS / SKIPPED / NOT-TRIGGERED-BY-EVENT / INCONCLUSIVE / INVALID "
                    "for every workflow with the filter that decided it. Job-level `if:` is not evaluated.",
    )
    p.add_argument("--version", action="version", version="wouldrun " + __version__)
    p.add_argument("--repo", default=".", help="repository root (default: current directory)")
    p.add_argument("-e", "--event", default="push", help="event to simulate: " + EVENT_HELP + " [push]")
    p.add_argument("-r", "--ref", help="branch name (for pull_request: the BASE branch), or a full "
                   "refs/heads/... / refs/tags/... ref. Default: the current branch for push; for "
                   "pull_request, --base without an 'origin/' prefix")
    p.add_argument("--tag", action="store_true", help="treat a short --ref as a tag (push only)")
    p.add_argument("-t", "--type", dest="activity",
                   help="activity type, e.g. opened, synchronize, closed, labeled "
                        "[synchronize for pull_request / pull_request_target]")
    p.add_argument("--base", help="base commit/branch for `git diff --name-only`")
    p.add_argument("--head", default="HEAD", help="head commit for the diff [HEAD]")
    p.add_argument("--files", nargs="+", metavar="PATH",
                   help="changed files, instead of a git diff; '-' reads one path per line from stdin")
    p.add_argument("--required", action="append", default=[], metavar="CHECK",
                   help="a required status check name (a job name); repeatable. Exit 1 if its workflow "
                        "would not run, which strands the PR")
    p.add_argument("--expect-run", action="append", default=[], metavar="WORKFLOW",
                   help="workflow file name or `name:` that must RUN; repeatable. Exit 1 otherwise")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="list workflows that don't mention the event one by one (text output; "
                        "JSON always lists every workflow)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    return p


def _split_ref(ref, force_tag):
    if ref.startswith("refs/heads/"):
        return "branch", ref[len("refs/heads/"):]
    if ref.startswith("refs/tags/"):
        return "tag", ref[len("refs/tags/"):]
    return ("tag" if force_tag else "branch"), ref


def main(argv=None):
    args = build_parser().parse_args(argv)
    repo = args.repo
    if not os.path.isdir(repo):
        print("wouldrun: not a directory: %s" % repo, file=sys.stderr)
        return 2
    event = args.event
    is_pr = event in ev.PR_EVENTS

    activity = args.activity
    if activity is None and is_pr:
        activity = "synchronize"

    ref = args.ref
    if ref is None:
        if is_pr and args.base:
            ref = args.base[len("origin/"):] if args.base.startswith("origin/") else args.base
        elif event == "push":
            ref = gitutil.current_branch(repo)
    if is_pr and ref is None:
        print("wouldrun: pull_request needs the base branch: pass --ref BRANCH", file=sys.stderr)
        return 2
    kind, name = ("branch", None) if ref is None else _split_ref(ref, args.tag and event == "push")
    if is_pr and kind == "tag":
        print("wouldrun: pull request filters match a base branch, not a tag", file=sys.stderr)
        return 2

    files, commits = None, None
    try:
        if args.files:
            if args.files == ["-"]:
                files = [l.rstrip("\n") for l in sys.stdin if l.strip()]
            else:
                files = list(args.files)
        elif args.base:
            files = gitutil.changed_files(repo, args.base, args.head, three_dot=is_pr)
            if event == "push":
                commits = gitutil.commit_count(repo, args.base, args.head)
    except gitutil.GitError as exc:
        print("wouldrun: %s" % exc, file=sys.stderr)
        return 2

    ctx = ev.Context(event, kind, name, activity, files, commits)
    results = ev.evaluate_all(load_workflows(repo), ctx)
    required = ev.check_required(results, args.required) if args.required else []

    expect = []
    for want in args.expect_run:
        hits = [(wf, d) for wf, d in results
                if want in (wf.file, os.path.basename(wf.file), wf.name)]
        if not hits:
            expect.append({"name": want, "ok": False, "note": "no such workflow"})
        else:
            expect.append({"name": want, "ok": all(d.status == ev.RUNS for _, d in hits)})

    if args.format == "json":
        print(report.render_json(ctx, results, required, expect))
    else:
        color = args.color == "always" or (
            args.color == "auto" and sys.stdout.isatty() and "NO_COLOR" not in os.environ)
        print(report.render_text(ctx, results, required, color, expect, args.verbose))

    failed = any(r["state"] == "stranded" for r in required) or any(not e["ok"] for e in expect)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
