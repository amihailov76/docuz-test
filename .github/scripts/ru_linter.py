#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ru_linter.py - Python linter for Russian MDX files.

Replaces Vale for Russian content: Vale existence+raw rules don't match
Cyrillic on Windows runners (Go RE2 + Unicode word boundary issues).
Reads the same YAML rules and applies them using Python re.

YAML rule files may optionally include a 'raw_hints' list (parallel to 'raw')
with suggested replacement strings shown in the linter output.

Usage:
  python ru_linter.py \\
    --files docs/ru/a.mdx docs/ru/b.mdx \\
    --output /tmp/ru.json \\
    --styles-dir ./styles/Russian
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[ERROR] pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# JSX tags (from TokenIgnores in .vale-ru.ini)
_JSX_TAG_RE = re.compile(
    r"(?i)</?(?:Accordion(?:Group)?|Card(?:Group)?|CodeGroup|Highlight|Info|"
    r"Layout|Note|Steps?|Tab(?:s)?|Tip|Warning)(?:\\s[^>]*)*/?>",
    re.IGNORECASE,
)

_FRONTMATTER_SEP = re.compile(r"^---\\s*$")
_FENCE_RE = re.compile(r"^```")


# ---------------------------------------------------------------------------
# Block-level skip helpers
# ---------------------------------------------------------------------------

def _frontmatter_range(lines):
    if not lines or not _FRONTMATTER_SEP.match(lines[0]):
        return (-1, -1)
    for i in range(1, len(lines)):
        if _FRONTMATTER_SEP.match(lines[i]):
            return (0, i)
    return (-1, -1)


def _code_block_ranges(lines):
    ranges = []
    in_block = False
    start = 0
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line.strip()):
            if not in_block:
                in_block = True
                start = i
            else:
                ranges.append((start, i))
                in_block = False
    if in_block:
        ranges.append((start, len(lines) - 1))
    return ranges


def _skip_ranges_in_line(line):
    ranges = []
    for m in re.finditer(r"`[^`]*`", line):
        ranges.append((m.start(), m.end()))
    for m in _JSX_TAG_RE.finditer(line):
        ranges.append((m.start(), m.end()))
    return ranges


def _overlaps(match_start, match_end, skip_ranges):
    return any(match_start < end and match_end > start
               for start, end in skip_ranges)


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------

def load_rules(styles_dir):
    """
    Load all YAML rule files from styles_dir.
    Supports existence rules with 'raw' patterns.
    Optional 'raw_hints' list (parallel to 'raw') provides suggested replacements.
    """
    rules = []
    for yml_file in sorted(Path(styles_dir).glob("*.yml")):
        try:
            raw_bytes = yml_file.read_bytes().replace(b"\\x00", b"")
            data = yaml.safe_load(raw_bytes.decode("utf-8"))
        except Exception as exc:
            print(f"[WARN] Could not load {yml_file}: {exc}", file=sys.stderr)
            continue

        if not data or data.get("extends") != "existence":
            continue
        raw_patterns = data.get("raw") or []
        raw_hints    = data.get("raw_hints") or []   # parallel list of replacement hints
        if not raw_patterns:
            continue

        compiled = []
        for i, pat in enumerate(raw_patterns):
            hint = raw_hints[i] if i < len(raw_hints) else ""
            try:
                compiled.append((re.compile(pat, re.IGNORECASE | re.UNICODE), hint))
            except re.error as exc:
                print(f"[WARN] {yml_file.name}: bad pattern {pat!r}: {exc}", file=sys.stderr)

        if compiled:
            rules.append({
                "name":     f"Russian.{yml_file.stem}",
                "message":  data.get("message", "Style violation: \"%s\"."),
                "severity": data.get("level", "warning"),
                "link":     data.get("link", ""),
                "patterns": compiled,   # list of (compiled_regex, hint_str)
            })

    return rules


# ---------------------------------------------------------------------------
# MCP rule loading
# ---------------------------------------------------------------------------

def fetch_rules_from_mcp(mcp_url, mcp_key, timeout=10):
    """
    Fetch YAML rule contents from MCP server's /tools/get_forbidden_words endpoint.
    Returns dict {rule_stem: yaml_content_str} or None on failure.
    """
    import urllib.request
    import urllib.error

    url = f"{mcp_url}/tools/get_forbidden_words"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {mcp_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            rules = data.get("rules", {})
            if not isinstance(rules, dict):
                raise ValueError("unexpected response shape")
            return rules
    except Exception as exc:
        print(f"[WARN] MCP fetch failed ({exc}), falling back to local rules.", file=sys.stderr)
        return None


def load_rules_from_mcp_data(rules_data):
    """
    Parse rules from MCP response dict {stem: yaml_content}.
    Identical parsing logic to load_rules(), but from in-memory strings.
    """
    rules = []
    for stem, content in sorted(rules_data.items()):
        try:
            data = yaml.safe_load(content)
        except Exception as exc:
            print(f"[WARN] Could not parse MCP rule '{stem}': {exc}", file=sys.stderr)
            continue

        if not data or data.get("extends") != "existence":
            continue
        raw_patterns = data.get("raw") or []
        raw_hints    = data.get("raw_hints") or []
        if not raw_patterns:
            continue

        compiled = []
        for i, pat in enumerate(raw_patterns):
            hint = raw_hints[i] if i < len(raw_hints) else ""
            try:
                compiled.append((re.compile(pat, re.IGNORECASE | re.UNICODE), hint))
            except re.error as exc:
                print(f"[WARN] MCP rule '{stem}': bad pattern {pat!r}: {exc}", file=sys.stderr)

        if compiled:
            rules.append({
                "name":     f"Russian.{stem}",
                "message":  data.get("message", "Style violation: \"%s\"."),
                "severity": data.get("level", "warning"),
                "link":     data.get("link", ""),
                "patterns": compiled,
            })

    return rules


# ---------------------------------------------------------------------------
# Single-file linting
# ---------------------------------------------------------------------------

def lint_file(filepath, rules):
    """Lint one MDX file, return Vale-compatible findings list."""
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except Exception as exc:
        print(f"[WARN] Cannot read {filepath}: {exc}", file=sys.stderr)
        return []

    lines = content.splitlines()
    fm_start, fm_end = _frontmatter_range(lines)
    code_ranges = _code_block_ranges(lines)

    def _in_skip_block(idx):
        if fm_start <= idx <= fm_end:
            return True
        return any(s <= idx <= e for s, e in code_ranges)

    findings = []

    for line_idx, raw_line in enumerate(lines):
        if _in_skip_block(line_idx):
            continue

        skip_ranges = _skip_ranges_in_line(raw_line)

        for rule in rules:
            for pattern, hint in rule["patterns"]:
                for m in pattern.finditer(raw_line):
                    if _overlaps(m.start(), m.end(), skip_ranges):
                        continue
                    matched_text = m.group(0)
                    msg = rule["message"].replace("%s", matched_text)
                    if hint:
                        msg += f" Replacement: \"{hint}\""
                    findings.append({
                        "Action":      {"Name": "", "Params": None},
                        "Check":       rule["name"],
                        "Description": "",
                        "Line":        line_idx + 1,
                        "Link":        rule["link"],
                        "Message":     msg,
                        "Severity":    rule["severity"],
                        "Span":        [m.start() + 1, m.end()],
                    })

    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Russian MDX linter (Vale replacement)")
    parser.add_argument("--files", nargs="+", required=True, help="MDX files to lint")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--styles-dir", default="./styles/Russian",
                        help="Path to Russian YAML rules directory")
    args = parser.parse_args()

    # Try MCP server first; fall back to local styles-dir.
    mcp_url = os.environ.get("MCP_SERVER_URL", "").strip()
    mcp_key = os.environ.get("MCP_API_KEY", "").strip()

    rules = None
    if mcp_url and mcp_key:
        print(f"[INFO] Fetching rules from MCP server: {mcp_url}")
        mcp_data = fetch_rules_from_mcp(mcp_url, mcp_key)
        if mcp_data:
            rules = load_rules_from_mcp_data(mcp_data)
            print(f"[INFO] Loaded {len(rules)} rule(s) from MCP: {[r['name'] for r in rules]}")

    if rules is None:
        print("[INFO] Using local rules from disk.")
        styles_dir = Path(args.styles_dir)
        if not styles_dir.exists():
            print(f"[ERROR] Styles dir not found: {styles_dir}", file=sys.stderr)
            sys.exit(1)
        rules = load_rules(styles_dir)
        if not rules:
            print("[WARN] No rules loaded - all files will have zero findings.", file=sys.stderr)
        else:
            print(f"[INFO] Loaded {len(rules)} rule file(s): {[r['name'] for r in rules]}")

    results = {}
    total = 0

    for filepath in args.files:
        filepath = filepath.strip()
        if not filepath:
            continue
        findings = lint_file(filepath, rules)
        if findings:
            results[filepath] = findings
            total += len(findings)
            print(f"[INFO] {filepath}: {len(findings)} warning(s)")
        else:
            print(f"[INFO] {filepath}: no warnings")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Total warnings: {total}")
    print(f"[INFO] Output written to: {args.output}")


if __name__ == "__main__":
    main()
