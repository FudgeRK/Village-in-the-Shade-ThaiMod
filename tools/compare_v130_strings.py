#!/usr/bin/env python3
"""Compare the installed v1.30 string database with the v1.20 Thai sources."""

from __future__ import annotations

import argparse
import csv
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path


ARCHIVE_HEADER = struct.Struct("<8sIIQQQQ")
TOC_ENTRY = struct.Struct("<QQQQQQ")


@dataclass(frozen=True)
class StringRecord:
    record_id: int
    key: str
    japanese: str


def read_c_string(data: bytes, offset: int) -> str:
    end = data.find(b"\0", offset)
    if end < 0:
        end = len(data)
    return data[offset:end].decode("utf-8")


def read_archive_member(archive_path: Path, wanted_name: str) -> bytes:
    with archive_path.open("rb") as stream:
        header = stream.read(ARCHIVE_HEADER.size)
        if len(header) != ARCHIVE_HEADER.size:
            raise ValueError("archive header is truncated")

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
            if name == wanted_name:
                stream.seek(offset)
                payload = stream.read(size)
                if len(payload) != size:
                    raise ValueError(f"{wanted_name} is truncated")
                return payload

    raise KeyError(f"archive member not found: {wanted_name}")


def decode_text_ref(text_pool: bytes, offset: int, length: int) -> str:
    if offset < 0 or length < 0 or offset + length > len(text_pool):
        raise ValueError(f"invalid text reference: offset={offset}, length={length}")
    return text_pool[offset : offset + length].decode("utf-8")


def parse_string_database(payload: bytes) -> list[StringRecord]:
    if len(payload) < 16:
        raise ValueError("string.dat is too small")

    record_count, record_data_size, text_size = struct.unpack_from("<3I", payload, 0)
    entry_size = struct.unpack_from("<I", payload, 12)[0]
    if entry_size == 0 or entry_size % 4 != 0:
        raise ValueError(f"invalid entry size: {entry_size}")
    if record_data_size != record_count * entry_size:
        raise ValueError("record-data size does not match record count and entry size")

    stride = entry_size + 4
    text_base = 12 + record_count * stride
    if text_base + text_size != len(payload):
        raise ValueError(
            f"database length mismatch: expected {text_base + text_size}, got {len(payload)}"
        )
    text_pool = payload[text_base:]

    records: list[StringRecord] = []
    word_count = entry_size // 4
    if word_count < 6:
        raise ValueError("string.dat records do not contain the expected text slots")

    for index in range(record_count):
        record_offset = 12 + index * stride
        stored_size = struct.unpack_from("<I", payload, record_offset)[0]
        if stored_size != entry_size:
            raise ValueError(f"record {index} has unexpected size {stored_size}")
        words = struct.unpack_from(f"<{word_count}I", payload, record_offset + 4)
        record_id = words[0]
        key = decode_text_ref(text_pool, words[2], words[3])
        japanese = decode_text_ref(text_pool, words[4], words[5])
        records.append(StringRecord(record_id, key, japanese))

    ids = [record.record_id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("string.dat contains duplicate record IDs")
    return records


def load_v120_csv(path: Path) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            record_id = int(row["ID"])
            result[record_id] = {
                "key": row.get("Key", ""),
                "japanese": row.get("ต้นฉบับ_JP", ""),
                "thai": row.get("คำแปลไทย", ""),
                "thai_pua": row.get("Thai_PUA", ""),
            }
    return result


def unescape_like_mod(value: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            escaped = value[index + 1]
            if escaped == "n":
                output.append("\n")
                index += 2
                continue
            if escaped == "t":
                output.append("\t")
                index += 2
                continue
            if escaped == "\\":
                output.append("\\")
                index += 2
                continue
        output.append(value[index])
        index += 1
    return "".join(output)


def load_runtime_translations(primary_path: Path) -> dict[str, str]:
    paths = [primary_path]
    modular_dir = primary_path.parent / "translations"
    if modular_dir.is_dir():
        paths.extend(sorted(modular_dir.glob("*.txt")))

    result: dict[str, str] = {}
    scale_tag = re.compile(r"\[SCALE:[^\]]+\]")
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for raw_line in stream:
                if not raw_line or raw_line[0] in "\r\n":
                    continue
                stripped = raw_line.lstrip(" \t")
                if stripped.startswith(("#", ";", "//")) or "=" not in raw_line:
                    continue
                source, translated = raw_line.rstrip("\r\n").split("=", 1)
                source = scale_tag.sub("", unescape_like_mod(source))
                translated = unescape_like_mod(translated)
                if source and translated:
                    result[source] = translated
    return result


def has_thai_source(row: dict[str, str] | None) -> bool:
    return bool(row and (row.get("thai_pua", "").strip() or row.get("thai", "").strip()))


def compare_records(
    current_records: list[StringRecord],
    old_by_id: dict[int, dict[str, str]],
    runtime_translations: dict[str, str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    old_by_key: dict[str, tuple[int, dict[str, str]]] = {}
    old_thai_by_japanese: dict[str, str] = {}
    for old_id, row in old_by_id.items():
        key = row["key"]
        if key in old_by_key:
            raise ValueError(f"v1.20 CSV contains a duplicate key: {key}")
        old_by_key[key] = (old_id, row)
        japanese = row["japanese"]
        thai = row["thai_pua"].strip() or row["thai"].strip()
        if japanese and thai:
            old_thai_by_japanese.setdefault(japanese, thai)

    current_by_key = {record.key: record for record in current_records}
    if len(current_by_key) != len(current_records):
        raise ValueError("v1.30 string.dat contains duplicate keys")

    rows: list[dict[str, object]] = []
    status_counts = {"new": 0, "changed": 0, "unchanged": 0, "removed": 0}
    renumbered_count = 0
    update_needs_new_translation = 0
    update_needs_migration = 0
    update_runtime_covered = 0

    for record in current_records:
        old_match = old_by_key.get(record.key)
        old_id = old_match[0] if old_match else None
        old = old_match[1] if old_match else None
        if old is None:
            status = "new"
        elif old["japanese"] != record.japanese:
            status = "changed"
        else:
            status = "unchanged"
        status_counts[status] += 1
        renumbered = old_id is not None and old_id != record.record_id
        if renumbered:
            renumbered_count += 1

        runtime_translation = runtime_translations.get(record.japanese, "")
        old_translation = ""
        if old and old["japanese"] == record.japanese and has_thai_source(old):
            old_translation = old["thai_pua"].strip() or old["thai"].strip()
        elif record.japanese in old_thai_by_japanese:
            old_translation = old_thai_by_japanese[record.japanese]

        has_meaningful_source = bool(record.japanese.strip())
        if not has_meaningful_source:
            coverage = "no_source_text"
            needs_new_translation = False
        elif runtime_translation:
            coverage = "translation.txt"
            needs_new_translation = False
        elif old_translation:
            coverage = "v1.20_translation_available"
            needs_new_translation = False
        else:
            coverage = "missing"
            needs_new_translation = True

        if status in {"new", "changed"}:
            if runtime_translation:
                update_runtime_covered += 1
            elif old_translation:
                update_needs_migration += 1
            elif has_meaningful_source:
                update_needs_new_translation += 1

        rows.append(
            {
                "status": status,
                "id_v120": old_id if old_id is not None else "",
                "id_v130": record.record_id,
                "id_changed": renumbered,
                "key": record.key,
                "japanese_v120": old["japanese"] if old else "",
                "japanese_v130": record.japanese,
                "coverage": coverage,
                "runtime_translation": runtime_translation,
                "v120_translation": old_translation,
                "needs_new_translation": needs_new_translation,
            }
        )

    for old_id, old in old_by_id.items():
        if old["key"] in current_by_key:
            continue
        status_counts["removed"] += 1
        rows.append(
            {
                "status": "removed",
                "id_v120": old_id,
                "id_v130": "",
                "id_changed": False,
                "key": old["key"],
                "japanese_v120": old["japanese"],
                "japanese_v130": "",
                "coverage": "not_in_v130",
                "runtime_translation": "",
                "v120_translation": old["thai_pua"].strip() or old["thai"].strip(),
                "needs_new_translation": False,
            }
        )

    nonempty_current = [record for record in current_records if record.japanese.strip()]
    runtime_covered_all = sum(
        1 for record in nonempty_current if record.japanese in runtime_translations
    )
    old_available_all = sum(
        1
        for row in rows
        if row["status"] != "removed"
        and str(row["japanese_v130"]).strip()
        and row["coverage"] == "v1.20_translation_available"
    )
    missing_all = sum(
        1
        for row in rows
        if row["status"] != "removed"
        and str(row["japanese_v130"]).strip()
        and row["coverage"] == "missing"
    )

    summary: dict[str, object] = {
        "v120_record_count": len(old_by_id),
        "v130_record_count": len(current_records),
        "status_counts": status_counts,
        "renumbered_record_count": renumbered_count,
        "updated_record_count": status_counts["new"] + status_counts["changed"],
        "updated_runtime_covered": update_runtime_covered,
        "updated_translation_available_but_needs_migration": update_needs_migration,
        "updated_needs_new_translation": update_needs_new_translation,
        "v130_nonempty_japanese_records": len(nonempty_current),
        "v130_runtime_covered": runtime_covered_all,
        "v130_translation_available_but_needs_migration": old_available_all,
        "v130_missing_any_thai_source": missing_all,
    }
    return rows, summary


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, summary: dict[str, object], rows: list[dict[str, object]]) -> None:
    changed_rows = [row for row in rows if row["status"] in {"new", "changed"}]
    lines = [
        "# Village in the Shade v1.30 string.dat comparison",
        "",
        f"- v1.20 records: {summary['v120_record_count']}",
        f"- v1.30 records: {summary['v130_record_count']}",
        f"- New records: {summary['status_counts']['new']}",
        f"- Changed records: {summary['status_counts']['changed']}",
        f"- Removed records: {summary['status_counts']['removed']}",
        f"- Existing records with a changed numeric ID: {summary['renumbered_record_count']}",
        f"- Updated records already covered at runtime: {summary['updated_runtime_covered']}",
        "- Updated records with an existing v1.20 Thai translation that only needs migration: "
        f"{summary['updated_translation_available_but_needs_migration']}",
        f"- Updated records requiring a new Thai translation: {summary['updated_needs_new_translation']}",
        "",
        "## New or changed records",
        "",
        "| Status | ID | Key | Japanese v1.30 | Coverage |",
        "|---|---:|---|---|---|",
    ]
    for row in changed_rows:
        escaped = {
            key: str(value).replace("|", "\\|").replace("\n", "<br>")
            for key, value in row.items()
        }
        lines.append(
            f"| {escaped['status']} | {escaped['id_v130']} | {escaped['key']} | "
            f"{escaped['japanese_v130']} | {escaped['coverage']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--v120-csv", type=Path, required=True)
    parser.add_argument("--translation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    current_payload = read_archive_member(args.archive, "data/database/string.dat")
    current_records = parse_string_database(current_payload)
    old_by_id = load_v120_csv(args.v120_csv)
    runtime_translations = load_runtime_translations(args.translation)
    rows, summary = compare_records(current_records, old_by_id, runtime_translations)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "v130_string_changes.csv", rows)
    (args.output_dir / "v130_string_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(args.output_dir / "v130_string_report.md", summary, rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
