#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run Codespell on a list of files and output Vale-compatible JSON.
Usage: python run_codespell.py --files file1 file2 ... --output out.json [--ignore-words words.txt]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def run(files: list, ignore_words: str | None, output: str) -> None:
    cmd = ["codespell", "--quiet-level", "2"]

    if ignore_words and Path(ignore_words).exists():
        cmd += ["--ignore-words", ignore_words]
    elif ignore_words:
        print(f"[WARN] Codespell: ignore-words file not found: {ignore_words}", file=sys.stderr)

    cmd += files

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        print("[WARN] codespell not found — typo check skipped.", file=sys.stderr)
        Path(output).write_text("{}", encoding="utf-8")
        return

    result: dict = {}
    # Codespell default output: <file>:<line>: `word` ==> `suggestion`
    pattern = re.compile(r"^(.+?):(\d+):\s+(.+)$")

    for raw_line in proc.stdout.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        m = pattern.match(raw_line)
        if not m:
            continue

        filepath = m.group(1).replace("\\", "/")
        lineno = int(m.group(2))
        message = m.group(3).strip()

        # Normalize: strip content/ prefix
        norm = filepath
        if norm.startswith("content/"):
            norm = norm[len("content/"):]
        norm = norm.lstrip("./")

        result.setdefault(norm, []).append({
            "Line": lineno,
            "Message": message,
            "Check": "Codespell.Typo",
            "Severity": "warning",
        })

    total = sum(len(v) for v in result.values())
    Path(output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[INFO] Codespell: {total} typo(s) found.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Codespell, output Vale-compatible JSON")
    parser.add_argument("--files", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ignore-words", default=None)
    args = parser.parse_args()
    run(args.files, args.ignore_words, args.output)
