#!/usr/bin/env python3
"""Translate a v1.30 workset with Gemini 3.5 Flash-Lite and strict validation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


PROMPT_VERSION = "vits-th-v7"
THAI = re.compile(r"[\u0e00-\u0e7f]")
PUA = re.compile(r"[\ue000-\uf8ff]")
TOKEN = re.compile(
    r"<[^>]+>|\[SCALE:[^\]]+\]|\\[nt]|%(?:\d+\$)?[sdif]|\{[^{}]+\}"
)

GROUP_TONE_GUIDE = {
    "BOY": "เด็กผู้ชายร่าเริง: แทนตัวเองว่า 'ผม' เสมอ พูดเป็นกันเองและสดใส",
    "CARPENTER": "ช่างไม้ชายพูดห้าวและตรง: แทนตัวเองว่า 'ข้า' เรียกอีกฝ่ายว่า 'เจ้า'",
    "CITY_HALL_STAFF": "เจ้าหน้าที่ชายสุภาพ: แทนตัวเองว่า 'ผม' ลงท้าย 'ครับ' อย่างเป็นธรรมชาติ",
    "FEMALE_DOCTOR": "คุณหมอหญิงสุภาพอ่อนโยน: แทนตัวเองว่า 'ฉัน' ลงท้าย 'ค่ะ/คะ'",
    "GENERAL_STORE_MANAGER": "เจ้าของร้านหญิงอารมณ์ดีแบบพี่สาว: ใช้ 'ฉัน/พี่สาว' เรียกผู้เล่นว่า 'เธอ' ลงท้าย 'จ๊ะ/จ๋า' ตามอารมณ์",
    "GIRL": "เด็กหญิงไร้เดียงสา: แทนตัวเองว่า 'หนู' ใช้ 'จ้ะ/นะ'",
    "HUNTER": "หญิงนักล่าที่เป็นมิตรแต่สุขุม: แทนตัวเองว่า 'ฉัน' เรียกผู้เล่นว่า 'เธอ' ใช้ 'จ๊ะ' เมื่อเหมาะสม",
    "LUMBERJACK": "ชายสูงวัยสำเนียงบ้านๆ: แทนตัวเองว่า 'ข้า' เรียกผู้เล่นว่า 'เจ้า' ใช้คำอย่าง 'เรอะ/ล่ะ'",
    "OLD_MAN": "ลุงเจ้าของร้านอาหารพูดขบขันโบราณ: แทนตัวเองว่า 'ลุง' ลงท้าย 'ขอรับ'",
    "ORPHAN": "หญิงสาวพูดห้วนและเก็บตัว: แทนตัวเองว่า 'ฉัน' เรียกผู้เล่นว่า 'นาย' ไม่เติมคำสุภาพเกินบุคลิก",
    "SECRETARY": "เลขานุการชายจอมทะเล้นที่แสร้งเป็นทางการ: ใช้คำสุภาพโอเวอร์และลงท้าย 'คร้าบ' ตามสำนวนเดิม",
    "STREET_VENDOR": "แม่ค้าหญิงร่าเริง: แทนตัวเองว่า 'ฉัน' เรียกผู้เล่นว่า 'เธอ' ลงท้าย 'จ้า/ล่ะ'",
    "VILLAGE_HEAD": "ผู้นำหมู่บ้านหญิงน้ำเสียงเด็ดขาดและมีอำนาจ: กระชับ มั่นใจ ไม่อ่อนหวานเกินไป",
    "YOUNG_MAN": "ชายหนุ่มสุภาพเป็นกันเอง: แทนตัวเองว่า 'ผม' และรักษาน้ำเสียงอบอุ่น",
}

SYSTEM_PROMPT = """You are the lead Thai localization editor for the cozy farming RPG
Village in the Shade (Honogurashi no Niwa). Translate game text into polished,
natural Thai suitable for an official localization.

Priority and tone:
1. Translate primarily from source_en. Use source_jp to recover nuance, omitted
   subjects, honorifics, gender, and the exact fragment boundary.
2. Use context_en to understand lines that the official English localization
   merged across several Japanese fragments. Translate only the Japanese fragment
   in source_jp, while making adjacent Thai fragments read naturally together.
   Items from the same key are supplied in source order. Coordinate their wording
   as one scene; never translate a short English continuation in isolation or omit
   meaningful Japanese words such as 気持ち merely because English moved them to
   the previous fragment.
   The semantic boundary of source_jp is authoritative: translate everything in
   that Japanese fragment and nothing belonging only to adjacent fragments. If
   source_en merges two or more JP lines, do not copy its extra clause into this
   item and do not duplicate content that another item will translate.
3. Match the supplied legacy style examples and existing_thai. Keep an existing
   translation when it is accurate and natural; revise it when stiff, mistranslated,
   inconsistent, or tonally wrong.
   If alternative_thai is present, compare both Thai candidates skeptically.
   Do not assume the later candidate is better: keep existing_thai, select the
   alternative, or write a third improved version according to accuracy and voice.
4. Preserve each speaker's personality: rough speech stays rough, children sound
   youthful, reserved characters stay restrained, and polite professionals remain
   polite. Do not flatten everyone into the same neutral voice.
5. UI, item, quest, and system text must be concise and immediately clear.

Hard requirements:
- Return normal Unicode Thai, never PUA glyphs.
- Preserve every placeholder and markup token from source_jp exactly, once, and
  in the same order: examples include <player>, <value 1>, <cmd ...>, <strong>,
  closing tags, and escaped newlines. You may insert <br> only where a Thai line
  genuinely needs wrapping; do not add any other markup.
- Do not translate character variables, command names, IDs, or tag attributes.
- Do not add explanations, quotation marks, romanization, or translator notes.
- Avoid word-for-word English syntax. Prefer idiomatic Thai that fits the scene.
- Translate repeated terminology consistently throughout the batch.
- Output one result for every input id, in the same order.
"""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, start=1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def load_mapping(path: Path) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    mapping = json.loads(path.read_text(encoding="utf-8"))
    forward = sorted(
        ((str(normal), str(encoded)) for normal, encoded in mapping.items()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    inverse_map: dict[str, str] = {}
    for normal, encoded in forward:
        inverse_map.setdefault(encoded, normal)
    inverse = sorted(inverse_map.items(), key=lambda item: len(item[0]), reverse=True)
    return forward, inverse


def index_pairs(pairs: list[tuple[str, str]]) -> dict[str, list[tuple[str, str]]]:
    indexed: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for source, target in pairs:
        if source:
            indexed[source[0]].append((source, target))
    return dict(indexed)


def replace_longest(text: str, indexed_pairs: dict[str, list[tuple[str, str]]]) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        for source, target in indexed_pairs.get(text[index], []):
            if text.startswith(source, index):
                output.append(target)
                index += len(source)
                break
        else:
            output.append(text[index])
            index += 1
    return "".join(output)


def token_counter(text: str) -> Counter[str]:
    return Counter(token for token in TOKEN.findall(text) if token.lower() != "<br>")


def validate_translation(item: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("id") != item["id"]:
        errors.append(f"id mismatch: expected {item['id']!r}, got {result.get('id')!r}")
    thai = result.get("thai")
    if not isinstance(thai, str) or not thai.strip():
        errors.append("empty Thai translation")
        return errors
    if PUA.search(thai):
        errors.append("output contains PUA glyphs")
    if token_counter(thai) != token_counter(str(item["source_jp"])):
        errors.append(
            "placeholder/markup mismatch: "
            f"source={dict(token_counter(str(item['source_jp'])))} "
            f"output={dict(token_counter(thai))}"
        )
    if not THAI.search(thai):
        errors.append("output contains no Thai characters")
    expected_actions = {"translated"} if item["state"] == "missing" else {"kept", "revised"}
    if result.get("action") not in expected_actions:
        errors.append(
            f"invalid action {result.get('action')!r}; expected {sorted(expected_actions)}"
        )
    return errors


def response_schema(batch: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "minItems": len(batch),
                "maxItems": len(batch),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "The exact input id.",
                        },
                        "thai": {
                            "type": "string",
                            "description": "Final normal-Unicode Thai game text.",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["translated", "kept", "revised"],
                        },
                    },
                    "required": ["id", "thai", "action"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["translations"],
        "additionalProperties": False,
    }


def prompt_for_batch(
    batch: list[dict[str, Any]], style_examples: dict[str, list[dict[str, str]]]
) -> str:
    groups = sorted(
        {
            group
            for item in batch
            for group in str(item.get("group", "")).split(";")
            if group
        }
    )
    compact_examples = [
        {"group": group, **example}
        for group in groups
        for example in style_examples.get(group, [])[:8]
    ][:20]
    tone_guide = {group: GROUP_TONE_GUIDE[group] for group in groups if group in GROUP_TONE_GUIDE}
    compact_items = [
        {
            "id": item["id"],
            "state": item["state"],
            "group": item["group"],
            "key": item["keys"],
            "source_en": item["source_en"],
            "source_jp": item["source_jp"],
            "existing_thai": item["existing_thai"],
            "alternative_thai": item.get("alternative_thai", ""),
            "context_en": item["context_en"],
        }
        for item in batch
    ]
    return (
        "Translate/edit the following batch. The character voice guide is binding, "
        "especially first-person pronouns and sentence endings. The legacy examples are style evidence, "
        "not text to output. For a blank source_en, infer the fragment from context_en "
        "and source_jp.\n\nCHARACTER VOICE GUIDE:\n"
        + json.dumps(tone_guide, ensure_ascii=False, separators=(",", ":"))
        + "\n\nLEGACY STYLE EXAMPLES:\n"
        + json.dumps(compact_examples, ensure_ascii=False, separators=(",", ":"))
        + "\n\nITEMS:\n"
        + json.dumps(compact_items, ensure_ascii=False, separators=(",", ":"))
    )


def extract_response_text(response: dict[str, Any]) -> str:
    candidates = response.get("candidates") or []
    if not candidates:
        raise ValueError(f"Gemini returned no candidates: {response.get('promptFeedback')}")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(str(part.get("text", "")) for part in parts)
    if not text:
        raise ValueError("Gemini candidate contained no text")
    return text


def call_gemini(
    *,
    api_key: str,
    model: str,
    batch: list[dict[str, Any]],
    style_examples: dict[str, list[dict[str, str]]],
    timeout: float,
    max_retries: int,
    thinking_level: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], float, int]:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + model
        + ":generateContent"
    )
    base_prompt = prompt_for_batch(batch, style_examples)
    validation_feedback = ""
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        prompt = base_prompt + validation_feedback
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "thinkingConfig": {"thinkingLevel": thinking_level},
                "responseFormat": {
                    "text": {
                        "mimeType": "APPLICATION_JSON",
                        "schema": response_schema(batch),
                    }
                }
            },
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response_stream:
                response = json.loads(response_stream.read().decode("utf-8"))
            elapsed = time.perf_counter() - started
            parsed = json.loads(extract_response_text(response))
            translations = parsed.get("translations")
            if not isinstance(translations, list) or len(translations) != len(batch):
                raise ValueError(
                    f"expected {len(batch)} translations, got "
                    f"{len(translations) if isinstance(translations, list) else type(translations)}"
                )
            errors: list[str] = []
            for item, result in zip(batch, translations):
                item_errors = validate_translation(item, result)
                errors.extend(f"{item['id']}: {message}" for message in item_errors)
            if errors:
                validation_feedback = (
                    "\n\nThe previous answer failed validation. Regenerate the entire batch and fix "
                    "all of these issues:\n- "
                    + "\n- ".join(errors[:30])
                )
                last_error = ValueError("; ".join(errors))
                if attempt < max_retries:
                    continue
                raise last_error
            return translations, response.get("usageMetadata", {}), elapsed, attempt
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {exc.code}: {body[:1000]}")
            if exc.code not in {408, 409, 429, 500, 502, 503, 504} or attempt >= max_retries:
                raise last_error from exc
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else min(30.0, 1.5 * 2 ** (attempt - 1))
            time.sleep(delay + random.random())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt >= max_retries:
                raise
            time.sleep(min(15.0, 1.25 * 2 ** (attempt - 1)) + random.random())
    raise RuntimeError(f"Gemini request failed: {last_error}")


def make_batches(rows: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[str(row.get("group", "OTHER"))].append(row)
    batches: list[list[dict[str, Any]]] = []
    for group in sorted(by_group):
        group_rows = by_group[group]
        for offset in range(0, len(group_rows), batch_size):
            batches.append(group_rows[offset : offset + batch_size])
    return batches


def batch_identity(batch: list[dict[str, Any]], model: str, thinking_level: str) -> str:
    material = json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            "model": model,
            "thinking_level": thinking_level,
            "ids": [item["id"] for item in batch],
            "sources": [item["source_jp"] for item in batch],
            "states": [item["state"] for item in batch],
            "existing_thai": [item.get("existing_thai", "") for item in batch],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--style-examples", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument(
        "--thinking-level", choices=["minimal", "low", "medium", "high"], default="low"
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    rows = read_jsonl(args.input)
    if args.limit is not None:
        rows = rows[: args.limit]
    if not rows:
        raise ValueError("workset is empty")
    style_examples = json.loads(args.style_examples.read_text(encoding="utf-8"))
    forward_mapping, inverse_mapping = load_mapping(args.mapping)
    forward_index = index_pairs(forward_mapping)
    inverse_index = index_pairs(inverse_mapping)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    response_dir = args.output_dir / "responses"
    response_dir.mkdir(parents=True, exist_ok=True)
    batches = make_batches(rows, args.batch_size)
    started_all = time.perf_counter()
    result_by_id: dict[str, dict[str, Any]] = {}
    usage_totals: Counter[str] = Counter()
    api_requests = 0
    cached_batches = 0
    durations: list[float] = []

    pending: list[tuple[str, list[dict[str, Any]], Path]] = []

    def accumulate_usage(usage: dict[str, Any]) -> None:
        for key, value in usage.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage_totals[key] += value

    for batch in batches:
        identity = batch_identity(batch, args.model, args.thinking_level)
        path = response_dir / f"{identity}.json"
        if path.is_file() and not args.no_resume:
            saved = json.loads(path.read_text(encoding="utf-8"))
            translations = saved.get("translations", [])
            if len(translations) == len(batch) and all(
                not validate_translation(item, result)
                for item, result in zip(batch, translations)
            ):
                for result in translations:
                    result_by_id[result["id"]] = result
                accumulate_usage(saved.get("usage", {}))
                cached_batches += 1
                continue
        pending.append((identity, batch, path))

    def run_one(entry: tuple[str, list[dict[str, Any]], Path]) -> dict[str, Any]:
        identity, batch, path = entry
        translations, usage, elapsed, attempts = call_gemini(
            api_key=api_key,
            model=args.model,
            batch=batch,
            style_examples=style_examples,
            timeout=args.timeout,
            max_retries=args.max_retries,
            thinking_level=args.thinking_level,
        )
        saved = {
            "batch_id": identity,
            "model": args.model,
            "prompt_version": PROMPT_VERSION,
            "input_ids": [item["id"] for item in batch],
            "translations": translations,
            "usage": usage,
            "elapsed_seconds": elapsed,
            "attempts": attempts,
        }
        path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return saved

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = {executor.submit(run_one, entry): entry[0] for entry in pending}
        completed = 0
        for future in as_completed(futures):
            saved = future.result()
            for result in saved["translations"]:
                result_by_id[result["id"]] = result
            accumulate_usage(saved.get("usage", {}))
            durations.append(float(saved["elapsed_seconds"]))
            api_requests += 1
            completed += 1
            print(
                f"completed {completed}/{len(pending)} API batches "
                f"({len(result_by_id)}/{len(rows)} lines)",
                flush=True,
            )

    missing_ids = [row["id"] for row in rows if row["id"] not in result_by_id]
    if missing_ids:
        raise RuntimeError(f"missing translated IDs: {missing_ids[:20]}")

    output_rows: list[dict[str, Any]] = []
    for item in rows:
        result = result_by_id[item["id"]]
        thai = result["thai"].strip()
        thai_pua = replace_longest(thai, forward_index)
        roundtrip = replace_longest(thai_pua, inverse_index)
        if roundtrip != thai:
            raise ValueError(f"PUA round-trip mismatch for {item['id']}: {thai!r} -> {roundtrip!r}")
        output_rows.append(
            {
                **item,
                "thai": thai,
                "thai_pua": thai_pua,
                "action": result["action"],
                "model": args.model,
                "prompt_version": PROMPT_VERSION,
            }
        )

    csv_path = args.output_dir / "v130_translated_thai.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0].keys()))
        writer.writeheader()
        writer.writerows(output_rows)
    with (args.output_dir / "v130_translated_thai.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as stream:
        for row in output_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    elapsed_all = time.perf_counter() - started_all
    translated_count = sum(row["action"] == "translated" for row in output_rows)
    kept_count = sum(row["action"] == "kept" for row in output_rows)
    revised_count = sum(row["action"] == "revised" for row in output_rows)
    prompt_tokens = int(usage_totals.get("promptTokenCount", 0))
    output_tokens = int(usage_totals.get("candidatesTokenCount", 0))
    thoughts_tokens = int(usage_totals.get("thoughtsTokenCount", 0))
    summary = {
        "model": args.model,
        "prompt_version": PROMPT_VERSION,
        "total_lines": len(output_rows),
        "translated": translated_count,
        "kept_existing": kept_count,
        "revised_existing": revised_count,
        "elapsed_seconds": round(elapsed_all, 3),
        "throughput_lines_per_minute": round(len(output_rows) / elapsed_all * 60, 1),
        "api_batches": api_requests,
        "cached_batches": cached_batches,
        "batch_size": args.batch_size,
        "concurrency": args.concurrency,
        "thinking_level": args.thinking_level,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "thoughts_tokens": thoughts_tokens,
        "estimated_usd": round(
            prompt_tokens / 1_000_000 * 0.30
            + (output_tokens + thoughts_tokens) / 1_000_000 * 2.50,
            4,
        ),
        "max_single_batch_seconds": round(max(durations), 3) if durations else 0,
    }
    (args.output_dir / "v130_translation_run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
