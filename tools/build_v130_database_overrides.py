#!/usr/bin/env python3
"""Build shape-compatible v1.30 Thai database overrides from the retail archive."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
from collections import Counter, defaultdict, deque
from pathlib import Path

from audit_v130_database_texts import (
    DatabaseRecord,
    ParsedDatabase,
    infer_record_japanese_fields,
    parse_database,
    read_database_members,
    text_is_translated_candidate,
)
from build_v130_gemini_workset import extract_talk_lines
from compare_v130_strings import load_runtime_translations


JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
HEADER = struct.Struct("<3I")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def serialize_with_replacements(
    payload: bytes,
    database: ParsedDatabase,
    replacements: dict[tuple[int, int], str],
) -> bytes:
    record_count, record_data_size, text_size = HEADER.unpack_from(payload, 0)
    text_base = 12 + record_count * 4 + record_data_size
    if text_base + text_size != len(payload):
        raise ValueError(f"invalid database layout: {database.name}")
    text_pool = bytearray(payload[text_base:])
    appended: dict[bytes, tuple[int, int]] = {}
    record_bytes = bytearray()

    for record in database.records:
        words = list(record.words)
        for field_index in sorted(record.refs):
            translated = replacements.get((record.record_id, field_index))
            if translated is None:
                continue
            encoded = translated.encode("utf-8")
            if b"\0" in encoded:
                raise ValueError(
                    f"translation contains NUL: {database.name}:{record.record_id}:{field_index}"
                )
            if encoded not in appended:
                appended[encoded] = (len(text_pool), len(encoded))
                text_pool.extend(encoded)
                text_pool.append(0)
            offset, length = appended[encoded]
            words[field_index] = offset
            words[field_index + 1] = length
        stored_size = len(words) * 4
        record_bytes.extend(struct.pack("<I", stored_size))
        record_bytes.extend(struct.pack(f"<{len(words)}I", *words))

    expected_record_bytes = record_count * 4 + record_data_size
    if len(record_bytes) != expected_record_bytes:
        raise ValueError(
            f"record-data size changed for {database.name}: "
            f"{len(record_bytes)} != {expected_record_bytes}"
        )
    return HEADER.pack(record_count, record_data_size, len(text_pool)) + record_bytes + text_pool


def final_translation_maps(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    talk: dict[str, str] = {}
    database: dict[str, str] = {}
    for row in read_csv(path):
        source = row["source_jp"]
        translated = row["thai_pua"]
        scopes = set(row["scope"].split(";"))
        if "talk" in scopes:
            talk[source] = translated
        if "database" in scopes:
            database[source] = translated
    return talk, database


def load_string_translations(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in read_csv(path):
        translated = row.get("Thai_PUA", "").strip() or row.get("คำแปลไทย", "").strip()
        if row.get("Key") and translated:
            result[row["Key"]] = translated
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--old-database-dir", type=Path, required=True)
    parser.add_argument("--old-talk-csv", type=Path, required=True)
    parser.add_argument("--old-string-csv", type=Path, required=True)
    parser.add_argument("--runtime-translation", type=Path, required=True)
    parser.add_argument("--final-translations", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    current_members = read_database_members(args.archive)
    parsed_current = {
        name: database
        for name, payload in current_members.items()
        if (database := parse_database(name, payload)) is not None
    }
    final_talk, final_database = final_translation_maps(args.final_translations)
    runtime = load_runtime_translations(args.runtime_translation)
    old_string_by_key = load_string_translations(args.old_string_csv)

    comparable: dict[str, tuple[ParsedDatabase, ParsedDatabase]] = {}
    for old_path in sorted(args.old_database_dir.glob("*.dat")):
        name = f"data/database/{old_path.name}"
        current = parsed_current.get(name)
        old = parse_database(name, old_path.read_bytes())
        if current is not None and old is not None:
            comparable[name] = (current, old)

    global_reusable: dict[str, str] = {}
    for name, (current, old) in comparable.items():
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
                    global_reusable.setdefault(source, translated)

    output_root = args.output_dir / "data" / "database"
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_files: list[dict[str, object]] = []
    missing_rows: list[dict[str, object]] = []
    coverage: Counter[str] = Counter()

    for name, (current, old) in sorted(comparable.items()):
        payload = current_members[name]
        old_by_id = {record.record_id: record for record in old.records}
        replacements: dict[tuple[int, int], str] = {}
        for record in current.records:
            old_record = old_by_id.get(record.record_id)
            fields = infer_record_japanese_fields(name, record, old_record)
            for field_index in fields:
                source = record.refs.get(field_index, "")
                if not source:
                    continue
                translated = ""
                source_kind = ""
                if name.endswith("/string.dat"):
                    key = record.refs.get(2, "")
                    translated = final_database.get(source, "")
                    if translated:
                        source_kind = "gemini_final"
                    elif key in old_string_by_key:
                        translated = old_string_by_key[key]
                        source_kind = "v120_string_key"
                    elif source in runtime:
                        translated = runtime[source]
                        source_kind = "runtime_translation"
                else:
                    translated = final_database.get(source, "")
                    if translated:
                        source_kind = "gemini_final"
                    if not translated and old_record is not None:
                        candidate = old_record.refs.get(field_index, "")
                        if text_is_translated_candidate(candidate):
                            translated = candidate
                            source_kind = "v120_same_record"
                    if not translated and source in global_reusable:
                        translated = global_reusable[source]
                        source_kind = "v120_global_reuse"
                    if not translated and source in runtime:
                        translated = runtime[source]
                        source_kind = "runtime_translation"
                if translated:
                    replacements[(record.record_id, field_index)] = translated
                    coverage[source_kind] += 1
                elif JAPANESE.search(source):
                    missing_rows.append(
                        {
                            "database": name,
                            "record_id": record.record_id,
                            "field_index": field_index,
                            "source_jp": source,
                        }
                    )

        built = serialize_with_replacements(payload, current, replacements)
        reparsed = parse_database(name, built)
        if reparsed is None or len(reparsed.records) != len(current.records):
            raise ValueError(f"generated override failed to parse: {name}")
        reparsed_by_id = {record.record_id: record for record in reparsed.records}
        for (record_id, field_index), translated in replacements.items():
            observed = reparsed_by_id[record_id].refs.get(field_index)
            if observed != translated:
                raise ValueError(
                    f"override verification failed: {name}:{record_id}:{field_index}"
                )
        output_path = output_root / Path(name).name
        output_path.write_bytes(built)
        manifest_files.append(
            {
                "name": name,
                "record_count": len(current.records),
                "replacement_fields": len(replacements),
                "original_size": len(payload),
                "override_size": len(built),
                "original_sha256": sha256_bytes(payload),
                "override_sha256": sha256_bytes(built),
            }
        )

    talk_name = "data/database/talk.dat"
    talk_database = parsed_current[talk_name]
    talk_lines = extract_talk_lines(talk_database)
    talk_key_by_record: dict[int, str] = {}
    for record in talk_database.records:
        keys = [text for text in record.refs.values() if text.startswith("TALK_ID_")]
        if keys:
            talk_key_by_record[record.record_id] = keys[0]

    old_talk_by_key: dict[str, dict[str, deque[str]]] = defaultdict(
        lambda: defaultdict(deque)
    )
    old_talk_global: dict[str, str] = {}
    for row in read_csv(args.old_talk_csv):
        source = row.get("text_jp", "")
        translated = row.get("text_th_pua", "")
        key = row.get("key", "")
        if source and translated and key:
            old_talk_by_key[key][source].append(translated)
            old_talk_global.setdefault(source, translated)

    talk_replacements: dict[tuple[int, int], str] = {}
    talk_missing: list[dict[str, object]] = []
    talk_record_by_key = {
        key: record
        for record in talk_database.records
        if (key := talk_key_by_record.get(record.record_id))
    }
    for key, lines in talk_lines.items():
        record = talk_record_by_key[key]
        for sequence, line in enumerate(lines, start=1):
            source = line.japanese
            translated = final_talk.get(source, "")
            source_kind = "gemini_final" if translated else ""
            queue = old_talk_by_key.get(key, {}).get(source)
            if not translated and queue:
                translated = queue.popleft()
                source_kind = "v120_same_talk_key"
            if not translated and source in old_talk_global:
                translated = old_talk_global[source]
                source_kind = "v120_global_talk_reuse"
            if not translated and source in runtime:
                translated = runtime[source]
                source_kind = "runtime_translation"
            if translated:
                talk_replacements[(record.record_id, line.field_index)] = translated
                coverage[source_kind] += 1
            elif JAPANESE.search(source):
                talk_missing.append(
                    {
                        "database": talk_name,
                        "record_id": record.record_id,
                        "field_index": line.field_index,
                        "key": key,
                        "sequence": sequence,
                        "source_jp": source,
                    }
                )

    talk_payload = current_members[talk_name]
    built_talk = serialize_with_replacements(talk_payload, talk_database, talk_replacements)
    reparsed_talk = parse_database(talk_name, built_talk)
    if reparsed_talk is None or len(reparsed_talk.records) != len(talk_database.records):
        raise ValueError("generated talk.dat failed to parse")
    reparsed_talk_by_id = {record.record_id: record for record in reparsed_talk.records}
    for (record_id, field_index), translated in talk_replacements.items():
        if reparsed_talk_by_id[record_id].refs.get(field_index) != translated:
            raise ValueError(f"talk override verification failed: {record_id}:{field_index}")
    talk_output = output_root / "talk.dat"
    talk_output.write_bytes(built_talk)
    manifest_files.append(
        {
            "name": talk_name,
            "record_count": len(talk_database.records),
            "replacement_fields": len(talk_replacements),
            "original_size": len(talk_payload),
            "override_size": len(built_talk),
            "original_sha256": sha256_bytes(talk_payload),
            "override_sha256": sha256_bytes(built_talk),
        }
    )

    all_missing = missing_rows + talk_missing
    with (args.output_dir / "v130_override_missing.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        fieldnames = sorted({key for row in all_missing for key in row}) if all_missing else ["source_jp"]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_missing)

    manifest = {
        "source_archive": str(args.archive),
        "source_archive_size": args.archive.stat().st_size,
        "source_archive_sha256": sha256_file(args.archive),
        "files": manifest_files,
        "coverage_fields": dict(coverage),
        "missing_japanese_fields": len(all_missing),
        "output_database_directory": str(output_root),
    }
    (args.output_dir / "v130_override_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "override_files": len(manifest_files),
                "database_replacements": sum(
                    int(item["replacement_fields"])
                    for item in manifest_files
                    if item["name"] != talk_name
                ),
                "talk_replacements": len(talk_replacements),
                "missing_japanese_fields": len(all_missing),
                "coverage_fields": dict(coverage),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
