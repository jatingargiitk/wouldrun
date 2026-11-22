"""Load .github/workflows/*.yml and normalise the ``on:`` key."""

import glob
import os
import re

import yaml


class _Loader(yaml.SafeLoader):
    """SafeLoader that only treats ``true``/``false`` as booleans.

    Stock PyYAML implements YAML 1.1, where the bare key ``on`` (and ``yes``,
    ``no``, ``off``) become booleans, so ``on:`` arrives as the key ``True``.
    GitHub's parser does not do that, so we drop the 1.1 bool resolver.
    """


_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:bool"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false|True|TRUE|False|FALSE)$"),
    list("tTfF"),
)


class Workflow:
    def __init__(self, path, rel):
        self.path = path
        self.file = rel
        self.name = None
        self.events = {}   # event name -> config (dict, list, or None)
        self.jobs = []     # list of dicts: id, name, matrix, uses
        self.error = None

    @property
    def label(self):
        return self.name or self.file


def normalise_on(raw):
    """Return {event: config} for the string, list and map forms of ``on:``."""
    if isinstance(raw, str):
        return {raw: None}
    if isinstance(raw, list):
        return {str(e): None for e in raw}
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items()}
    raise ValueError("`on:` must be a string, a list or a map, got %s" % type(raw).__name__)


def _jobs(doc):
    out = []
    jobs = doc.get("jobs")
    if isinstance(jobs, dict):
        for jid, job in jobs.items():
            job = job if isinstance(job, dict) else {}
            strategy = job.get("strategy")
            out.append({
                "id": str(jid),
                "name": job.get("name") if isinstance(job.get("name"), str) else None,
                "matrix": isinstance(strategy, dict) and "matrix" in strategy,
                "uses": isinstance(job.get("uses"), str),
            })
    return out


def parse_workflow(path, rel):
    wf = Workflow(path, rel)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.load(fh, Loader=_Loader)
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        wf.error = "YAML error: %s" % str(exc).replace("\n", " ")
        return wf
    if not isinstance(doc, dict):
        wf.error = "workflow file is not a YAML mapping"
        return wf
    if isinstance(doc.get("name"), str) and doc["name"].strip():
        wf.name = doc["name"].strip()
    raw_on = doc["on"] if "on" in doc else doc.get(True)
    if raw_on is None:
        wf.error = "missing `on:` key"
        return wf
    try:
        wf.events = normalise_on(raw_on)
    except ValueError as exc:
        wf.error = str(exc)
        return wf
    wf.jobs = _jobs(doc)
    return wf


def load_workflows(repo):
    d = os.path.join(repo, ".github", "workflows")
    paths = sorted(glob.glob(os.path.join(d, "*.yml")) + glob.glob(os.path.join(d, "*.yaml")))
    return [parse_workflow(p, os.path.relpath(p, repo).replace(os.sep, "/")) for p in paths]
