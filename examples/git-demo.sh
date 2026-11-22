#!/usr/bin/env bash
# Builds a throwaway git repo from examples/repo, makes a docs-only feature branch,
# and asks wouldrun about the pull request using a real `git diff --name-only main...feature`.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cp -R "$here/repo/." "$tmp/"
export GIT_AUTHOR_NAME=demo GIT_AUTHOR_EMAIL=demo@example.com
export GIT_COMMITTER_NAME=demo GIT_COMMITTER_EMAIL=demo@example.com
git -C "$tmp" init -q -b main
mkdir -p "$tmp/src" "$tmp/docs"
echo 'print("hi")' > "$tmp/src/app.py"
echo '# demo' > "$tmp/README.md"
git -C "$tmp" add -A && git -C "$tmp" commit -q -m base
git -C "$tmp" checkout -q -b feature
echo 'more docs' > "$tmp/docs/guide.md"
echo '# demo, edited' > "$tmp/README.md"
git -C "$tmp" add -A && git -C "$tmp" commit -q -m "docs only"
export PYTHONPATH="$here/.."
python3 -m wouldrun --repo "$tmp" -e pull_request --base main --head feature --required test || true
