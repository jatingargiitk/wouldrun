#!/usr/bin/env python3
"""Run every ```console block in README.md and compare the output.

A block is: one or more lines starting with "$ " (only the first is the command)
followed by the expected stdout. Run with --update to rewrite the blocks from real output.
The exit status of the command is not compared.
"""
import os
import re
import shlex
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")
BLOCK = re.compile(r"```console\n(.*?)```", re.S)


def run(cmd):
    argv = shlex.split(cmd)
    if argv[0] == "wouldrun":
        argv = [sys.executable, "-m", "wouldrun"] + argv[1:]
    env = dict(os.environ, PYTHONPATH=ROOT, NO_COLOR="1")
    proc = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True)
    return (proc.stdout + proc.stderr).rstrip("\n")


def main():
    update = "--update" in sys.argv
    text = open(README, encoding="utf-8").read()
    bad = 0
    count = 0

    def fix(m):
        nonlocal bad, count
        body = m.group(1)
        first, _, rest = body.partition("\n")
        if not first.startswith("$ "):
            return m.group(0)
        count += 1
        actual = run(first[2:])
        if actual != rest.rstrip("\n"):
            bad += 1
            print("MISMATCH for: %s" % first, file=sys.stderr)
            print("--- README\n%s\n--- actual\n%s" % (rest.rstrip("\n"), actual), file=sys.stderr)
        return "```console\n%s\n%s\n```" % (first, actual)

    new = BLOCK.sub(fix, text)
    if update:
        open(README, "w", encoding="utf-8").write(new)
        print("updated %d example blocks" % count)
        return 0
    if count == 0:
        print("no console blocks found", file=sys.stderr)
        return 1
    print("%d README example blocks checked, %d mismatched" % (count, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
