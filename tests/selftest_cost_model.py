#!/usr/bin/env python3
"""tests/selftest_cost_model.py — prove check_cost_model.py has teeth.

Each mutation is applied to a copy of the repository in a temporary directory; the checker must exit
non-zero for every one, and must still pass on the unmutated copy. If a mutation survives, the checker
is not guarding the number it claims to guard.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MUTATIONS = [
    ("docs/markdown-vs-json-cost.md", "$203.80", "$203.08", "doc volume total"),
    ("docs/markdown-vs-json-cost.md", "1.96×", "1.69×", "doc volume multiple"),
    ("docs/markdown-vs-json-cost.md", "$0.008186", "$0.008168", "doc 403 effective cost"),
    ("docs/markdown-vs-json-cost.md", "1.65×", "1.56×", "doc success-rate multiple"),
    ("docs/markdown-vs-json-cost.md", "3,088", "3,808", "doc break-even (Standard)"),
    ("docs/markdown-vs-json-cost.md", "A scrape that returns no result is not charged.",
     "A scrape that returns no result is billed.", "doc vendor quote"),
    ("docs/cost-model.json", '"local_structuring_usd_per_page": 0.0017466',
     '"local_structuring_usd_per_page": 0.0018466', "json local cost"),
    ("docs/cost-model.json", '"output_tokens": 1243', '"output_tokens": 1423', "json output tokens"),
    ("docs/cost-model.json", '"json_page_usd": 0.00495', '"json_page_usd": 0.00459', "json JSON-page price"),
    ("docs/cost-model.json", '"same_block": false', '"same_block": true', "json block verdict"),
]


def copy_tree(dst):
    for sub in ("docs", "tools", "tests"):
        shutil.copytree(os.path.join(ROOT, sub), os.path.join(dst, sub))


def run_checker(root):
    p = subprocess.run([sys.executable, os.path.join(root, "tests", "check_cost_model.py")],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    caught = 0
    with tempfile.TemporaryDirectory() as tmp:
        control = os.path.join(tmp, "control")
        copy_tree(control)
        rc, out = run_checker(control)
        if rc != 0:
            print("CONTROL FAILED — the unmutated tree does not pass:")
            print(out[-2000:])
            return 1
        print("control: PASS")

        for i, (rel, old, new, label) in enumerate(MUTATIONS, 1):
            d = os.path.join(tmp, "m%02d" % i)
            copy_tree(d)
            path = os.path.join(d, rel)
            text = open(path, encoding="utf-8").read()
            if old not in text:
                print("MUTATION %d IMPOSSIBLE (%s): %r not found" % (i, label, old))
                return 1
            open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
            rc, out = run_checker(d)
            if rc == 0:
                print("SURVIVED: %s" % label)
            else:
                caught += 1
                print("caught %d/%d: %s" % (i, len(MUTATIONS), label))

    print("%d/%d mutations caught" % (caught, len(MUTATIONS)))
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    sys.exit(main())
