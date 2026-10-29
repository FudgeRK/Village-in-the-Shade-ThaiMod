#!/usr/bin/env python3
"""Merge Gemini translation/editor passes and apply verified glossary fixes."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from gemini_translate_v130 import index_pairs, load_mapping, replace_longest, token_counter


JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
EXACT_OVERRIDES = {
    "水分補給、忘れないでほしいと思ってさ": "ผมก็เลยอยากให้นายไม่ลืมดื่มน้ำน่ะ",
    "自分で決めればいいじゃない": "ก็เลือกเองสิ จะเป็นไรไปเล่า",
    "……さ、さて！　私は仕事に戻らないと！": "……อะ... เอาล่ะ! ฉันต้องกลับไปทำงานแล้ว!",
}
TEXT_REPLACEMENTS = {
    "チナナ": "ชินานะ",
    "・": " - ",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-pass", type=Path, required=True)
    parser.add_argument("--review-pass", type=Path, required=True)
    parser.add_argument("--adjudication-pass", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    first_rows = read_csv(args.first_pass)
    review_by_id = {row["id"]: row for row in read_csv(args.review_pass)}
    adjudication_by_id = {row["id"]: row for row in read_csv(args.adjudication_pass)}
    forward, inverse = load_mapping(args.mapping)
    forward_index = index_pairs(forward)
    inverse_index = index_pairs(inverse)

    final_rows: list[dict[str, str]] = []
    source_counts: Counter[str] = Counter()
    manual_override_count = 0
    replacement_count = 0
    errors: list[str] = []
    for row in first_rows:
        first_thai = row["thai"]
        review_thai = review_by_id.get(row["id"], {}).get("thai", "")
        adjudicated_thai = adjudication_by_id.get(row["id"], {}).get("thai", "")
        if adjudicated_thai:
            final_thai = adjudicated_thai
            final_source = "adjudication"
        elif review_thai:
            final_thai = review_thai
            final_source = "review"
        else:
            final_thai = first_thai
            final_source = "first_pass"

        source_jp = row["source_jp"]
        if source_jp in EXACT_OVERRIDES:
            final_thai = EXACT_OVERRIDES[source_jp]
            final_source = "verified_manual_override"
            manual_override_count += 1
        for old, new in TEXT_REPLACEMENTS.items():
            if old in final_thai:
                final_thai = final_thai.replace(old, new)
                final_source = "verified_glossary_fix"
                replacement_count += 1
        final_thai = re.sub(r" {2,}", " ", final_thai).strip()

        if token_counter(final_thai) != token_counter(source_jp):
            errors.append(f"{row['id']}: placeholder mismatch")
        if JAPANESE.search(final_thai):
            errors.append(f"{row['id']}: Japanese remains in {final_thai!r}")
        final_pua = replace_longest(final_thai, forward_index)
        if replace_longest(final_pua, inverse_index) != final_thai:
            errors.append(f"{row['id']}: PUA round-trip mismatch")
        source_counts[final_source] += 1
        final_rows.append(
            {
                **row,
                "first_pass_thai": first_thai,
                "review_thai": review_thai,
                "adjudicated_thai": adjudicated_thai,
                "thai": final_thai,
                "thai_pua": final_pua,
                "final_source": final_source,
            }
        )

    if errors:
        raise ValueError("final merge validation failed:\n" + "\n".join(errors[:50]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "v130_translations_final.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(final_rows[0].keys()))
        writer.writeheader()
        writer.writerows(final_rows)
    with (args.output_dir / "v130_translations_final.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as stream:
        for row in final_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "final_unique_translations": len(final_rows),
        "source_counts": dict(source_counts),
        "exact_manual_overrides": manual_override_count,
        "glossary_replacements": replacement_count,
        "placeholder_mismatches": 0,
        "japanese_remaining": 0,
        "pua_roundtrip_failures": 0,
    }
    (args.output_dir / "v130_translations_final_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
