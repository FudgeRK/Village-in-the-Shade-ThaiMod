#!/usr/bin/env python3
"""Create an English-first Gemini workset for untranslated v1.30 game text."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from audit_v130_database_texts import (
    HANGUL,
    KANA,
    ParsedDatabase,
    parse_database,
    read_database_members,
)


TALK_KEY = re.compile(r"^TALK_ID_")
JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
EVENT_MARKERS = (
    "_BIRTHDAY_",
    "_ROUTINE_",
    "_HOLIDAY_",
    "_SPECIAL_",
    "_PRESENT_",
    "_FESTIVAL_",
)


@dataclass(frozen=True)
class TalkLine:
    field_index: int
    japanese: str
    english: str


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def load_inverse_mapping(path: Path) -> list[tuple[str, str]]:
    mapping = json.loads(path.read_text(encoding="utf-8"))
    inverse: dict[str, str] = {}
    for normal, pua in mapping.items():
        inverse.setdefault(str(pua), str(normal))
    return sorted(inverse.items(), key=lambda item: len(item[0]), reverse=True)


def from_pua(text: str, inverse: list[tuple[str, str]]) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        for encoded, normal in inverse:
            if text.startswith(encoded, index):
                output.append(normal)
                index += len(encoded)
                break
        else:
            output.append(text[index])
            index += 1
    return "".join(output)


def extract_talk_lines(database: ParsedDatabase) -> dict[str, list[TalkLine]]:
    result: dict[str, list[TalkLine]] = {}
    for record in database.records:
        ordered = sorted(record.refs.items())
        keys = [text for _index, text in ordered if TALK_KEY.match(text)]
        if not keys:
            continue
        key = keys[0]
        refs = {
            index: text
            for index, text in ordered
            if text != key and not TALK_KEY.match(text)
        }
        handled: set[int] = set()
        lines: list[TalkLine] = []
        for field_index in sorted(refs):
            language_fields = [field_index + step * 2 for step in range(7)]
            if field_index in handled or not all(item in refs for item in language_fields):
                continue
            lines.append(TalkLine(field_index, refs[field_index], refs[field_index + 2]))
            handled.update(language_fields)
        for field_index in sorted(refs):
            text = refs[field_index]
            if field_index in handled or not KANA.search(text) or HANGUL.search(text):
                continue
            lines.append(TalkLine(field_index, text, refs.get(field_index + 2, "")))
            handled.add(field_index)
            if field_index + 2 in refs:
                handled.add(field_index + 2)
        for field_index in sorted(refs):
            text = refs[field_index]
            if field_index not in handled and KANA.search(text) and not HANGUL.search(text):
                lines.append(TalkLine(field_index, text, ""))
        result.setdefault(key, []).extend(sorted(lines, key=lambda line: line.field_index))
    return result


def talk_group(key: str) -> str:
    for marker in EVENT_MARKERS:
        if marker in key:
            return key.split(marker, 1)[0].removeprefix("TALK_ID_")
    return "STORY"


def concise_talk_context(lines: list[TalkLine], sequence: int) -> str:
    start = max(0, sequence - 3)
    end = min(len(lines), sequence + 2)
    context = []
    for index in range(start, end):
        text = lines[index].english or lines[index].japanese
        context.append(f"{index + 1}: {text}")
    return "\n".join(context)


def add_occurrence(
    grouped: dict[str, list[dict[str, str]]],
    *,
    source_jp: str,
    source_en: str,
    scope: str,
    group: str,
    key: str,
    location: str,
    context_en: str,
    state: str,
    existing_thai: str,
) -> None:
    if not source_jp.strip():
        return
    grouped[source_jp].append(
        {
            "source_en": source_en,
            "scope": scope,
            "group": group,
            "key": key,
            "location": location,
            "context_en": context_en,
            "state": state,
            "existing_thai": existing_thai,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--database-audit", type=Path, required=True)
    parser.add_argument("--string-changes", type=Path, required=True)
    parser.add_argument("--talk-comparison", type=Path, required=True)
    parser.add_argument("--v120-talk-csv", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    members = read_database_members(args.archive)
    parsed = {
        name: database
        for name, payload in members.items()
        if (database := parse_database(name, payload)) is not None
    }
    talk_database = parsed.get("data/database/talk.dat")
    if talk_database is None:
        raise ValueError("data/database/talk.dat could not be parsed")
    talk_lines = extract_talk_lines(talk_database)
    inverse = load_inverse_mapping(args.mapping)

    database_audit = read_csv(args.database_audit)
    string_changes = read_csv(args.string_changes)
    talk_comparison = read_csv(args.talk_comparison)
    old_talk_rows = read_csv(args.v120_talk_csv)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)

    record_maps = {
        name: {record.record_id: record for record in database.records}
        for name, database in parsed.items()
    }

    # Translate every uncovered Japanese field in the v1.30 databases. The
    # semantic string.dat comparator replaces its ID-shifted generic rows below.
    for row in database_audit:
        if row["coverage"] != "missing" or row["database"] == "data/database/string.dat":
            continue
        database_name = row["database"]
        record_id = int(row["record_id"])
        field_index = int(row["field_index"])
        record = record_maps[database_name][record_id]
        source_jp = row["source_text"]
        source_en = record.refs.get(field_index + 2, "")
        key = record.refs.get(2, "")
        add_occurrence(
            grouped,
            source_jp=source_jp,
            source_en=source_en,
            scope="database",
            group=Path(database_name).stem,
            key=key,
            location=f"{database_name}:{record_id}:{field_index}",
            context_en=f"Database {Path(database_name).name}; key {key}; record {record_id}",
            state="missing",
            existing_thai="",
        )

    string_records = record_maps["data/database/string.dat"]
    for row in string_changes:
        if row["coverage"] != "missing" or not truthy(row["needs_new_translation"]):
            continue
        record_id = int(row["id_v130"])
        record = string_records[record_id]
        add_occurrence(
            grouped,
            source_jp=row["japanese_v130"],
            source_en=record.refs.get(6, ""),
            scope="database",
            group="string",
            key=row["key"],
            location=f"data/database/string.dat:{record_id}:4",
            context_en=f"System string; key {row['key']}; ID {record_id}",
            state="missing",
            existing_thai="",
        )

    for row in talk_comparison:
        if row["status"] == "unchanged" or row["coverage"] == "no_translation_needed":
            continue
        key = row["key"]
        sequence = int(row["sequence"])
        lines = talk_lines[key]
        if sequence < 1 or sequence > len(lines):
            raise ValueError(f"talk sequence out of range: {key} #{sequence}")
        line = lines[sequence - 1]
        if line.japanese != row["source_text"]:
            raise ValueError(
                f"talk sequence mismatch: {key} #{sequence}: "
                f"{line.japanese!r} != {row['source_text']!r}"
            )
        if row["coverage"] == "missing":
            state = "missing"
            existing_thai = ""
        else:
            state = "polish"
            encoded = row["runtime_translation"] or row["v120_reusable_translation"]
            existing_thai = from_pua(encoded, inverse)
        add_occurrence(
            grouped,
            source_jp=line.japanese,
            source_en=line.english,
            scope="talk",
            group=talk_group(key),
            key=key,
            location=f"data/database/talk.dat:{key}:{sequence}",
            context_en=concise_talk_context(lines, sequence),
            state=state,
            existing_thai=existing_thai,
        )

    # Also review translations reused by newly added database records.
    for row in database_audit:
        if (
            row["record_status"] != "new_record"
            or row["coverage"] not in {"translation.txt", "v1.20_database_translation_available"}
            or not JAPANESE.search(row["source_text"])
        ):
            continue
        database_name = row["database"]
        record_id = int(row["record_id"])
        field_index = int(row["field_index"])
        record = record_maps[database_name][record_id]
        encoded = row["runtime_translation"] or row["v120_database_translation"]
        add_occurrence(
            grouped,
            source_jp=row["source_text"],
            source_en=record.refs.get(field_index + 2, ""),
            scope="database",
            group=Path(database_name).stem,
            key=record.refs.get(2, ""),
            location=f"{database_name}:{record_id}:{field_index}",
            context_en=f"Database {Path(database_name).name}; record {record_id}",
            state="polish",
            existing_thai=from_pua(encoded, inverse),
        )

    output_rows: list[dict[str, object]] = []
    missing_count = 0
    polish_count = 0
    english_missing = 0
    conflicting_english = 0
    for source_jp, occurrences in grouped.items():
        states = {item["state"] for item in occurrences}
        state = "missing" if "missing" in states else "polish"
        english_values = list(dict.fromkeys(item["source_en"] for item in occurrences if item["source_en"]))
        existing_values = list(
            dict.fromkeys(item["existing_thai"] for item in occurrences if item["existing_thai"])
        )
        context_values = list(dict.fromkeys(item["context_en"] for item in occurrences if item["context_en"]))
        keys = sorted({item["key"] for item in occurrences if item["key"]})
        groups = sorted({item["group"] for item in occurrences if item["group"]})
        locations = sorted({item["location"] for item in occurrences})
        if state == "missing":
            missing_count += 1
        else:
            polish_count += 1
        if not english_values:
            english_missing += 1
        if len(english_values) > 1:
            conflicting_english += 1
        stable_id = "tr-" + hashlib.sha1(source_jp.encode("utf-8")).hexdigest()[:12]
        output_rows.append(
            {
                "id": stable_id,
                "state": state,
                "scope": ";".join(sorted({item["scope"] for item in occurrences})),
                "group": ";".join(groups),
                "keys": ";".join(keys),
                "source_en": english_values[0] if english_values else "",
                "english_variants": " || ".join(english_values),
                "source_jp": source_jp,
                "existing_thai": existing_values[0] if existing_values else "",
                "existing_thai_variants": " || ".join(existing_values),
                "context_en": "\n---\n".join(context_values[:4]),
                "locations": ";".join(locations),
                "occurrence_count": len(occurrences),
            }
        )

    # Python's sort is stable, so dialogue fragments retain their original
    # record/sequence order within each group instead of being shuffled by hash.
    output_rows.sort(key=lambda row: (str(row["group"]), str(row["keys"])))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = list(output_rows[0].keys()) if output_rows else []
    with (args.output_dir / "v130_gemini_workset.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
    with (args.output_dir / "v130_gemini_workset.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as stream:
        for row in output_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "total_unique_work_items": len(output_rows),
        "missing_unique": missing_count,
        "polish_unique": polish_count,
        "without_english_source": english_missing,
        "with_multiple_english_variants": conflicting_english,
        "total_occurrences": sum(int(row["occurrence_count"]) for row in output_rows),
    }
    (args.output_dir / "v130_gemini_workset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    wanted_groups = {
        group
        for row in output_rows
        for group in str(row["group"]).split(";")
        if group and group != "STORY"
    }
    style_examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen_examples: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in old_talk_rows:
        key = row.get("key", "")
        group = talk_group(key)
        if group not in wanted_groups or len(style_examples[group]) >= 10:
            continue
        english = row.get("text_en", "").strip()
        encoded_thai = row.get("text_th_pua", "").strip()
        if not english or not encoded_thai or len(english) < 8 or len(english) > 180:
            continue
        thai = from_pua(encoded_thai, inverse)
        pair = (english, thai)
        if pair in seen_examples[group]:
            continue
        seen_examples[group].add(pair)
        style_examples[group].append({"english": english, "thai": thai, "key": key})
    (args.output_dir / "v130_style_examples.json").write_text(
        json.dumps(style_examples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
