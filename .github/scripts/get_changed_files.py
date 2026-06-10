#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_changed_files.py
====================
Fetch list of changed .mdx files in a GitHub PR via API.
Prints one filepath per line (docs/ru/... or docs/en/...).

Env vars:
    GITHUB_TOKEN  -- GitHub auth token
    REPO          -- owner/repo (e.g. amihailov76/docuz-test)
    PR_NUMBER     -- PR number (string); exits cleanly if empty
"""
import os
import json
import sys
import urllib.request

token  = os.environ["GITHUB_TOKEN"]
repo   = os.environ["REPO"]
pr_num = os.environ.get("PR_NUMBER", "").strip()

print(f"[DEBUG] pr_num={repr(pr_num)}", file=sys.stderr)

if not pr_num:
    print("[WARN] No PR number — cannot detect changed files.", file=sys.stderr)
    sys.exit(0)

url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}/files?per_page=100"
print(f"[DEBUG] Fetching: {url}", file=sys.stderr)

req = urllib.request.Request(url, headers={
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github+json",
})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        files = json.load(r)
    print(f"[DEBUG] Total files in PR: {len(files)}", file=sys.stderr)
    for f in files:
        name = f["filename"]
        print(f"[DEBUG] file: {name}", file=sys.stderr)
        if name.startswith("docs/") and name.endswith(".mdx"):
            parts = name.split("/")
            if len(parts) >= 2 and parts[1] in ("ru", "en"):
                print(name)
except Exception as e:
    print(f"[ERROR] API call failed: {e}", file=sys.stderr)
    sys.exit(1)
