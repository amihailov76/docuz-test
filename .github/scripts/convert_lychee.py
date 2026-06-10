#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert Lychee JSON output to Vale-compatible format.
Usage: python convert_lychee.py <lychee_raw.json> <output.json>
"""
import json
import sys
from pathlib import Path


def convert(input_path: str, output_path: str) -> None:
    try:
        text = Path(input_path).read_text(encoding="utf-8").strip()
        if not text:
            Path(output_path).write_text("{}", encoding="utf-8")
            return
        data = json.loads(text)
    except (json.JSONDecodeError, FileNotFoundError, OSError) as exc:
        print(f"[WARN] convert_lychee: {exc}", file=sys.stderr)
        Path(output_path).write_text("{}", encoding="utf-8")
        return

    result: dict[str, list] = {}
    fail_map = data.get("fail_map") or {}

    for filepath, failures in fail_map.items():
        # Normalize: strip content/ prefix, backslashes, leading ./
        norm = filepath.replace("\\", "/")
        if norm.startswith("content/"):
            norm = norm[len("content/"):]
        norm = norm.lstrip("./")

        alerts = []
        for failure in (failures if isinstance(failures, list) else []):
            url = failure.get("url", "")
            status = failure.get("status") or {}
            code = status.get("code", "")
            status_text = status.get("text", "")
            source = failure.get("source") or {}
            line = source.get("line") or 0

            msg = f"Broken link: {url}"
            if code:
                msg += f" ({code}"
                if status_text:
                    msg += f" {status_text}"
                msg += ")"

            alerts.append({
                "Line": int(line) if line else 0,
                "Message": msg,
                "Check": "Lychee.BrokenLink",
                "Severity": "error",
            })

        if alerts:
            result[norm] = alerts

    total = sum(len(v) for v in result.values())
    Path(output_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[INFO] Lychee: {total} broken link(s) converted.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.json> <output.json>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
