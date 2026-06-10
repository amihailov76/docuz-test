#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_rules.py
==============
Fetch linter rules (Russian YAML) and style guide from MCP server.
Falls back to local files if MCP is unavailable or not configured.

Writes fetched content into $RUNNER_TEMP/rules/{Russian,style_guide}/.
Appends ru_rules_dir, styleguide_dir, mcp_status to $GITHUB_OUTPUT.

Env vars:
    MCP_SERVER_URL  -- base URL of MCP server (optional)
    MCP_API_KEY     -- Bearer token for MCP (optional)
    RUNNER_TEMP     -- runner temp directory
    GITHUB_OUTPUT   -- path to GitHub Actions output file
"""
import json
import os
import shutil
import urllib.request
from pathlib import Path

mcp_url = os.environ.get("MCP_SERVER_URL", "").strip()
mcp_key = os.environ.get("MCP_API_KEY", "").strip()
temp    = os.environ.get("RUNNER_TEMP", "/tmp")
ws      = os.getcwd()

ru_dir = Path(temp) / "rules" / "Russian"
sg_dir = Path(temp) / "rules" / "style_guide"
ru_dir.mkdir(parents=True, exist_ok=True)
sg_dir.mkdir(parents=True, exist_ok=True)

mcp_ok = False
if mcp_url and mcp_key:
    try:
        headers = {"Authorization": f"Bearer {mcp_key}"}

        req = urllib.request.Request(
            f"{mcp_url}/tools/get_forbidden_words", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            for stem, content in json.loads(r.read()).get("rules", {}).items():
                (ru_dir / f"{stem}.yml").write_text(content, encoding="utf-8")

        req2 = urllib.request.Request(
            f"{mcp_url}/tools/get_style_guide", headers=headers)
        with urllib.request.urlopen(req2, timeout=10) as r:
            data = json.loads(r.read())
            sections = data.get("sections") or {}
            if not sections and "content" in data:
                (sg_dir / "styleguide.md").write_text(data["content"], encoding="utf-8")
            else:
                for fname, text in sections.items():
                    (sg_dir / fname).write_text(text, encoding="utf-8")

        mcp_ok = True
        print("[INFO] Rules and style guide fetched from MCP server.")
    except Exception as e:
        print(f"[WARN] MCP fetch failed: {e}. Using local files.")

if not mcp_ok:
    local_ru = Path(ws) / "styles" / "Russian"
    local_sg = Path(ws) / "style_guide"
    if local_ru.exists():
        shutil.copytree(str(local_ru), str(ru_dir), dirs_exist_ok=True)
    if local_sg.exists():
        shutil.copytree(str(local_sg), str(sg_dir), dirs_exist_ok=True)
    print("[INFO] Using local rules and style guide.")

gh_out = os.environ.get("GITHUB_OUTPUT", "")
if gh_out:
    with open(gh_out, "a") as f:
        f.write(f"ru_rules_dir={ru_dir}\n")
        f.write(f"styleguide_dir={sg_dir}\n")
        f.write(f"mcp_status={'ok' if mcp_ok else 'unavailable'}\n")
