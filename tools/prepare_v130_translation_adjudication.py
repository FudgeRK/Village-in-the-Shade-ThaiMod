#!/usr/bin/env python3
"""Prepare adjudication items where Gemini's second pass changed the first."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewed-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with args.reviewed_csv.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))

    generated_fields = {"thai", "thai_pua", "action", "model", "prompt_version"}
    output_rows: list[dict[str, str]] = []
    for row in rows:
        if row.get("action") != "revised":
            continue
        prepared = {key: value for key, value in row.items() if key not in generated_fields}
        prepared["state"] = "polish"
        prepared["existing_thai"] = row["thai"]
        prepared["alternative_thai"] = row.get("first_pass_thai", "")
        prepared["second_pass_thai"] = row["thai"]
        prepared["second_pass_action"] = row["action"]
        output_rows.append(prepared)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        for row in output_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"adjudication_items": len(output_rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
