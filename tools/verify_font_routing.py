#!/usr/bin/env python3
"""Verify that every locale in font.dat can be routed to the Thai KiwiMaru face."""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path


ARCHIVE_HEADER = struct.Struct("<8sIIQQQQ")
TOC_ENTRY = struct.Struct("<QQQQQQ")
FONT_MEMBER = "data/database/font.dat"


@dataclass(frozen=True)
class FontLayout:
    record_count: int
    text_base: int
    text_size: int
    records: tuple[tuple[int, int], ...]


def read_c_string(data: bytes, offset: int) -> str:
    end = data.find(b"\0", offset)
    if end < 0:
        end = len(data)
    return data[offset:end].decode("utf-8")


def read_archive_member(archive_path: Path, wanted_name: str) -> bytes:
    with archive_path.open("rb") as stream:
        header = stream.read(ARCHIVE_HEADER.size)
        if len(header) != ARCHIVE_HEADER.size:
            raise ValueError(f"{archive_path}: archive header is truncated")

        magic, count, _unknown, string_offset, string_size, toc_offset, _padding = (
            ARCHIVE_HEADER.unpack(header)
        )
        if magic != b"FAFULLFS":
            raise ValueError(f"{archive_path}: unexpected archive magic {magic!r}")

        stream.seek(toc_offset)
        entries = [TOC_ENTRY.unpack(stream.read(TOC_ENTRY.size)) for _ in range(count)]
        stream.seek(string_offset)
        string_table = stream.read(string_size)

        for _hash, name_offset, _unknown1, size, offset, _unknown2 in entries:
            if name_offset >= len(string_table):
                continue
            if read_c_string(string_table, int(name_offset)) != wanted_name:
                continue
            stream.seek(offset)
            payload = stream.read(size)
            if len(payload) != size:
                raise ValueError(f"{archive_path}: {wanted_name} is truncated")
            return payload

    raise KeyError(f"{archive_path}: archive member not found: {wanted_name}")


def parse_layout(payload: bytes) -> FontLayout:
    if len(payload) < 64:
        raise ValueError("font.dat is too small")

    record_count, record_data_size, text_size = struct.unpack_from("<3I", payload)
    text_base = 12 + record_count * 4 + record_data_size
    if not 0 < record_count <= 32 or text_base + text_size != len(payload):
        raise ValueError(
            "invalid font.dat layout: "
            f"records={record_count}, record_data={record_data_size}, "
            f"text={text_size}, file={len(payload)}"
        )

    records: list[tuple[int, int]] = []
    cursor = 12
    for record_index in range(record_count):
        if cursor + 4 > text_base:
            raise ValueError(f"record {record_index} size is outside record region")
        record_size = struct.unpack_from("<I", payload, cursor)[0]
        words_offset = cursor + 4
        if (
            record_size == 0
            or record_size % 4
            or words_offset + record_size > text_base
        ):
            raise ValueError(f"record {record_index} has invalid size {record_size}")
        records.append((words_offset, record_size // 4))
        cursor = words_offset + record_size

    if cursor != text_base:
        raise ValueError(f"record region ends at {cursor}, expected {text_base}")
    return FontLayout(record_count, text_base, text_size, tuple(records))


def decode_ref(text_pool: bytes, offset: int, length: int) -> str | None:
    if offset + length > len(text_pool):
        return None
    try:
        return text_pool[offset : offset + length].decode("ascii")
    except UnicodeDecodeError:
        return None


def find_ttf_indices(words: list[int], text_pool: bytes) -> list[int]:
    result: list[int] = []
    index = 1
    while index + 1 < len(words):
        text = decode_ref(text_pool, words[index], words[index + 1])
        if text and text.lower().startswith("data/misc/") and text.lower().endswith(
            ".ttf"
        ):
            result.append(index)
            index += 2
        else:
            index += 1
    return result


def route_and_verify(payload: bytes) -> tuple[int, int]:
    """Mirror the C runtime patch and assert its postconditions."""
    layout = parse_layout(payload)
    patched = bytearray(payload)
    text_pool = payload[layout.text_base :]
    expected_by_record: list[tuple[int, int, int, int, int]] = []

    for record_index, (words_offset, word_count) in enumerate(layout.records):
        words = list(struct.unpack_from(f"<{word_count}I", patched, words_offset))
        path_indices = find_ttf_indices(words, text_pool)
        kiwi_indices = [
            index
            for index in path_indices
            if "kiwimaru-"
            in (decode_ref(text_pool, words[index], words[index + 1]) or "").lower()
        ]
        if len(kiwi_indices) != 1:
            raise AssertionError(
                f"record {record_index}: expected one KiwiMaru slot, found {len(kiwi_indices)}"
            )

        kiwi_index = kiwi_indices[0]
        if kiwi_index + 3 >= word_count:
            raise AssertionError(f"record {record_index}: incomplete KiwiMaru reference")
        kiwi_ref = tuple(words[kiwi_index : kiwi_index + 4])
        expected_by_record.append((*kiwi_ref, len(path_indices)))

        for path_index in path_indices:
            words[path_index : path_index + 4] = kiwi_ref
            if path_index + 19 < word_count:
                words[path_index + 18 : path_index + 20] = [1, 5]
        struct.pack_into(f"<{word_count}I", patched, words_offset, *words)

    total_slots = 0
    for record_index, ((words_offset, word_count), expected) in enumerate(
        zip(layout.records, expected_by_record, strict=True)
    ):
        words = list(struct.unpack_from(f"<{word_count}I", patched, words_offset))
        path_indices = find_ttf_indices(words, text_pool)
        kiwi_offset, kiwi_length, family_offset, family_length, expected_slots = expected
        if len(path_indices) != expected_slots:
            raise AssertionError(
                f"record {record_index}: slot count changed from {expected_slots} "
                f"to {len(path_indices)}"
            )
        for path_index in path_indices:
            actual_ref = tuple(words[path_index : path_index + 4])
            if actual_ref != (
                kiwi_offset,
                kiwi_length,
                family_offset,
                family_length,
            ):
                raise AssertionError(f"record {record_index}: locale was not routed")
            if path_index + 19 >= word_count or words[path_index + 18 : path_index + 20] != [
                1,
                5,
            ]:
                raise AssertionError(
                    f"record {record_index}: proportional flags were not patched"
                )
        total_slots += len(path_indices)

    return layout.record_count, total_slots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "font_dat",
        nargs="*",
        type=Path,
        help="standalone font.dat file(s); defaults to data/font.dat",
    )
    parser.add_argument(
        "--archive",
        action="append",
        default=[],
        type=Path,
        help="FAFULLFS archive containing data/database/font.dat",
    )
    args = parser.parse_args()

    targets: list[tuple[str, bytes]] = []
    for path in args.font_dat or [Path("data/font.dat")]:
        targets.append((str(path), path.read_bytes()))
    for path in args.archive:
        targets.append(
            (f"{path}:{FONT_MEMBER}", read_archive_member(path, FONT_MEMBER))
        )

    for label, payload in targets:
        records, slots = route_and_verify(payload)
        print(f"PASS {label}: records={records}, locale_slots={slots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
