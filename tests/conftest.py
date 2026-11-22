import os
import subprocess
import textwrap

import pytest

from wouldrun.workflow import load_workflows


def write_workflows(root, files):
    d = os.path.join(str(root), ".github", "workflows")
    os.makedirs(d, exist_ok=True)
    for name, body in files.items():
        with open(os.path.join(d, name), "w") as fh:
            fh.write(textwrap.dedent(body))
    return str(root)


@pytest.fixture
def wf(tmp_path):
    """Return a function: wf(yaml_text) -> Workflow parsed from a temp file."""
    counter = [0]

    def make(text):
        counter[0] += 1
        name = "w%d.yml" % counter[0]
        write_workflows(tmp_path, {name: text})
        found = [w for w in load_workflows(str(tmp_path)) if w.file.endswith(name)]
        return found[0]

    return make


def git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    subprocess.run(["git", "-C", str(repo)] + list(args), check=True, env=env,
                   capture_output=True)
