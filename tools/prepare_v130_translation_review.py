#!/usr/bin/env python3
"""Prepare a focused second-pass Gemini review workset for v1.30 translations."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
STRAY_ENGLISH = re.compile(r"(?<![A-Za-z])(if|and|but|the|you|your)(?![A-Za-z])", re.I)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translated-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with args.translated_csv.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))

    review_rows: list[dict[str, str]] = []
    reasons: dict[str, int] = {
        "talk": 0,
        "prior_polish": 0,
        "no_english": 0,
        "japanese_remaining": 0,
        "stray_english": 0,
    }
    generated_fields = {"thai", "thai_pua", "action", "model", "prompt_version"}
    for row in rows:
        row_reasons: list[str] = []
        if "talk" in row.get("scope", "").split(";"):
            row_reasons.append("talk")
        if row.get("state") == "polish":
            row_reasons.append("prior_polish")
        if not row.get("source_en", ""):
            row_reasons.append("no_english")
        if JAPANESE.search(row.get("thai", "")):
            row_reasons.append("japanese_remaining")
        plain_thai = re.sub(r"<[^>]+>", "", row.get("thai", ""))
        if STRAY_ENGLISH.search(plain_thai):
            row_reasons.append("stray_english")
        if not row_reasons:
            continue
        for reason in set(row_reasons):
            reasons[reason] += 1
        prepared = {key: value for key, value in row.items() if key not in generated_fields}
        prepared["state"] = "polish"
        prepared["existing_thai"] = row["thai"]
        prepared["first_pass_thai"] = row["thai"]
        prepared["first_pass_action"] = row["action"]
        prepared["review_reasons"] = ";".join(sorted(set(row_reasons)))
        review_rows.append(prepared)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        for row in review_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {"review_items": len(review_rows), "reason_counts": reasons}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
