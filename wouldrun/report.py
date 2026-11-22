"""Human and JSON output."""

import json

from . import evaluate as ev

_COLORS = {
    ev.RUNS: "32", ev.SKIPPED: "33", ev.NOT_TRIGGERED: "90",
    ev.INCONCLUSIVE: "35", ev.INVALID: "31",
    "ok": "32", "stranded": "31", "unknown": "35", "unknown-check": "35",
}


def _c(text, key, color):
    return "\033[%sm%s\033[0m" % (_COLORS[key], text) if color else text


def describe_context(ctx):
    parts = [ctx.event]
    if ctx.activity and ctx.event not in ("push",):
        parts[0] += " (%s)" % ctx.activity
    if ctx.ref_name:
        if ctx.event in ev.PR_EVENTS:
            parts.append("base branch %s" % ctx.ref_name)
        else:
            parts.append("%s %s" % (ctx.ref_kind, ctx.ref_name))
    if ctx.files is not None:
        parts.append("%d changed file%s" % (len(ctx.files), "" if len(ctx.files) == 1 else "s"))
    return ", ".join(parts)


def render_text(ctx, results, required, color=False, expect=None):
    lines = ["wouldrun: " + describe_context(ctx), ""]
    width = max([len(d.status) for _, d in results] + [3])
    for wf, d in results:
        head = "%s  %s" % (_c(d.status.ljust(width), d.status, color), wf.file)
        if wf.name:
            head += '  "%s"' % wf.name
        lines.append(head)
        pad = " " * (width + 2)
        lines.append(pad + d.reason)
        for extra in d.details:
            lines.append(pad + "  " + extra)
    if not results:
        lines.append("no workflow files found in .github/workflows")
    if required:
        lines += ["", "required checks:"]
        for r in required:
            word = {"ok": "ok", "stranded": "STRANDED", "unknown": "UNKNOWN",
                    "unknown-check": "NOT FOUND"}[r["state"]]
            where = " (%s)" % r["workflow"] if r["workflow"] else ""
            lines.append("  %s  %s%s" % (_c(word.ljust(9), r["state"], color), r["check"], where))
            if r["state"] != "ok":
                lines.append("             " + r["note"])
            if r["state"] == "stranded":
                lines.append("             the PR would sit at \"Expected \u2014 Waiting for status "
                             "to be reported\" and could not merge")
    if expect:
        lines += ["", "expected to run:"]
        for e in expect:
            word = "ok" if e["ok"] else "stranded"
            lines.append("  %s  %s" % (_c(("ok" if e["ok"] else "NOT RUN").ljust(7), word, color), e["name"]))
    return "\n".join(lines)


def render_json(ctx, results, required, expect=None):
    doc = {
        "event": ctx.event,
        "activity": ctx.activity,
        "ref": {"kind": ctx.ref_kind, "name": ctx.ref_name},
        "changed_files": ctx.files,
        "workflows": [
            dict(file=wf.file, name=wf.name, **d.as_dict()) for wf, d in results
        ],
        "required_checks": required,
        "expected": expect or [],
    }
    return json.dumps(doc, indent=2)
