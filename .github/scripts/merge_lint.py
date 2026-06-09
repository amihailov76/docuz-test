#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_lint.py
=============
Merge two Vale-compatible JSON lint result files into one.
Prints merged JSON to stdout.

Usage:
    python merge_lint.py <ru_json_path> <en_json_path>
"""
import json
import os
import sys

merged = {}
for path in sys.argv[1:]:
    if not os.path.exists(path):
        continue
    try:
        text = open(path, encoding="utf-8").read().strip()
        if text.startswith("{"):
            merged.update(json.loads(text))
        elif text:
            print(f"[WARN] {path}: not JSON — skipped", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] {path}: {e}", file=sys.stderr)

print(json.dumps(merged))
