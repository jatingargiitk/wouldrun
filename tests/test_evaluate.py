import pytest

from wouldrun import evaluate as ev
from wouldrun.evaluate import Context


def run(wf, text, **kw):
    return ev.evaluate(wf(text), Context(**kw))


def test_on_key_is_not_a_boolean(wf):
    w = wf("on: push\njobs: {}\n")
    assert list(w.events) == ["push"]
    assert not w.error


def test_on_string_list_map_forms(wf):
    assert list(wf("on: push\njobs: {}\n").events) == ["push"]
    assert list(wf("on: [push, fork]\njobs: {}\n").events) == ["push", "fork"]
    w = wf("on:\n  push:\n  pull_request:\n    branches: [main]\njobs: {}\n")
    assert list(w.events) == ["push", "pull_request"]


def test_yaml_error_is_invalid(wf):
    d = run(wf, "on:\n  push:\n    paths:\n      - **/README.md\n", event="push")
    assert d.status == ev.INVALID
    assert "YAML" in d.reason


def test_missing_on_is_invalid(wf):
    assert run(wf, "name: x\njobs: {}\n", event="push").status == ev.INVALID


def test_event_not_listed(wf):
    d = run(wf, "on: [push]\njobs: {}\n", event="pull_request", ref_name="main", activity="opened")
    assert d.status == ev.NOT_TRIGGERED
    assert "does not list 'pull_request'" in d.reason


def test_plain_push_runs(wf):
    d = run(wf, "on: push\njobs: {}\n", event="push", ref_name="anything")
    assert d.status == ev.RUNS


def test_branches_include_and_exclude_order(wf):
    text = "on:\n  push:\n    branches: ['releases/**', '!releases/**-alpha']\njobs: {}\n"
    assert run(wf, text, event="push", ref_name="releases/10").status == ev.RUNS
    d = run(wf, text, event="push", ref_name="releases/10-alpha")
    assert d.status == ev.SKIPPED and "!releases/**-alpha" in d.reason
    d = run(wf, text, event="push", ref_name="main")
    assert d.status == ev.SKIPPED and "no pattern" in d.reason


def test_branches_ignore(wf):
    text = "on:\n  push:\n    branches-ignore: ['release/**']\njobs: {}\n"
    d = run(wf, text, event="push", ref_name="release/1.2")
    assert d.status == ev.SKIPPED
    assert d.reason == "branches-ignore: 'release/**' matched branch 'release/1.2'"
    assert run(wf, text, event="push", ref_name="main").status == ev.RUNS


def test_branches_and_ignore_together_invalid(wf):
    text = "on:\n  push:\n    branches: [main]\n    branches-ignore: [x]\njobs: {}\n"
    d = run(wf, text, event="push", ref_name="main")
    assert d.status == ev.INVALID and "branches-ignore" in d.reason


def test_tags_and_tags_ignore_invalid(wf):
    text = "on:\n  push:\n    tags: [v1]\n    tags-ignore: [v2]\njobs: {}\n"
    assert run(wf, text, event="push", ref_kind="tag", ref_name="v1").status == ev.INVALID


def test_only_negative_patterns_invalid(wf):
    text = "on:\n  push:\n    branches: ['!main']\njobs: {}\n"
    assert run(wf, text, event="push", ref_name="dev").status == ev.INVALID


def test_tag_only_workflow_skips_branch_pushes_and_vice_versa(wf):
    tags_only = "on:\n  push:\n    tags: ['v*']\njobs: {}\n"
    assert run(wf, tags_only, event="push", ref_name="main").status == ev.SKIPPED
    assert run(wf, tags_only, event="push", ref_kind="tag", ref_name="v1").status == ev.RUNS
    branches_only = "on:\n  push:\n    branches: [main]\njobs: {}\n"
    d = run(wf, branches_only, event="push", ref_kind="tag", ref_name="v1")
    assert d.status == ev.SKIPPED and "tag pushes" in d.reason
    # tags-ignore alone still means "branch pushes do not run"
    ti = "on:\n  push:\n    tags-ignore: ['v2']\njobs: {}\n"
    assert run(wf, ti, event="push", ref_name="main").status == ev.SKIPPED
    assert run(wf, ti, event="push", ref_kind="tag", ref_name="v2").status == ev.SKIPPED
    assert run(wf, ti, event="push", ref_kind="tag", ref_name="v3").status == ev.RUNS


def test_branches_and_tags_both_defined(wf):
    text = "on:\n  push:\n    branches: [main]\n    tags: ['v*']\njobs: {}\n"
    assert run(wf, text, event="push", ref_name="main").status == ev.RUNS
    assert run(wf, text, event="push", ref_name="dev").status == ev.SKIPPED
    assert run(wf, text, event="push", ref_kind="tag", ref_name="v1").status == ev.RUNS


def test_paths_filter(wf):
    text = "on:\n  push:\n    paths: ['src/**', '!src/docs/**']\njobs: {}\n"
    d = run(wf, text, event="push", ref_name="main", files=["src/a.py", "README.md"])
    assert d.status == ev.RUNS and "src/a.py matched 'src/**'" in d.reason
    d = run(wf, text, event="push", ref_name="main", files=["src/docs/x.md"])
    assert d.status == ev.SKIPPED
    assert "src/docs/x.md: excluded by '!src/docs/**'" in d.details


def test_paths_ignore(wf):
    text = "on:\n  push:\n    paths-ignore: ['docs/**']\njobs: {}\n"
    assert run(wf, text, event="push", ref_name="m", files=["docs/a.md"]).status == ev.SKIPPED
    d = run(wf, text, event="push", ref_name="m", files=["docs/a.md", "x.py"])
    assert d.status == ev.RUNS and "x.py is not ignored" in d.reason


def test_paths_with_no_files_skips(wf):
    text = "on:\n  push:\n    paths: ['**']\njobs: {}\n"
    d = run(wf, text, event="push", ref_name="m", files=[])
    assert d.status == ev.SKIPPED and "no files changed" in d.reason


def test_paths_without_files_is_inconclusive(wf):
    text = "on:\n  push:\n    paths: ['src/**']\njobs: {}\n"
    assert run(wf, text, event="push", ref_name="m").status == ev.INCONCLUSIVE


def test_branch_and_paths_must_both_pass(wf):
    text = "on:\n  push:\n    branches: [main]\n    paths: ['src/**']\njobs: {}\n"
    assert run(wf, text, event="push", ref_name="dev", files=["src/a"]).status == ev.SKIPPED
    assert run(wf, text, event="push", ref_name="main", files=["x"]).status == ev.SKIPPED
    assert run(wf, text, event="push", ref_name="main", files=["src/a"]).status == ev.RUNS


def test_paths_not_evaluated_for_tags(wf):
    text = "on:\n  push:\n    tags: ['v*']\n    paths: ['src/**']\njobs: {}\n"
    d = run(wf, text, event="push", ref_kind="tag", ref_name="v1", files=["README.md"])
    assert d.status == ev.RUNS
    assert any("not evaluated for tag" in x for x in d.details)


def test_large_diff_not_in_first_3000_is_inconclusive(wf):
    text = "on:\n  pull_request:\n    paths: ['src/**']\njobs: {}\n"
    files = ["other/%d" % i for i in range(3001)] + ["src/a.py"]
    d = run(wf, text, event="pull_request", ref_name="main", activity="opened", files=files)
    assert d.status == ev.INCONCLUSIVE
    files = ["src/a.py"] + ["other/%d" % i for i in range(3001)]
    d = run(wf, text, event="pull_request", ref_name="main", activity="opened", files=files)
    assert d.status == ev.RUNS


def test_push_over_1000_commits_always_runs(wf):
    text = "on:\n  push:\n    paths: ['src/**']\njobs: {}\n"
    d = run(wf, text, event="push", ref_name="main", files=["README.md"], commits=1001)
    assert d.status == ev.RUNS and "always runs" in d.reason
    d = run(wf, text, event="push", ref_name="main", files=["README.md"], commits=1000)
    assert d.status == ev.SKIPPED


@pytest.mark.parametrize("activity,expected", [
    ("opened", ev.RUNS), ("synchronize", ev.RUNS), ("reopened", ev.RUNS),
    ("closed", ev.NOT_TRIGGERED), ("labeled", ev.NOT_TRIGGERED),
])
def test_pr_default_activity_types(wf, activity, expected):
    d = run(wf, "on: pull_request\njobs: {}\n", event="pull_request", ref_name="main",
            activity=activity)
    assert d.status == expected


def test_pr_explicit_types(wf):
    text = "on:\n  pull_request:\n    types: [opened]\njobs: {}\n"
    d = run(wf, text, event="pull_request", ref_name="main", activity="closed")
    assert d.status == ev.NOT_TRIGGERED
    assert d.reason == "types: closed not in ['opened']"
    assert run(wf, text, event="pull_request", ref_name="main", activity="opened").status == ev.RUNS


def test_pr_branches_match_base(wf):
    text = "on:\n  pull_request:\n    branches: [main]\njobs: {}\n"
    assert run(wf, text, event="pull_request", ref_name="main", activity="opened").status == ev.RUNS
    d = run(wf, text, event="pull_request", ref_name="develop", activity="opened")
    assert d.status == ev.SKIPPED


def test_pull_request_target(wf):
    text = "on:\n  pull_request_target:\n    branches: [main]\n    paths: ['a/**']\njobs: {}\n"
    d = run(wf, text, event="pull_request_target", ref_name="main", activity="opened", files=["b"])
    assert d.status == ev.SKIPPED


def test_workflow_dispatch_and_schedule(wf):
    text = "on:\n  workflow_dispatch:\n  schedule:\n    - cron: '0 0 * * *'\njobs: {}\n"
    assert run(wf, text, event="workflow_dispatch").status == ev.RUNS
    assert run(wf, text, event="schedule").status == ev.RUNS
    assert run(wf, "on: push\njobs: {}\n", event="workflow_dispatch").status == ev.NOT_TRIGGERED


def test_other_event_types(wf):
    text = "on:\n  issues:\n    types: [opened]\njobs: {}\n"
    assert run(wf, text, event="issues", activity="opened").status == ev.RUNS
    assert run(wf, text, event="issues", activity="closed").status == ev.NOT_TRIGGERED
    assert run(wf, text, event="issues").status == ev.INCONCLUSIVE


def test_ref_filter_without_ref_is_inconclusive(wf):
    assert run(wf, "on:\n  push:\n    branches: [main]\njobs: {}\n", event="push").status == ev.INCONCLUSIVE


def test_scalar_filter_value_is_one_pattern(wf):
    d = run(wf, "on:\n  push:\n    branches: main\njobs: {}\n", event="push", ref_name="main")
    assert d.status == ev.RUNS


# ---- required checks ----

def _results(wf, text, ctx):
    w = wf(text)
    return [(w, ev.evaluate(w, ctx))]


def test_required_check_stranded_by_paths(wf):
    text = """
on:
  pull_request:
    paths: ['src/**']
jobs:
  test:
    runs-on: ubuntu-24.04
  lint:
    name: Lint code
    runs-on: ubuntu-24.04
"""
    ctx = Context("pull_request", "branch", "main", "opened", files=["README.md"])
    res = _results(wf, text, ctx)
    out = ev.check_required(res, ["test", "Lint code", "other"])
    assert [o["state"] for o in out] == ["stranded", "stranded", "unknown-check"]
    ctx = Context("pull_request", "branch", "main", "opened", files=["src/a.py"])
    out = ev.check_required(_results(wf, text, ctx), ["test"])
    assert out[0]["state"] == "ok"


def test_required_check_matrix_and_expression_names(wf):
    text = """
on:
  pull_request:
    paths: ['src/**']
jobs:
  test:
    strategy:
      matrix:
        py: ['3.9', '3.10']
    runs-on: ubuntu-24.04
  build:
    name: build ${{ matrix.os }}
    runs-on: ubuntu-24.04
"""
    ctx = Context("pull_request", "branch", "main", "opened", files=["README.md"])
    out = ev.check_required(_results(wf, text, ctx), ["test (3.9)", "build linux"])
    assert [o["state"] for o in out] == ["stranded", "stranded"]


def test_required_check_inconclusive(wf):
    text = "on:\n  pull_request:\n    paths: ['src/**']\njobs:\n  test:\n    runs-on: x\n"
    ctx = Context("pull_request", "branch", "main", "opened", files=None)
    assert ev.check_required(_results(wf, text, ctx), ["test"])[0]["state"] == "unknown"
