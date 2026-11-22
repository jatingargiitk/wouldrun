"""Decide, per workflow, whether an event would trigger it and which filter decided."""

import re

from .globs import evaluate_patterns, first_match, only_negative

RUNS = "RUNS"
SKIPPED = "SKIPPED"
NOT_TRIGGERED = "NOT-TRIGGERED-BY-EVENT"
INCONCLUSIVE = "INCONCLUSIVE"
INVALID = "INVALID"

PR_EVENTS = ("pull_request", "pull_request_target")
PR_DEFAULT_TYPES = ["opened", "synchronize", "reopened"]

# https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
# "If the generated diff contains more than 3,000 files and the files the workflow
# filter matches are not in the first 3,000 returned by the filter, the workflow will
# not run." / "If a push contains more than 1,000 commits, the workflow will always run."
MAX_DIFF_FILES = 3000
MAX_PUSH_COMMITS = 1000


class Context:
    """One concrete event to evaluate workflows against."""

    def __init__(self, event, ref_kind="branch", ref_name=None, activity=None,
                 files=None, commits=None):
        self.event = event
        self.ref_kind = ref_kind      # "branch" or "tag" (pull_request: always the base branch)
        self.ref_name = ref_name
        self.activity = activity
        self.files = files            # list of changed paths, or None if unknown
        self.commits = commits        # number of commits in a push, or None


class Decision:
    def __init__(self, status, reason, details=None):
        self.status = status
        self.reason = reason          # the deciding filter / explanation, one line
        self.details = details or []  # extra lines: what matched what

    def as_dict(self):
        return {"status": self.status, "reason": self.reason, "details": self.details}


def _as_list(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return [str(value)]
    if isinstance(value, list):
        return [str(v) for v in value]
    return None


def _quote(patterns):
    return "[" + ", ".join("'%s'" % p for p in patterns) + "]"


def _conflicts(cfg, event):
    """Return an INVALID reason if the event config breaks a documented rule."""
    pairs = [("branches", "branches-ignore"), ("paths", "paths-ignore")]
    if event == "push":
        pairs.append(("tags", "tags-ignore"))
    for a, b in pairs:
        if a in cfg and b in cfg:
            return "cannot use both `%s` and `%s` for `%s`" % (a, b, event)
    for key in ("branches", "tags", "paths"):
        if key in cfg and (event == "push" or key != "tags"):
            pats = _as_list(cfg[key])
            if pats is None:
                return "`%s` must be a list of patterns" % key
            if only_negative(pats):
                return ("`%s` only has `!` patterns; add at least one pattern without `!` "
                        "or use `%s-ignore`" % (key, key))
    return None


def _ref_filter(cfg, ctx, key, name):
    """Apply branches/branches-ignore (key='branches') or tags/tags-ignore.

    Returns (None, detail) when the ref passes, or (reason, None) when it does not.
    """
    if key in cfg:
        pats = _as_list(cfg[key])
        ok, decider = evaluate_patterns(pats, name)
        if ok:
            return None, "%s: '%s' matched %s '%s'" % (key, decider, ctx_kind(key), name)
        if decider:
            return ("%s: %s excluded %s '%s'" % (key, "'%s'" % decider, ctx_kind(key), name)), None
        return ("%s: no pattern in %s matched %s '%s'" % (key, _quote(pats), ctx_kind(key), name)), None
    ign = key + "-ignore"
    if ign in cfg:
        pats = _as_list(cfg[ign])
        hit = first_match(pats, name)
        if hit is not None:
            return ("%s: '%s' matched %s '%s'" % (ign, hit, ctx_kind(key), name)), None
        return None, "%s: no pattern in %s matched '%s'" % (ign, _quote(pats), name)
    return None, None


def ctx_kind(key):
    return "branch" if key == "branches" else "tag"


def _path_filter(cfg, files, truncated):
    """Return (Decision-ish tuple). Result: ('pass'|'fail'|'unknown', reason, details)."""
    if "paths" in cfg:
        pats = _as_list(cfg["paths"])
        key = "paths"
    else:
        pats = _as_list(cfg["paths-ignore"])
        key = "paths-ignore"
    if files is None:
        return "unknown", "%s filter %s needs the changed files (use --base/--head or --files)" % (
            key, _quote(pats)), []
    if not files:
        return "fail", "%s: no files changed, so the workflow does not run" % key, []
    hits = []
    for f in files:
        if key == "paths":
            ok, decider = evaluate_patterns(pats, f)
            if ok:
                hits.append("%s matched '%s'" % (f, decider))
        else:
            if first_match(pats, f) is None:
                hits.append("%s is not ignored (no pattern in %s matched)" % (f, _quote(pats)))
    if hits:
        extra = hits[1:3]
        if len(hits) > 3:
            extra.append("(+%d more files)" % (len(hits) - 3))
        return "pass", "%s: %s" % (key, hits[0]), extra
    if truncated:
        return "unknown", ("%s: no match in the first %d changed files; GitHub only looks at the "
                           "first %d files of a larger diff" % (key, MAX_DIFF_FILES, MAX_DIFF_FILES)), []
    if key == "paths":
        return "fail", "paths: no changed file matched %s" % _quote(pats), [
            "%s: no pattern includes it" % f if not evaluate_patterns(pats, f)[1]
            else "%s: excluded by '%s'" % (f, evaluate_patterns(pats, f)[1])
            for f in files[:5]]
    return "fail", "paths-ignore: every changed file matched %s" % _quote(pats), [
        "%s matched '%s'" % (f, first_match(pats, f)) for f in files[:5]]


def evaluate(wf, ctx):
    if wf.error:
        return Decision(INVALID, wf.error)
    event = ctx.event
    if event not in wf.events:
        listed = ", ".join(sorted(wf.events)) or "nothing"
        return Decision(NOT_TRIGGERED, "`on:` does not list '%s' (it lists: %s)" % (event, listed))
    cfg = wf.events[event]
    cfg = cfg if isinstance(cfg, dict) else {}

    if event == "workflow_dispatch":
        return Decision(RUNS, "workflow_dispatch: started manually; no branch/path filters apply")
    if event == "schedule":
        return Decision(RUNS, "schedule: runs at its cron times on the default branch; "
                              "no branch/path filters apply")

    # activity types
    if "types" in cfg or event in PR_EVENTS:
        types = _as_list(cfg.get("types")) if "types" in cfg else None
        if types is None and "types" in cfg:
            return Decision(INVALID, "`types` for `%s` must be a list" % event)
        allowed = types if types is not None else PR_DEFAULT_TYPES
        label = "types" if types is not None else "types (default)"
        if ctx.activity is None and types is not None:
            return Decision(INCONCLUSIVE, "%s: %s needs an activity type (use --type)" % (
                label, _quote(allowed)))
        if ctx.activity is not None and ctx.activity not in allowed:
            return Decision(NOT_TRIGGERED, "%s: %s not in %s" % (label, ctx.activity, _quote(allowed)))

    if event not in ("push",) + PR_EVENTS:
        return Decision(RUNS, "%s: only `types` is checked for this event; other filters are not "
                              "evaluated by wouldrun" % event)

    bad = _conflicts(cfg, event)
    if bad:
        return Decision(INVALID, "on.%s: %s" % (event, bad))

    notes = []
    kind, name = ctx.ref_kind, ctx.ref_name
    if event in PR_EVENTS:
        kind = "branch"  # filters match the base branch
    if event == "push":
        has_b = "branches" in cfg or "branches-ignore" in cfg
        has_t = "tags" in cfg or "tags-ignore" in cfg
        if kind == "tag" and has_b and not has_t:
            return Decision(SKIPPED, "only branches/branches-ignore is defined, so tag pushes do not "
                                     "run it (tag '%s')" % name)
        if kind == "branch" and has_t and not has_b:
            return Decision(SKIPPED, "only tags/tags-ignore is defined, so branch pushes do not run "
                                     "it (branch '%s')" % name)

    if name is None:
        if "branches" in cfg or "branches-ignore" in cfg or "tags" in cfg or "tags-ignore" in cfg:
            return Decision(INCONCLUSIVE, "a ref filter is defined but no ref was given (use --ref)")
    else:
        key = "branches" if kind == "branch" else "tags"
        reason, detail = _ref_filter(cfg, ctx, key, name)
        if reason:
            return Decision(SKIPPED, reason)
        if detail:
            notes.append(detail)

    has_paths = "paths" in cfg or "paths-ignore" in cfg
    if has_paths and kind == "tag":
        notes.append("paths: not evaluated for tag pushes")
    elif has_paths:
        if event == "push" and ctx.commits is not None and ctx.commits > MAX_PUSH_COMMITS:
            return Decision(RUNS, "push has %d commits (>%d): GitHub always runs the workflow, "
                                  "path filters are skipped" % (ctx.commits, MAX_PUSH_COMMITS), notes)
        files = ctx.files
        truncated = files is not None and len(files) > MAX_DIFF_FILES
        if truncated:
            files = files[:MAX_DIFF_FILES]
        res, reason, details = _path_filter(cfg, files, truncated)
        if res == "fail":
            return Decision(SKIPPED, reason, details)
        if res == "unknown":
            return Decision(INCONCLUSIVE, reason)
        notes = [reason] + details if not notes else notes + [reason] + details
        return Decision(RUNS, notes[0], notes[1:])

    if notes:
        return Decision(RUNS, notes[0], notes[1:])
    return Decision(RUNS, "no branch/tag/path filter excludes this event")


def evaluate_all(workflows, ctx):
    return [(wf, evaluate(wf, ctx)) for wf in workflows]


# ---- required status checks ---------------------------------------------

def _job_matches(job, required):
    names = [job["name"] or job["id"]]
    if job["name"] and job["id"] not in names:
        names.append(job["id"])
    for n in names:
        if "${{" in n:
            rx = re.escape(n)
            rx = re.sub(r"\\\$\\\{\\\{.*?\\\}\\\}", ".*", rx)
            if re.fullmatch(rx, required):
                return True
            continue
        if required == n or required.startswith(n + " (") or required.startswith(n + " / "):
            return True
    return False


def check_required(results, required_names):
    """For each required check name, find the workflow(s) that produce it.

    A required check whose workflow is not triggered stays "Expected -- Waiting
    for status reported" and blocks the PR. Returns a list of dicts.
    """
    out = []
    for req in required_names:
        owners = [(wf, d) for wf, d in results for job in wf.jobs if _job_matches(job, req)]
        if not owners:
            out.append({"check": req, "state": "unknown-check", "workflow": None,
                        "note": "no job in .github/workflows produces this check name "
                                "(it may come from an app or a matrix/reusable-workflow name)"})
            continue
        if any(d.status == RUNS for _, d in owners):
            wf, d = next((w, d) for w, d in owners if d.status == RUNS)
            out.append({"check": req, "state": "ok", "workflow": wf.file, "note": "workflow runs"})
        elif any(d.status == INCONCLUSIVE for _, d in owners):
            wf, d = next((w, d) for w, d in owners if d.status == INCONCLUSIVE)
            out.append({"check": req, "state": "unknown", "workflow": wf.file, "note": d.reason})
        else:
            wf, d = owners[0]
            out.append({"check": req, "state": "stranded", "workflow": wf.file,
                        "note": "%s: %s" % (d.status, d.reason)})
    return out
