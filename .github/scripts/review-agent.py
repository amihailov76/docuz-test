#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docs Review Agent
=================
Reads PR diff + linter JSON, loads style guide via MCP server
(or local fallback), calls LLM and posts inline comments + summary
in a GitHub PR Review.

Env vars (LLM):
    LLM_API_KEY   -- API key (required)
    LLM_BASE_URL  -- base URL for OpenAI-compatible API
    LLM_MODEL     -- model name (default: gpt-4o-mini)
"""

import argparse
import json
import os
import re
import sys
import textwrap
import time
from pathlib import Path

import requests
from openai import OpenAI

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL     = "gpt-4o-mini"
MAX_INLINE        = 20          # max inline comments
MAX_FILES         = 10          # max files per run
MAX_DIFF_CHARS    = 60_000      # truncate diff to this size
MAX_FILE_CHARS    = 30_000      # per-file content guard (skip oversized files)
MCP_TIMEOUT       = 10          # seconds per MCP request
STYLE_GUIDE_DIR   = Path(__file__).parent.parent.parent / "style_guide"

# Mirrors the mapping in mcp_server/app.py.
# Maps linter rule names to style guide section file stems.
RULE_SECTION_MAP: dict[str, list[str]] = {
    "Russian.WordChoice":    ["03_word_choice"],
    "Russian.Substitutions": ["01_instructions", "02_neutral_tone"],
}
ENGLISH_SECTIONS: list[str] = ["04_sentences", "05_links"]

# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------

def gh_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_pr_diff(repo, pr_number, token):
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    resp = requests.get(
        url,
        headers={**gh_headers(token), "Accept": "application/vnd.github.v3.diff"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def post_review(repo, pr_number, token, comments, summary):
    """Post a GitHub PR Review (COMMENT type, never REQUEST_CHANGES)."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
    payload = {
        "body": summary,
        "event": "COMMENT",
        "comments": [
            {
                "path": c["path"],
                "line": c["line"],
                "side": "RIGHT",
                "body": c["body"],
            }
            for c in comments
        ],
    }
    resp = requests.post(url, headers=gh_headers(token), json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        print(f"[ERROR] GitHub API {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        resp.raise_for_status()
    print(f"[OK] Review posted with {len(comments)} inline comment(s).")


def post_summary_only(repo, pr_number, token, summary):
    post_review(repo, pr_number, token, [], summary)


# ---------------------------------------------------------------------------
# MCP / Style guide
# ---------------------------------------------------------------------------

def fetch_style_guide_mcp(mcp_url, mcp_key, section=None):
    """Fetch full style guide from MCP server (all sections)."""
    params: dict[str, str] = {"section": section} if section else {}
    resp = requests.get(
        f"{mcp_url}/tools/get_style_guide",
        headers={"Authorization": f"Bearer {mcp_key}"},
        params=params,
        timeout=MCP_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if "content" in data:
        return data["content"]
    if "sections" in data:
        return "\n\n".join(data["sections"].values())
    return json.dumps(data)


def load_style_guide_local():
    """Load full style guide from local files."""
    if not STYLE_GUIDE_DIR.exists():
        return "(style guide unavailable)"
    parts = [md.read_text(encoding="utf-8") for md in sorted(STYLE_GUIDE_DIR.glob("0*.md"))]
    return "\n\n---\n\n".join(parts) if parts else "(style guide empty)"


def get_style_guide(mcp_status, mcp_url, mcp_key):
    """Load full style guide from MCP server or local fallback."""
    if mcp_status == "ok" and mcp_url and mcp_key:
        try:
            guide = fetch_style_guide_mcp(mcp_url, mcp_key)
            print("[OK] Style guide loaded from MCP server (all sections).")
            return guide
        except Exception as exc:
            print(f"[WARN] MCP fetch failed ({exc}), using local fallback.")
    else:
        print("[INFO] MCP unavailable, using local style guide (all sections).")
    return load_style_guide_local()


# ---------------------------------------------------------------------------
# Linter output
# ---------------------------------------------------------------------------

def parse_vale_output(vale_json_path):
    """Parse linter JSON (Vale-compatible format). Returns {filepath: [alerts]}."""
    try:
        raw = Path(vale_json_path).read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

    result = {}
    for filepath, alerts in data.items():
        items = []
        for alert in alerts:
            items.append({
                "line":     alert.get("Line", 0),
                "message":  alert.get("Message", ""),
                "rule":     alert.get("Check", ""),
                "severity": alert.get("Severity", "warning"),
            })
        if items:
            key = filepath.lstrip("./")
            result[key] = items
    return result


def format_linter_for_prompt(linter_results):
    """Format linter findings as readable text for the LLM prompt."""
    if not linter_results:
        return "Linter found no violations."
    lines = []
    for filepath, alerts in linter_results.items():
        lines.append(f"File: {filepath}")
        for a in alerts:
            lines.append(f"  Line {a['line']}: [{a['rule']}] {a['message']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def extract_added_lines(diff, target_files):
    """
    Extract added lines from a unified diff.
    Returns {filepath: [(line_number, text), ...]}
    """
    result = {}
    current_file = None
    new_line = 0

    for raw_line in diff.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
            if current_file not in result:
                result[current_file] = []
            continue
        if raw_line.startswith("--- ") or raw_line.startswith("diff ") or raw_line.startswith("index "):
            continue

        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
        if hunk:
            new_line = int(hunk.group(1)) - 1
            continue

        if current_file is None:
            continue

        if raw_line.startswith("+"):
            new_line += 1
            if current_file in target_files:
                result[current_file].append((new_line, raw_line[1:]))
        elif not raw_line.startswith("-"):
            new_line += 1

    return result


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a strict technical documentation editor.\n"
    "You receive the FULL content of each changed file, plus the PR diff showing what was added.\n"
    "Review the ENTIRE file for style guide violations — not just the changed lines.\n\n"
    "Rules:\n"
    "- Comment only on real style guide violations. Silence is better than noise.\n"
    f"- Maximum {{max_inline}} inline comments. Pick the most important ones.\n"
    "- INLINE COMMENTS: only on lines that appear in the diff (added/changed lines).\n"
    "  GitHub does not allow inline comments on unchanged lines.\n"
    "- UNCHANGED LINES with violations: mention them in the 'summary' field, not as inline comments.\n"
    "- Do not duplicate: if the linter already flagged something precisely, you may add explanation,\n"
    "  but don't repeat the same thing in different words.\n"
    "- Tone: neutral, concrete. Don't say 'good' or 'bad'.\n"
    "  Say what specifically is violated and how to fix it.\n"
    "- Do not comment on: code, JSX tags, frontmatter (title/description),\n"
    "  file names, URLs, technical terms.\n"
    "- Comment language: Russian for docs/ru/, English for docs/en/.\n\n"
    "Reply STRICTLY in JSON format (no markdown wrapper):\n"
    '{{\n'
    '  "comments": [\n'
    '    {{"path": "docs/ru/example.mdx", "line": 42, "body": "Comment text"}}\n'
    '  ],\n'
    '  "summary": "Brief summary: what was checked, main issues (2-4 sentences). '
    'Include issues found in unchanged lines here."\n'
    '}}\n'
).format(max_inline=MAX_INLINE)


def read_changed_files(changed_files):
    """
    Read full content of each changed file from disk.
    Returns {filepath: content_or_error_string}.
    Skips files larger than MAX_FILE_CHARS.
    """
    contents = {}
    for filepath in changed_files:
        try:
            text = Path(filepath).read_text(encoding="utf-8")
            if len(text) > MAX_FILE_CHARS:
                contents[filepath] = f"[File too large to include ({len(text)} chars > {MAX_FILE_CHARS})]"
            else:
                contents[filepath] = text
        except FileNotFoundError:
            contents[filepath] = "[File not found — may have been deleted in this PR]"
        except Exception as exc:
            contents[filepath] = f"[Could not read file: {exc}]"
    return contents


def build_user_message(diff_excerpt, linter_text, style_guide, changed_files, file_contents=None):
    MAX_GUIDE = 50_000
    guide_excerpt = style_guide[:MAX_GUIDE]
    if len(style_guide) > MAX_GUIDE:
        guide_excerpt += "\n\n[style guide truncated to save tokens]"

    files_section = ""
    if file_contents:
        parts = []
        for fp, content in file_contents.items():
            parts.append(f"### {fp}\n```\n{content}\n```")
        files_section = "\n\n".join(parts)
    else:
        files_section = chr(10).join(changed_files)

    return textwrap.dedent(f"""\
        ## Full file content
        {files_section}

        ## Linter findings
        {linter_text}

        ## Diff (what changed in this PR)
        ```diff
        {diff_excerpt}
        ```

        ## Style guide
        {guide_excerpt}
    """)


# ---------------------------------------------------------------------------
# OpenAI-compatible LLM
# ---------------------------------------------------------------------------

def extract_json_from_response(raw):
    """Extract JSON from LLM response. Handles plain JSON, markdown blocks, embedded JSON."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    md_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if md_match:
        try:
            return json.loads(md_match.group(1))
        except json.JSONDecodeError:
            pass
    obj_match = re.search(r"\{[\s\S]+\}", raw)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not extract JSON from LLM response (first 300 chars): {raw[:300]}")


def call_llm(system, user, api_key, model=DEFAULT_MODEL, base_url=None, max_retries=3):
    """
    Call LLM via OpenAI-compatible API, returns parsed JSON dict.
    Retries up to max_retries times with exponential backoff.
    Tries response_format=json_object first; falls back without it if unsupported.
    """
    client_kwargs = {"api_key": api_key, "timeout": 180.0}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)
    last_exc = None

    for attempt in range(1, max_retries + 1):
        try:
            call_kwargs = dict(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=0.2,
                max_tokens=4096,
            )
            try:
                response = client.chat.completions.create(
                    **call_kwargs,
                    response_format={"type": "json_object"},
                )
            except Exception as fmt_exc:
                print(f"[WARN] response_format not supported, retrying without it: {fmt_exc}")
                response = client.chat.completions.create(**call_kwargs)

            raw = response.choices[0].message.content
            return extract_json_from_response(raw)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                wait = 2 ** (attempt - 1)
                print(f"[WARN] LLM attempt {attempt}/{max_retries} failed: {exc}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"[ERROR] LLM: all {max_retries} attempts exhausted.")

    raise last_exc


# ---------------------------------------------------------------------------
# Direct inline comments from linter (exact line numbers, no LLM needed)
# ---------------------------------------------------------------------------

def linter_inline_comments(linter_results, diff_added, changed_files, limit=MAX_INLINE):
    """
    Convert linter findings directly to GitHub inline comments,
    using exact line numbers from the linter output.
    Only includes lines that appear in the PR diff (added lines).
    """
    added_lines = {
        fp: {ln for ln, _ in lines}
        for fp, lines in diff_added.items()
    }
    comments = []
    seen = set()

    for filepath, alerts in linter_results.items():
        norm = filepath.lstrip("./")
        if norm not in changed_files:
            continue
        for alert in alerts:
            line = alert.get("line", 0)
            if line <= 0:
                continue
            if norm not in added_lines or line not in added_lines[norm]:
                continue
            key = (norm, line)
            if key in seen:
                continue
            seen.add(key)
            rule = alert.get("rule", "")
            msg  = alert.get("message", "")
            comments.append({"path": norm, "line": line, "body": f"**{rule}**\n{msg}"})
            if len(comments) >= limit:
                return comments

    return comments


# ---------------------------------------------------------------------------
# Validate LLM-generated comments
# ---------------------------------------------------------------------------

def validate_comments(comments, diff_added, changed_files):
    """
    Filter LLM-generated comments:
    - only to actually changed (added) lines
    - only to files from changed_files
    - limit MAX_INLINE
    """
    valid = []
    added_lines = {
        fp: {ln for ln, _ in lines}
        for fp, lines in diff_added.items()
    }

    for c in comments:
        path = c.get("path", "")
        line = c.get("line")
        body = c.get("body", "").strip()

        if not path or not line or not body:
            continue
        norm_path = path.lstrip("./")
        if norm_path not in changed_files:
            print(f"[SKIP] {norm_path}: not in changed files list")
            continue
        if norm_path not in added_lines or line not in added_lines[norm_path]:
            print(f"[SKIP] {norm_path}:{line}: line not added in this PR")
            continue

        valid.append({"path": norm_path, "line": line, "body": body})
        if len(valid) >= MAX_INLINE:
            print(f"[INFO] Reached limit of {MAX_INLINE} comments.")
            break

    return valid


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed-files", required=True,
                        help="File with list of changed paths (one per line)")
    parser.add_argument("--vale-output", required=True,
                        help="Linter JSON output (Vale-compatible format)")
    args = parser.parse_args()

    token      = os.environ["GITHUB_TOKEN"]
    repo       = os.environ["REPO"]
    pr_number  = os.environ.get("PR_NUMBER", "").strip()
    llm_key    = os.environ["LLM_API_KEY"]
    llm_base   = os.environ.get("LLM_BASE_URL") or None
    llm_model  = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    mcp_url    = os.environ.get("MCP_SERVER_URL", "")
    mcp_key    = os.environ.get("MCP_API_KEY", "")
    mcp_status = os.environ.get("MCP_STATUS", "unavailable")

    if not pr_number:
        print("[INFO] PR_NUMBER not set (workflow_dispatch without PR). Exiting cleanly.")
        sys.exit(0)

    changed_files = [
        line.strip()
        for line in Path(args.changed_files).read_text().splitlines()
        if line.strip()
    ]
    if not changed_files:
        print("[INFO] No files to review. Exiting.")
        sys.exit(0)

    if len(changed_files) > MAX_FILES:
        print(f"[WARN] {len(changed_files)} files, processing first {MAX_FILES}.")
        changed_files = changed_files[:MAX_FILES]

    print(f"[INFO] Files to review: {len(changed_files)}")

    print("[INFO] Fetching PR diff...")
    diff = get_pr_diff(repo, pr_number, token)
    diff_excerpt = diff[:MAX_DIFF_CHARS]
    if len(diff) > MAX_DIFF_CHARS:
        print(f"[WARN] Diff truncated to {MAX_DIFF_CHARS} chars.")

    diff_added = extract_added_lines(diff, changed_files)
    print(f"[INFO] Added lines per file: { {k: len(v) for k, v in diff_added.items()} }")

    linter_results = parse_vale_output(args.vale_output)
    linter_text    = format_linter_for_prompt(linter_results)
    linter_count   = sum(len(v) for v in linter_results.values())
    print(f"[INFO] Linter findings: {linter_count}")

    # Which linter rules fired? Used for section-based style guide delivery.
    fired_rules: set[str] = set()
    for _fp, _alerts in linter_results.items():
        for _a in _alerts:
            _r = _a.get("rule", "")
            if _r:
                fired_rules.add(_r)
    if fired_rules:
        print(f"[INFO] Rules fired: {chr(123)}{chr(39)}{chr(39).join(sorted(fired_rules))}{chr(39)}{chr(125)}")
    else:
        print("[INFO] No linter rules fired -- loading full style guide.")

    # fired_rules logged above; section filtering disabled — full guide always safer.
    # When style_guide grows past MAX_GUIDE, revisit RULE_SECTION_MAP filtering.
    style_guide = get_style_guide(mcp_status, mcp_url, mcp_key)

    print("[INFO] Reading full file contents...")
    file_contents = read_changed_files(changed_files)
    for fp, content in file_contents.items():
        chars = len(content)
        print(f"[INFO]   {fp}: {chars} chars")

    endpoint_info = f"{llm_base or 'api.openai.com'} / {llm_model}"
    print(f"[INFO] Calling LLM: {endpoint_info}")
    user_msg = build_user_message(diff_excerpt, linter_text, style_guide, changed_files, file_contents)

    try:
        result = call_llm(SYSTEM_PROMPT, user_msg, llm_key, model=llm_model, base_url=llm_base)
    except Exception as exc:
        print(f"[ERROR] LLM failed: {exc}", file=sys.stderr)
        post_summary_only(
            repo, pr_number, token,
            f"\u26a0\ufe0f **Docs Review**: LLM analysis failed (`{type(exc).__name__}: {exc}`).\n\n"
            f"**Linter** found **{linter_count}** issue(s):\n\n"
            + linter_text
        )
        sys.exit(0)

    # Validate LLM inline comments
    raw_comments  = result.get("comments", [])
    summary       = result.get("summary", "Docs Review complete.").strip()
    llm_comments  = validate_comments(raw_comments, diff_added, changed_files)
    print(f"[INFO] LLM comments after validation: {len(llm_comments)} (was {len(raw_comments)})")

    # Direct inline comments from linter (exact line numbers)
    direct_comments = linter_inline_comments(
        linter_results, diff_added, changed_files,
        limit=MAX_INLINE - len(llm_comments)
    )
    print(f"[INFO] Direct linter inline comments: {len(direct_comments)}")

    # Merge: LLM comments first, then direct, dedup by (path, line)
    used_keys = {(c["path"], c["line"]) for c in llm_comments}
    extra = [c for c in direct_comments if (c["path"], c["line"]) not in used_keys]
    all_comments = (llm_comments + extra)[:MAX_INLINE]
    print(f"[INFO] Total inline comments: {len(all_comments)}")

    # Build summary with full linter details in a collapsible section
    if linter_results:
        suffix = "s" if linter_count != 1 else ""
        summary += (
            f"\n\n---\n**Linter**: found **{linter_count}** issue{suffix}.\n\n"
            f"<details><summary>Show all findings</summary>\n\n"
            f"```\n{linter_text}\n```\n</details>"
        )

    try:
        post_review(repo, pr_number, token, all_comments, summary)
    except Exception as post_exc:
        print(f"[WARN] post_review failed ({post_exc}), retrying as summary-only...")
        try:
            post_summary_only(repo, pr_number, token, summary)
            print("[OK] Summary-only review posted as fallback.")
        except Exception as fallback_exc:
            print(f"[ERROR] Fallback also failed: {fallback_exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
