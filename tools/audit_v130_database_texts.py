#!/usr/bin/env python3
"""Audit v1.30 database text fields against the v1.20 mod and runtime dictionary."""

from __future__ import annotations

import argparse
import csv
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from compare_v130_strings import load_runtime_translations


ARCHIVE_HEADER = struct.Struct("<8sIIQQQQ")
TOC_ENTRY = struct.Struct("<QQQQQQ")
KANA = re.compile(r"[\u3040-\u30ff]")
HANGUL = re.compile(r"[\uac00-\ud7af]")
THAI_OR_PUA = re.compile(r"[\u0e00-\u0e7f\ue000-\uf8ff]")
IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]+$")


@dataclass
class DatabaseRecord:
    record_id: int
    words: tuple[int, ...]
    refs: dict[int, str]


@dataclass
class ParsedDatabase:
    name: str
    records: list[DatabaseRecord]


def read_c_string(data: bytes, offset: int) -> str:
    end = data.find(b"\0", offset)
    if end < 0:
        end = len(data)
    return data[offset:end].decode("utf-8")


def read_database_members(archive_path: Path) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    with archive_path.open("rb") as stream:
        header = stream.read(ARCHIVE_HEADER.size)
        magic, count, _unknown, string_offset, string_size, toc_offset, _padding = (
            ARCHIVE_HEADER.unpack(header)
        )
        if magic != b"FAFULLFS":
            raise ValueError(f"unexpected archive magic: {magic!r}")
        stream.seek(toc_offset)
        entries = [TOC_ENTRY.unpack(stream.read(TOC_ENTRY.size)) for _ in range(count)]
        stream.seek(string_offset)
        string_table = stream.read(string_size)
        for _hash, name_offset, _unknown1, size, offset, _unknown2 in entries:
            if name_offset >= len(string_table):
                continue
            name = read_c_string(string_table, int(name_offset))
            if not (name.startswith("data/database/") and name.endswith(".dat")):
                continue
            stream.seek(offset)
            payload = stream.read(size)
            if len(payload) != size:
                raise ValueError(f"archive member is truncated: {name}")
            members[name] = payload
    return members


def split_text_pool(text_pool: bytes) -> dict[tuple[int, int], str]:
    result: dict[tuple[int, int], str] = {}
    offset = 0
    while offset < len(text_pool):
        end = text_pool.find(b"\0", offset)
        if end < 0:
            end = len(text_pool)
        raw = text_pool[offset:end]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        if raw and text:
            result[(offset, len(raw))] = text
        offset = end + 1
    return result


def parse_database(name: str, payload: bytes) -> ParsedDatabase | None:
    if len(payload) < 12:
        return None
    record_count, record_data_size, text_size = struct.unpack_from("<3I", payload, 0)
    text_base = 12 + record_count * 4 + record_data_size
    if text_base + text_size != len(payload):
        return None
    segments = split_text_pool(payload[text_base:])
    records: list[DatabaseRecord] = []
    offset = 12
    for record_index in range(record_count):
        if offset + 4 > text_base:
            return None
        stored_size = struct.unpack_from("<I", payload, offset)[0]
        if not stored_size or stored_size % 4 or offset + 4 + stored_size > text_base:
            return None
        word_count = stored_size // 4
        words = struct.unpack_from(f"<{word_count}I", payload, offset + 4)
        refs: dict[int, str] = {}
        for word_index in range(1, word_count - 1):
            text = segments.get((words[word_index], words[word_index + 1]))
            if text is not None:
                refs[word_index] = text
        records.append(DatabaseRecord(words[0], words, refs))
        offset += 4 + stored_size
    if offset != text_base:
        return None
    return ParsedDatabase(name, records)


def infer_record_japanese_fields(
    database_name: str,
    record: DatabaseRecord,
    translated_record: DatabaseRecord | None,
) -> list[int]:
    if database_name.endswith("/string.dat"):
        return [4] if 4 in record.refs else []

    selected: set[int] = set()
    handled: set[int] = set()

    # Retail records commonly store seven adjacent offset/length pairs in this
    # order: JP, EN, FR, ES, zh-TW, KO, zh-CN. The first item in each complete
    # run is therefore the Japanese slot, even when its text is pure kanji.
    for field_index in sorted(record.refs):
        if IDENTIFIER.fullmatch(record.refs[field_index]):
            continue
        language_fields = [field_index + step * 2 for step in range(7)]
        if field_index in handled or not all(item in record.refs for item in language_fields):
            continue
        selected.add(field_index)
        handled.update(language_fields)

    # For records that existed in v1.20, a Thai/PUA value at the same index in
    # the translated database is direct evidence that the field is Japanese.
    if translated_record is not None:
        selected.update(
            field_index
            for field_index, text in translated_record.refs.items()
            if text_is_translated_candidate(text) and field_index in record.refs
        )

    # Some debug/Japanese-only fields have no seven-language run. Kana is a
    # safe fallback; pure CJK text is intentionally not guessed here.
    selected.update(
        field_index
        for field_index, text in record.refs.items()
        if KANA.search(text) and not HANGUL.search(text)
    )
    return sorted(selected)


def text_is_translated_candidate(text: str) -> bool:
    return bool(text.strip() and THAI_OR_PUA.search(text))


def audit(
    current_members: dict[str, bytes],
    mod_database_dir: Path,
    runtime_translations: dict[str, str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    rows: list[dict[str, object]] = []
    database_summaries: list[dict[str, object]] = []

    comparable: list[tuple[str, ParsedDatabase, ParsedDatabase]] = []

    for name in sorted(current_members):
        current = parse_database(name, current_members[name])
        if current is None:
            continue
        mod_path = mod_database_dir / Path(name).name
        if not mod_path.is_file():
            continue
        old = parse_database(name, mod_path.read_bytes())
        if old is None:
            continue
        comparable.append((name, current, old))

    # Recover a global v1.20 Japanese -> Thai map from records that still align
    # by ID and field. New v1.30 records can then reuse translations for common
    # strings such as "use" instead of being counted as brand-new work.
    reusable_v120: dict[str, str] = {}
    for name, current, old in comparable:
        if name.endswith("/string.dat"):
            continue
        old_by_id = {record.record_id: record for record in old.records}
        for record in current.records:
            old_record = old_by_id.get(record.record_id)
            if old_record is None:
                continue
            for field_index, translated in old_record.refs.items():
                source = record.refs.get(field_index, "")
                if source and text_is_translated_candidate(translated):
                    reusable_v120.setdefault(source, translated)

    for name, current, old in comparable:
        old_by_id = {record.record_id: record for record in old.records}
        current_ids = {record.record_id for record in current.records}
        old_ids = set(old_by_id)
        new_ids = current_ids - old_ids
        removed_ids = old_ids - current_ids
        japanese_fields: set[int] = set()

        per_database_sources: set[str] = set()
        per_database_missing: set[str] = set()
        per_database_new_missing: set[str] = set()

        for record in current.records:
            record_status = "new_record" if record.record_id in new_ids else "existing_record"
            old_record = old_by_id.get(record.record_id)
            record_japanese_fields = infer_record_japanese_fields(name, record, old_record)
            japanese_fields.update(record_japanese_fields)
            for field_index in record_japanese_fields:
                source = record.refs.get(field_index, "")
                if not source.strip():
                    continue
                per_database_sources.add(source)
                runtime_translation = runtime_translations.get(source, "")
                old_candidate = ""
                if old_record:
                    candidate = old_record.refs.get(field_index, "")
                    if text_is_translated_candidate(candidate):
                        old_candidate = candidate
                if not old_candidate:
                    old_candidate = reusable_v120.get(source, "")

                if runtime_translation:
                    coverage = "translation.txt"
                elif old_candidate:
                    coverage = "v1.20_database_translation_available"
                else:
                    coverage = "missing"
                    per_database_missing.add(source)
                    if record_status == "new_record":
                        per_database_new_missing.add(source)

                rows.append(
                    {
                        "database": name,
                        "record_id": record.record_id,
                        "record_status": record_status,
                        "field_index": field_index,
                        "source_text": source,
                        "coverage": coverage,
                        "runtime_translation": runtime_translation,
                        "v120_database_translation": old_candidate,
                    }
                )

        database_summaries.append(
            {
                "database": name,
                "v120_records": len(old.records),
                "v130_records": len(current.records),
                "new_record_ids": len(new_ids),
                "removed_record_ids": len(removed_ids),
                "inferred_japanese_fields": sorted(japanese_fields),
                "unique_source_strings": len(per_database_sources),
                "unique_missing_strings": len(per_database_missing),
                "unique_missing_strings_in_new_records": len(per_database_new_missing),
            }
        )

    unique_sources = {str(row["source_text"]) for row in rows}
    unique_missing = {
        str(row["source_text"]) for row in rows if row["coverage"] == "missing"
    }
    unique_new_missing = {
        str(row["source_text"])
        for row in rows
        if row["coverage"] == "missing" and row["record_status"] == "new_record"
    }
    summary: dict[str, object] = {
        "databases": database_summaries,
        "totals": {
            "parsed_databases": len(database_summaries),
            "net_new_records": sum(
                int(item["v130_records"]) - int(item["v120_records"])
                for item in database_summaries
            ),
            "new_record_ids": sum(int(item["new_record_ids"]) for item in database_summaries),
            "removed_record_ids": sum(
                int(item["removed_record_ids"]) for item in database_summaries
            ),
            "unique_japanese_field_strings": len(unique_sources),
            "unique_missing_strings": len(unique_missing),
            "unique_missing_strings_in_new_records": len(unique_new_missing),
        },
        "method_limitations": [
            "Japanese text fields are inferred from fields that contain kana in at least 5% of non-empty records.",
            "Pure-kanji-only fields without any kana may be omitted.",
            "Record-ID shifts can make a moved record look new outside string.dat.",
            "Runtime templates may translate some strings without an exact translation.txt key.",
        ],
    }
    return rows, summary


def write_outputs(output_dir: Path, rows: list[dict[str, object]], summary: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "v130_database_text_audit.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "v130_database_text_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--mod-database-dir", type=Path, required=True)
    parser.add_argument("--translation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    members = read_database_members(args.archive)
    runtime_translations = load_runtime_translations(args.translation)
    rows, summary = audit(members, args.mod_database_dir, runtime_translations)
    write_outputs(args.output_dir, rows, summary)
    print(json.dumps(summary["totals"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
