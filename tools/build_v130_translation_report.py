#!/usr/bin/env python3
"""Build one deduplicated v1.30 translation-gap report from audit outputs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def aggregate(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["source_text"])].append(row)

    result: list[dict[str, object]] = []
    for source_text, occurrences in grouped.items():
        result.append(
            {
                "source_text": source_text,
                "occurrence_count": len(occurrences),
                "scopes": ";".join(sorted({str(row["scope"]) for row in occurrences})),
                "databases": ";".join(
                    sorted({str(row["database"]) for row in occurrences if row["database"]})
                ),
                "record_ids": ";".join(
                    sorted({str(row["record_id"]) for row in occurrences if row["record_id"]})
                ),
                "keys": ";".join(
                    sorted({str(row["key"]) for row in occurrences if row["key"]})
                ),
                "update_statuses": ";".join(
                    sorted(
                        {
                            str(row["update_status"])
                            for row in occurrences
                            if row["update_status"]
                        }
                    )
                ),
            }
        )
    return sorted(result, key=lambda row: str(row["source_text"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-audit", type=Path, required=True)
    parser.add_argument("--database-summary", type=Path, required=True)
    parser.add_argument("--string-changes", type=Path, required=True)
    parser.add_argument("--string-summary", type=Path, required=True)
    parser.add_argument("--talk-comparison", type=Path, required=True)
    parser.add_argument("--talk-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    database_rows = read_csv(args.database_audit)
    string_rows = read_csv(args.string_changes)
    talk_rows = read_csv(args.talk_comparison)
    database_summary = read_json(args.database_summary)
    string_summary = read_json(args.string_summary)
    talk_summary = read_json(args.talk_summary)

    normalized_database: list[dict[str, object]] = []
    for row in database_rows:
        if (
            row["database"] == "data/database/string.dat"
            or row["record_status"] != "new_record"
            or row["coverage"] != "missing"
        ):
            continue
        normalized_database.append(
            {
                "scope": "database",
                "database": row["database"],
                "record_id": row["record_id"],
                "field_index": row["field_index"],
                "key": "",
                "update_status": "new_record_text",
                "source_text": row["source_text"],
            }
        )

    # string.dat IDs shifted in v1.30, so semantic keys from the dedicated
    # comparator replace the generic record-ID result for this one database.
    exact_new_strings = [
        row
        for row in string_rows
        if row["status"] == "new" and truthy(row["needs_new_translation"])
    ]
    for row in exact_new_strings:
        normalized_database.append(
            {
                "scope": "database",
                "database": "data/database/string.dat",
                "record_id": row["id_v130"],
                "field_index": "4",
                "key": row["key"],
                "update_status": "new_semantic_key",
                "source_text": row["japanese_v130"],
            }
        )

    normalized_talk = [
        {
            "scope": "talk",
            "database": "data/database/talk.dat",
            "record_id": "",
            "field_index": row["sequence"],
            "key": row["key"],
            "update_status": row["status"],
            "source_text": row["source_text"],
        }
        for row in talk_rows
        if row["status"] != "unchanged" and row["coverage"] == "missing"
    ]
    changed_linguistic_keys = {
        row["key"]
        for row in talk_rows
        if row["status"] == "new_or_changed_text"
        and row["coverage"] != "no_translation_needed"
    }
    changed_nonlinguistic_keys = {
        row["key"]
        for row in talk_rows
        if row["status"] == "new_or_changed_text"
        and row["coverage"] == "no_translation_needed"
    }
    changed_linguistic_rows = [
        row
        for row in talk_rows
        if row["status"] == "new_or_changed_text"
        and row["coverage"] != "no_translation_needed"
    ]

    database_unique = aggregate(normalized_database)
    talk_unique = aggregate(normalized_talk)
    combined_occurrences = normalized_database + normalized_talk
    combined_unique = aggregate(combined_occurrences)

    fields = [
        "scope",
        "database",
        "record_id",
        "field_index",
        "key",
        "update_status",
        "source_text",
    ]
    unique_fields = [
        "source_text",
        "occurrence_count",
        "scopes",
        "databases",
        "record_ids",
        "keys",
        "update_statuses",
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "v130_new_translation_candidates_occurrences.csv",
        normalized_database,
        fields,
    )
    write_csv(
        args.output_dir / "v130_new_translation_candidates_unique.csv",
        database_unique,
        unique_fields,
    )
    write_csv(
        args.output_dir / "v130_all_translation_candidates_occurrences.csv",
        combined_occurrences,
        fields,
    )
    write_csv(
        args.output_dir / "v130_all_translation_candidates_unique.csv",
        combined_unique,
        unique_fields,
    )

    status_counts = string_summary["status_counts"]
    totals = database_summary["totals"]
    final_summary: dict[str, object] = {
        "string_dat": {
            "new_keys": status_counts["new"],
            "changed_keys": status_counts["changed"],
            "removed_keys": status_counts["removed"],
            "renumbered_existing_keys": string_summary["renumbered_record_count"],
            "needs_new_thai": len(exact_new_strings),
        },
        "other_mod_databases_and_string_dat": {
            "compared_databases": totals["parsed_databases"],
            "new_record_ids": totals["new_record_ids"],
            "removed_record_ids": totals["removed_record_ids"],
            "missing_occurrences": len(normalized_database),
            "missing_unique_strings": len(database_unique),
        },
        "talk_dat": {
            "new_keys": talk_summary["new_key_count"],
            "removed_keys": talk_summary["removed_key_count"],
            "existing_keys_with_new_or_changed_text": talk_summary[
                "existing_keys_with_new_or_changed_text"
            ],
            "existing_keys_with_linguistic_text_changes": len(changed_linguistic_keys),
            "existing_keys_with_only_nonlinguistic_changes": len(
                changed_nonlinguistic_keys - changed_linguistic_keys
            ),
            "delta_occurrences": talk_summary["delta_japanese_occurrences"],
            "delta_unique_strings": talk_summary["delta_unique_japanese_strings"],
            "delta_linguistic_occurrences": talk_summary[
                "delta_linguistic_japanese_occurrences"
            ],
            "delta_linguistic_unique_strings": talk_summary[
                "delta_linguistic_unique_japanese_strings"
            ],
            "delta_nonlinguistic_occurrences": talk_summary[
                "delta_nonlinguistic_occurrences"
            ],
            "missing_occurrences": len(normalized_talk),
            "missing_unique_strings": len(talk_unique),
        },
        "combined": {
            "missing_occurrences": len(combined_occurrences),
            "missing_unique_strings": len(combined_unique),
            "cross_scope_duplicate_unique_strings": len(database_unique)
            + len(talk_unique)
            - len(combined_unique),
        },
        "scope_note": (
            "Counts cover talk.dat and the 35 database files present in the v1.20 mod. "
            "They exclude assets or script containers for which no v1.20 baseline was available."
        ),
    }
    (args.output_dir / "v130_translation_gap_summary.json").write_text(
        json.dumps(final_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    per_database: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in normalized_database:
        per_database[str(row["database"])].append(row)
    new_string_lines = [
        f"- `{row['key']}` (ID {row['id_v130']}): `{row['japanese_v130']}`"
        for row in exact_new_strings
    ]
    changed_talk_lines = [
        f"- `{row['key']}`: `{row['source_text']}`"
        for row in changed_linguistic_rows
    ]
    database_lines = [
        f"| `{name.removeprefix('data/database/')}` | {len(rows)} | "
        f"{len({str(row['source_text']) for row in rows})} |"
        for name, rows in sorted(per_database.items())
    ]
    report = [
        "# รายงานข้อความ v1.30 ที่ต้องแปลเพิ่ม",
        "",
        "## สรุป",
        "",
        f"- `string.dat`: คีย์ใหม่ {status_counts['new']} รายการ, ข้อความเดิมที่เปลี่ยน 0, "
        f"คีย์ที่ถูกลบ 0 และคีย์เดิมเปลี่ยนเลข ID {string_summary['renumbered_record_count']} รายการ",
        f"- ฐานข้อมูล 35 ไฟล์: ต้องแปลใหม่ {len(database_unique)} ข้อความไม่ซ้ำ "
        f"({len(normalized_database)} จุดที่ใช้งาน)",
        f"- `talk.dat`: คีย์บทสนทนาใหม่ {talk_summary['new_key_count']} คีย์ และคีย์เดิมที่มีข้อความเพิ่ม/แก้ "
        f"{talk_summary['existing_keys_with_new_or_changed_text']} คีย์ (เปลี่ยนถ้อยคำภาษาญี่ปุ่นจริง "
        f"{len(changed_linguistic_keys)} คีย์; อีก {len(changed_nonlinguistic_keys - changed_linguistic_keys)} คีย์เป็นเครื่องหมาย/รูปแบบ); ต้องแปลใหม่ "
        f"{len(talk_unique)} ข้อความไม่ซ้ำ ({len(normalized_talk)} จุดที่ใช้งาน)",
        f"- รวมทั้งหมด: **{len(combined_unique)} ข้อความต้นทางไม่ซ้ำที่ยังไม่มีคำแปลไทย** "
        f"({len(combined_occurrences)} จุดที่ใช้งาน)",
        "",
        "## คีย์ใหม่ใน string.dat",
        "",
        *new_string_lines,
        "",
        "## ข้อความภาษาญี่ปุ่นเดิมใน talk.dat ที่แก้ถ้อยคำ",
        "",
        *changed_talk_lines,
        "",
        "## จำนวนที่ขาดแยกตามฐานข้อมูล",
        "",
        "| ฐานข้อมูล | จุดที่ใช้งาน | ข้อความไม่ซ้ำในไฟล์ |",
        "|---|---:|---:|",
        *database_lines,
        "",
        "## ขอบเขต",
        "",
        "ตัวเลขนี้เทียบ `talk.dat` และฐานข้อมูล 35 ไฟล์ที่มีต้นฉบับจาก mod v1.2 โดยนับข้อความที่ไม่มีทั้งคำแปล runtime ปัจจุบันและคำแปล v1.2 ที่นำกลับมาใช้ได้ ข้อความในคอนเทนเนอร์อื่นที่ไม่มี baseline v1.2 ไม่รวมอยู่ในยอดนี้",
        "",
    ]
    (args.output_dir / "REPORT_TH.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(final_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
