#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert Lychee JSON output to Vale-compatible format.
Handles both fail_map (HTTP errors) and error_map (network/DNS errors).
Usage: python convert_lychee.py <lychee_raw.json> <output.json>
"""
import json
import sys
from pathlib import Path


def _normalize_path(filepath: str) -> str:
    norm = filepath.replace("\\", "/")
    if norm.startswith("content/"):
        norm = norm[len("content/"):]
    norm = norm.lstrip("./")
    return norm


def _extract_alerts(failures, use_span: bool) -> list:
    alerts = []
    for failure in (failures if isinstance(failures, list) else []):
        url = failure.get("url", "")
        status = failure.get("status") or {}

        # fail_map: status has 'code' + 'text'; error_map: status has 'text' + 'details'
        code = status.get("code", "")
        status_text = status.get("text", "") or status.get("details", "")

        # Location: error_map uses 'span', fail_map uses 'source'
        if use_span:
            loc = failure.get("span") or {}
        else:
            loc = failure.get("source") or {}
        line = loc.get("line") or 0

        msg = f"Broken link: {url}"
        if code:
            msg += f" ({code}"
            if status_text:
                msg += f" {status_text}"
            msg += ")"
        elif status_text:
            # Trim verbose network error messages to first sentence
            short = status_text.split("(error sending")[0].strip().rstrip(".")
            if short:
                msg += f" ({short})"

        alerts.append({
            "Line": int(line) if line else 0,
            "Message": msg,
            "Check": "Lychee.BrokenLink",
            "Severity": "error",
        })
    return alerts


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

    for filepath, failures in (data.get("fail_map") or {}).items():
        norm = _normalize_path(filepath)
        alerts = _extract_alerts(failures, use_span=False)
        if alerts:
            result.setdefault(norm, []).extend(alerts)

    for filepath, failures in (data.get("error_map") or {}).items():
        norm = _normalize_path(filepath)
        alerts = _extract_alerts(failures, use_span=True)
        if alerts:
            result.setdefault(norm, []).extend(alerts)

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
