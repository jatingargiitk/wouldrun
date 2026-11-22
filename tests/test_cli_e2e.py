import json
import subprocess
import sys

from conftest import git, write_workflows
from wouldrun.cli import main

CI = """
name: CI
on:
  pull_request:
    branches: [main]
    paths: ['src/**', '!src/docs/**']
jobs:
  test:
    runs-on: ubuntu-24.04
"""
DOCS = """
name: Docs
on:
  pull_request:
    paths-ignore: ['docs/**', '**.md']
jobs:
  docs:
    runs-on: ubuntu-24.04
"""
PUSH = """
name: Push
on:
  push:
    branches-ignore: ['wip/**']
jobs:
  p:
    runs-on: ubuntu-24.04
"""


def make_repo(tmp_path):
    write_workflows(tmp_path, {"ci.yml": CI, "docs.yml": DOCS, "push.yml": PUSH})
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("a = 1\n")
    (tmp_path / "README.md").write_text("hi\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def by_file(doc):
    return {w["file"].split("/")[-1]: w for w in doc["workflows"]}


def test_pr_with_docs_only_diff_real_git(tmp_path, capsys):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "feature")
    (repo / "README.md").write_text("changed\n")
    git(repo, "commit", "-qam", "docs")
    code = main(["--repo", str(repo), "-e", "pull_request", "--base", "main", "--head", "feature",
                 "--format", "json", "--required", "test", "--required", "docs"])
    doc = json.loads(capsys.readouterr().out)
    assert doc["changed_files"] == ["README.md"]
    w = by_file(doc)
    assert w["ci.yml"]["status"] == "SKIPPED"
    assert w["ci.yml"]["reason"] == "paths: no changed file matched ['src/**', '!src/docs/**']"
    assert w["docs.yml"]["status"] == "SKIPPED"
    assert w["push.yml"]["status"] == "NOT-TRIGGERED-BY-EVENT"
    assert {r["check"]: r["state"] for r in doc["required_checks"]} == {
        "test": "stranded", "docs": "stranded"}
    assert code == 1


def test_pr_three_dot_diff_ignores_changes_on_base(tmp_path, capsys):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "feature")
    (repo / "docs").mkdir()
    (repo / "docs" / "g.md").write_text("g\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "feature docs")
    git(repo, "checkout", "-q", "main")
    (repo / "src" / "b.py").write_text("b = 2\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "main moves on")
    code = main(["--repo", str(repo), "-e", "pull_request", "--base", "main", "--head", "feature",
                 "--format", "json"])
    doc = json.loads(capsys.readouterr().out)
    # BASE...HEAD only has the feature branch's own change, not src/b.py from main
    assert doc["changed_files"] == ["docs/g.md"]
    assert by_file(doc)["ci.yml"]["status"] == "SKIPPED"
    assert code == 0


def test_pr_touching_src_runs_and_required_ok(tmp_path, capsys):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "feature")
    (repo / "src" / "a.py").write_text("a = 2\n")
    git(repo, "commit", "-qam", "code")
    code = main(["--repo", str(repo), "-e", "pull_request", "--base", "main", "--head", "feature",
                 "--format", "json", "--required", "test"])
    doc = json.loads(capsys.readouterr().out)
    assert by_file(doc)["ci.yml"]["status"] == "RUNS"
    assert doc["required_checks"][0]["state"] == "ok"
    assert code == 0


def test_push_two_dot_and_branch_filter(tmp_path, capsys):
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text("again\n")
    git(repo, "commit", "-qam", "second")
    code = main(["--repo", str(repo), "-e", "push", "--ref", "wip/x", "--base", "HEAD~1",
                 "--format", "json"])
    doc = json.loads(capsys.readouterr().out)
    assert doc["changed_files"] == ["README.md"]
    assert by_file(doc)["push.yml"]["reason"] == "branches-ignore: 'wip/**' matched branch 'wip/x'"
    assert code == 0


def test_files_from_stdin_and_expect_run(tmp_path, monkeypatch, capsys):
    import io
    repo = make_repo(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("README.md\n"))
    code = main(["--repo", str(repo), "-e", "pull_request", "-r", "main", "--files", "-",
                 "--expect-run", "CI", "--expect-run", "nonexistent.yml"])
    out = capsys.readouterr().out
    assert "NOT RUN  CI" in out
    assert "NOT RUN  nonexistent.yml" in out
    assert code == 1


def test_bad_base_is_usage_error(tmp_path, capsys):
    repo = make_repo(tmp_path)
    code = main(["--repo", str(repo), "-e", "pull_request", "-r", "main", "--base", "nope"])
    assert code == 2
    assert "git diff" in capsys.readouterr().err


def test_pr_without_ref_is_usage_error(tmp_path, capsys):
    repo = make_repo(tmp_path)
    assert main(["--repo", str(repo), "-e", "pull_request"]) == 2


def test_ref_derived_from_origin_base(tmp_path, capsys):
    repo = make_repo(tmp_path)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "checkout", "-q", "-b", "f")
    (repo / "src" / "a.py").write_text("x\n")
    git(repo, "commit", "-qam", "c")
    main(["--repo", str(repo), "-e", "pull_request", "--base", "origin/main", "--format", "json"])
    doc = json.loads(capsys.readouterr().out)
    assert doc["ref"] == {"kind": "branch", "name": "main"}
    assert by_file(doc)["ci.yml"]["status"] == "RUNS"


def test_tag_flag_and_full_ref(tmp_path, capsys):
    repo = make_repo(tmp_path)
    main(["--repo", str(repo), "-e", "push", "--ref", "refs/tags/v1", "--format", "json"])
    doc = json.loads(capsys.readouterr().out)
    assert doc["ref"] == {"kind": "tag", "name": "v1"}
    # push.yml only defines branches-ignore, so tag pushes do not run it
    assert by_file(doc)["push.yml"]["status"] == "SKIPPED"
    main(["--repo", str(repo), "-e", "push", "--ref", "v1", "--tag", "--format", "json"])
    assert json.loads(capsys.readouterr().out)["ref"]["kind"] == "tag"


def test_no_color_when_piped_and_color_always(tmp_path, capsys):
    repo = make_repo(tmp_path)
    main(["--repo", str(repo), "-e", "push", "-r", "main"])
    assert "\033[" not in capsys.readouterr().out
    main(["--repo", str(repo), "-e", "push", "-r", "main", "--color", "always"])
    assert "\033[32mRUNS" in capsys.readouterr().out


def test_module_entrypoint(tmp_path):
    repo = make_repo(tmp_path)
    proc = subprocess.run([sys.executable, "-m", "wouldrun", "--repo", str(repo), "-r", "main"],
                          capture_output=True, text=True)
    assert proc.returncode == 0
    assert "RUNS" in proc.stdout and "push.yml" in proc.stdout


def test_missing_workflows_dir(tmp_path, capsys):
    assert main(["--repo", str(tmp_path), "-r", "main"]) == 0
    assert "no workflow files found" in capsys.readouterr().out
