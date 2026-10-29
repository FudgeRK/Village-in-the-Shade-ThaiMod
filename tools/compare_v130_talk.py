#!/usr/bin/env python3
"""Compare v1.30 talk.dat dialogue text with the v1.20 extraction CSV."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from audit_v130_database_texts import parse_database, read_database_members
from compare_v130_strings import load_runtime_translations


JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
KANA = re.compile(r"[\u3040-\u30ff]")
HANGUL = re.compile(r"[\uac00-\ud7af]")


def load_v120_talk(path: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, str]]:
    by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    thai_by_japanese: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            key = row.get("key", "")
            japanese = row.get("text_jp", "")
            thai = row.get("text_th_pua", "").strip()
            if not key or not japanese:
                continue
            by_key[key].append(row)
            if thai:
                thai_by_japanese.setdefault(japanese, thai)
    return dict(by_key), thai_by_japanese


def extract_v130_talk(archive_path: Path) -> tuple[dict[str, list[str]], dict[str, object]]:
    payload = read_database_members(archive_path)["data/database/talk.dat"]
    database = parse_database("data/database/talk.dat", payload)
    if database is None:
        raise ValueError("could not parse v1.30 talk.dat")

    result: dict[str, list[str]] = {}
    records_without_key = 0
    duplicate_keys: list[str] = []
    for record in database.records:
        ordered_ref_items = sorted(record.refs.items())
        ordered_refs = [text for _index, text in ordered_ref_items]
        keys = [text for text in ordered_refs if text.startswith("TALK_ID_")]
        if not keys:
            records_without_key += 1
            continue
        key = keys[0]
        ref_map = {
            index: text
            for index, text in ordered_ref_items
            if text != key and not text.startswith("TALK_ID_")
        }
        handled: set[int] = set()
        indexed_texts: list[tuple[int, str]] = []

        # Retail talk records store seven languages as adjacent offset/length
        # pairs: JP, EN, FR, ES, zh-TW, KO, zh-CN. Select only the first pair.
        for index in sorted(ref_map):
            language_indices = [index + step * 2 for step in range(7)]
            if index in handled or not all(item in ref_map for item in language_indices):
                continue
            indexed_texts.append((index, ref_map[index]))
            handled.update(language_indices)

        # Some official records omit one or more non-Japanese languages or
        # merge several JP lines into one English line. Keep the JP slot and
        # its EN neighbour when present even if the full seven-slot run is not.
        for index in sorted(ref_map):
            text = ref_map[index]
            if index in handled or not KANA.search(text) or HANGUL.search(text):
                continue
            indexed_texts.append((index, text))
            handled.add(index)
            if index + 2 in ref_map:
                handled.add(index + 2)

        # Older/debug records sometimes contain only the Japanese slot. Kana is
        # an unambiguous fallback; pure CJK strings are intentionally not guessed.
        for index in sorted(ref_map):
            text = ref_map[index]
            if index not in handled and KANA.search(text) and not HANGUL.search(text):
                indexed_texts.append((index, text))
        texts = [text for _index, text in sorted(indexed_texts)]
        if key in result:
            duplicate_keys.append(key)
            result[key].extend(texts)
        else:
            result[key] = texts

    diagnostics: dict[str, object] = {
        "record_count": len(database.records),
        "key_count": len(result),
        "records_without_key": records_without_key,
        "duplicate_keys": sorted(set(duplicate_keys)),
    }
    return result, diagnostics


def is_source_text(text: str) -> bool:
    return bool(text.strip() and not HANGUL.search(text))


def needs_linguistic_translation(text: str) -> bool:
    return bool(JAPANESE.search(text) and not HANGUL.search(text))


def compare(
    current_by_key: dict[str, list[str]],
    old_by_key: dict[str, list[dict[str, str]]],
    old_thai_by_japanese: dict[str, str],
    runtime_translations: dict[str, str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    rows: list[dict[str, object]] = []
    new_keys = set(current_by_key) - set(old_by_key)
    removed_keys = set(old_by_key) - set(current_by_key)
    changed_existing_keys: set[str] = set()

    for key, current_texts in current_by_key.items():
        old_rows = old_by_key.get(key, [])
        remaining_old = Counter(row["text_jp"] for row in old_rows if row.get("text_jp"))
        key_had_delta = False
        for sequence, source in enumerate(current_texts, start=1):
            if not is_source_text(source):
                continue
            if remaining_old[source] > 0:
                remaining_old[source] -= 1
                status = "unchanged"
            else:
                status = "new_key_text" if key in new_keys else "new_or_changed_text"
                key_had_delta = True

            runtime_translation = runtime_translations.get(source, "")
            reusable_translation = old_thai_by_japanese.get(source, "")
            if not needs_linguistic_translation(source):
                coverage = "no_translation_needed"
            elif runtime_translation:
                coverage = "translation.txt"
            elif reusable_translation:
                coverage = "v1.20_translation_reusable"
            else:
                coverage = "missing"

            rows.append(
                {
                    "status": status,
                    "key": key,
                    "sequence": sequence,
                    "source_text": source,
                    "coverage": coverage,
                    "runtime_translation": runtime_translation,
                    "v120_reusable_translation": reusable_translation,
                }
            )
        if key_had_delta and key not in new_keys:
            changed_existing_keys.add(key)

    delta_rows = [row for row in rows if row["status"] != "unchanged"]
    missing_delta_rows = [row for row in delta_rows if row["coverage"] == "missing"]
    reusable_delta_rows = [
        row for row in delta_rows if row["coverage"] == "v1.20_translation_reusable"
    ]
    runtime_delta_rows = [row for row in delta_rows if row["coverage"] == "translation.txt"]
    linguistic_delta_rows = [
        row for row in delta_rows if row["coverage"] != "no_translation_needed"
    ]
    nonlinguistic_delta_rows = [
        row for row in delta_rows if row["coverage"] == "no_translation_needed"
    ]

    summary: dict[str, object] = {
        "v120_key_count": len(old_by_key),
        "v130_key_count": len(current_by_key),
        "new_key_count": len(new_keys),
        "removed_key_count": len(removed_keys),
        "existing_keys_with_new_or_changed_text": len(changed_existing_keys),
        "delta_japanese_occurrences": len(delta_rows),
        "delta_unique_japanese_strings": len({str(row["source_text"]) for row in delta_rows}),
        "delta_linguistic_japanese_occurrences": len(linguistic_delta_rows),
        "delta_linguistic_unique_japanese_strings": len(
            {str(row["source_text"]) for row in linguistic_delta_rows}
        ),
        "delta_nonlinguistic_occurrences": len(nonlinguistic_delta_rows),
        "delta_nonlinguistic_unique_strings": len(
            {str(row["source_text"]) for row in nonlinguistic_delta_rows}
        ),
        "delta_runtime_covered_occurrences": len(runtime_delta_rows),
        "delta_reusable_v120_occurrences": len(reusable_delta_rows),
        "delta_missing_occurrences": len(missing_delta_rows),
        "delta_missing_unique_strings": len(
            {str(row["source_text"]) for row in missing_delta_rows}
        ),
        "new_keys": sorted(new_keys),
        "removed_keys": sorted(removed_keys),
        "changed_existing_keys": sorted(changed_existing_keys),
    }
    return rows, summary


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--v120-talk-csv", type=Path, required=True)
    parser.add_argument("--translation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    current_by_key, diagnostics = extract_v130_talk(args.archive)
    old_by_key, old_thai_by_japanese = load_v120_talk(args.v120_talk_csv)
    runtime_translations = load_runtime_translations(args.translation)
    rows, summary = compare(
        current_by_key, old_by_key, old_thai_by_japanese, runtime_translations
    )
    summary["v130_parse_diagnostics"] = diagnostics

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "v130_talk_comparison.csv", rows)
    write_csv(
        args.output_dir / "v130_talk_translation_candidates.csv",
        [row for row in rows if row["status"] != "unchanged" and row["coverage"] == "missing"],
    )
    (args.output_dir / "v130_talk_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in summary.items() if not isinstance(value, list)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
