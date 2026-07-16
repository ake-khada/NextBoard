#!/usr/bin/env python3
"""Build a deterministic NextBoard .nwlm model from monolingual text."""

from __future__ import annotations

import argparse
import gzip
import html
import lzma
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
import re
import struct
import sys
from typing import BinaryIO, Iterable, Iterator, TextIO


MAGIC = b"NWLM"
VERSION = 1
BOS_CONTEXT = "\x02"
CONTEXT_SEPARATOR = "\x01"
MAX_CANDIDATES = 4
TABLE_ENTRY_SIZE = 13
MAX_HASH_LOAD = 0.7
MASK64 = (1 << 64) - 1

PRIME64_1 = 11400714785074694791
PRIME64_2 = 14029467366897019727
PRIME64_3 = 1609587929392839161
PRIME64_4 = 9650029242287828579
PRIME64_5 = 2870177450012600261

TOKEN_RE = re.compile(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*", re.UNICODE)
SENTENCE_SPLIT_RE = re.compile(r"[.!?\r\n]+")
HTML_TAG_RE = re.compile(r"<[^>]+>")

TINY_SENTENCES = (
    "I want to go home.",
    "I want to see you.",
    "I want to be there.",
    "I like this keyboard.",
    "I like this place.",
    "You want to go now.",
    "You want to see this.",
    "We want to be ready.",
    "Hello there.",
    "Hello world.",
    "It's a tiny model.",
    "It's a useful test.",
)


def _rotl64(value: int, count: int) -> int:
    return ((value << count) | (value >> (64 - count))) & MASK64


def _round64(accumulator: int, lane: int) -> int:
    accumulator = (accumulator + lane * PRIME64_2) & MASK64
    accumulator = _rotl64(accumulator, 31)
    return (accumulator * PRIME64_1) & MASK64


def _merge_round64(accumulator: int, value: int) -> int:
    accumulator ^= _round64(0, value)
    return (accumulator * PRIME64_1 + PRIME64_4) & MASK64


def xxhash64(data: bytes, seed: int = 0) -> int:
    """Return the standard xxHash64 digest as an unsigned integer."""
    length = len(data)
    offset = 0
    if length >= 32:
        v1 = (seed + PRIME64_1 + PRIME64_2) & MASK64
        v2 = (seed + PRIME64_2) & MASK64
        v3 = seed & MASK64
        v4 = (seed - PRIME64_1) & MASK64
        limit = length - 32
        while offset <= limit:
            v1 = _round64(v1, int.from_bytes(data[offset : offset + 8], "little"))
            offset += 8
            v2 = _round64(v2, int.from_bytes(data[offset : offset + 8], "little"))
            offset += 8
            v3 = _round64(v3, int.from_bytes(data[offset : offset + 8], "little"))
            offset += 8
            v4 = _round64(v4, int.from_bytes(data[offset : offset + 8], "little"))
            offset += 8
        digest = (
            _rotl64(v1, 1)
            + _rotl64(v2, 7)
            + _rotl64(v3, 12)
            + _rotl64(v4, 18)
        ) & MASK64
        digest = _merge_round64(digest, v1)
        digest = _merge_round64(digest, v2)
        digest = _merge_round64(digest, v3)
        digest = _merge_round64(digest, v4)
    else:
        digest = (seed + PRIME64_5) & MASK64

    digest = (digest + length) & MASK64
    while offset + 8 <= length:
        lane = _round64(0, int.from_bytes(data[offset : offset + 8], "little"))
        digest ^= lane
        digest = (_rotl64(digest, 27) * PRIME64_1 + PRIME64_4) & MASK64
        offset += 8
    if offset + 4 <= length:
        lane = int.from_bytes(data[offset : offset + 4], "little")
        digest ^= (lane * PRIME64_1) & MASK64
        digest = (_rotl64(digest, 23) * PRIME64_2 + PRIME64_3) & MASK64
        offset += 4
    while offset < length:
        digest ^= (data[offset] * PRIME64_5) & MASK64
        digest = (_rotl64(digest, 11) * PRIME64_1) & MASK64
        offset += 1

    digest ^= digest >> 33
    digest = (digest * PRIME64_2) & MASK64
    digest ^= digest >> 29
    digest = (digest * PRIME64_3) & MASK64
    digest ^= digest >> 32
    return digest & MASK64


def normalize_key(token: str, language: str) -> str:
    normalized = token.replace("\u2019", "'").lower()
    if language == "ru":
        normalized = normalized.replace("ё", "е")
    return normalized


def normalize_surface(token: str) -> str:
    return token.replace("\u2019", "'")


def tokenize_sentences(text: str) -> Iterator[list[str]]:
    text = html.unescape(HTML_TAG_RE.sub(" ", text))
    for fragment in SENTENCE_SPLIT_RE.split(text):
        tokens = [normalize_surface(match.group(0)) for match in TOKEN_RE.finditer(fragment)]
        if tokens:
            yield tokens


def open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    if path.suffix in {".xz", ".lzma"}:
        return lzma.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def iter_corpus_sentences(paths: Iterable[Path]) -> Iterator[list[str]]:
    for path in paths:
        with open_text(path) as corpus:
            for line in corpus:
                yield from tokenize_sentences(line)


def count_ngrams(
    sentences: Iterable[list[str]],
    language: str,
    skip_sentences: int,
    max_sentences: int | None,
) -> tuple[
    dict[str, Counter[str]],
    dict[str, Counter[str]],
    dict[str, Counter[str]],
    int,
    int,
]:
    bigrams: dict[str, Counter[str]] = defaultdict(Counter)
    trigrams: dict[str, Counter[str]] = defaultdict(Counter)
    surfaces: dict[str, Counter[str]] = defaultdict(Counter)
    sentence_count = 0
    token_count = 0
    consumed = 0

    for sentence_index, sentence in enumerate(sentences):
        if sentence_index < skip_sentences:
            continue
        if max_sentences is not None and consumed >= max_sentences:
            break
        consumed += 1
        keys = [normalize_key(token, language) for token in sentence]
        for key, surface in zip(keys, sentence):
            surfaces[key][surface] += 1
        for index, candidate in enumerate(keys):
            if index == 0:
                bigrams[BOS_CONTEXT][candidate] += 1
            else:
                bigrams[keys[index - 1]][candidate] += 1
            if index >= 2:
                context = keys[index - 2] + CONTEXT_SEPARATOR + keys[index - 1]
                trigrams[context][candidate] += 1
        sentence_count += 1
        token_count += len(sentence)
    return bigrams, trigrams, surfaces, sentence_count, token_count


def choose_surface_forms(surfaces: dict[str, Counter[str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key in sorted(surfaces):
        counts = surfaces[key]
        result[key] = min(counts, key=lambda value: (-counts[value], value.encode("utf-8")))
    return result


def quantize_score(count: int, total: int) -> int:
    raw = 255.0 + 8.0 * math.log2(count / total)
    return max(1, min(255, int(math.floor(raw + 0.5))))


def select_contexts(
    counts: dict[str, Counter[str]], threshold: int
) -> dict[str, list[tuple[str, int]]]:
    selected: dict[str, list[tuple[str, int]]] = {}
    for context in sorted(counts, key=lambda value: value.encode("utf-8")):
        candidates = counts[context]
        total = sum(candidates.values())
        kept = [
            (word, quantize_score(count, total), count)
            for word, count in candidates.items()
            if count >= threshold
        ]
        kept.sort(key=lambda item: (-item[2], item[0].encode("utf-8")))
        if kept:
            selected[context] = [(word, score) for word, score, _ in kept[:MAX_CANDIDATES]]
    return selected


def table_size_for(context_count: int) -> int:
    size = 1
    minimum = max(1, math.ceil(context_count / MAX_HASH_LOAD))
    while size < minimum:
        size <<= 1
    return size


def estimated_size(language: str, contexts: dict[str, list[tuple[str, int]]]) -> int:
    words = sorted({word for candidates in contexts.values() for word, _ in candidates})
    pool_size = sum(len(word.encode("utf-8")) for word in words)
    candidate_count = sum(len(candidates) for candidates in contexts.values())
    header_size = 18 + len(language.encode("utf-8"))
    return (
        header_size
        + 4 * (len(words) + 1)
        + pool_size
        + table_size_for(len(contexts)) * TABLE_ENTRY_SIZE
        + candidate_count * 4
    )


def prune_to_size(
    bigrams: dict[str, Counter[str]],
    trigrams: dict[str, Counter[str]],
    language: str,
    bigram_threshold: int,
    trigram_threshold: int,
    max_bytes: int,
) -> tuple[dict[str, list[tuple[str, int]]], int, int]:
    while True:
        selected_bigrams = select_contexts(bigrams, bigram_threshold)
        selected_trigrams = select_contexts(trigrams, trigram_threshold)
        overlap = selected_bigrams.keys() & selected_trigrams.keys()
        if overlap:
            raise ValueError(f"context encoding overlap: {min(overlap)!r}")
        contexts = {**selected_bigrams, **selected_trigrams}
        if estimated_size(language, contexts) <= max_bytes:
            return contexts, bigram_threshold, trigram_threshold
        if not contexts:
            raise ValueError("model cannot fit the requested size")
        if len(selected_trigrams) >= len(selected_bigrams):
            trigram_threshold += 1
        else:
            bigram_threshold += 1


def write_u24(output: BinaryIO, value: int) -> None:
    if not 0 <= value <= 0xFFFFFF:
        raise ValueError(f"word id exceeds u24: {value}")
    output.write(bytes((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF)))


def serialize_model(
    output_path: Path,
    language: str,
    contexts: dict[str, list[tuple[str, int]]],
    surface_forms: dict[str, str],
) -> tuple[int, int, int]:
    language_bytes = language.encode("utf-8")
    if len(language_bytes) > 255:
        raise ValueError("language tag is too long")

    candidate_keys = {word for candidates in contexts.values() for word, _ in candidates}
    words = sorted(
        (surface_forms[word] for word in candidate_keys),
        key=lambda value: value.encode("utf-8"),
    )
    if len(words) != len(candidate_keys):
        raise ValueError("surface-form selection produced duplicate candidate words")
    word_ids = {normalize_key(word, language): index for index, word in enumerate(words)}
    if word_ids.keys() != candidate_keys:
        raise ValueError("surface forms do not round-trip to candidate keys")

    pool = bytearray()
    offsets = [0]
    for word in words:
        pool.extend(word.encode("utf-8"))
        offsets.append(len(pool))

    context_items = sorted(contexts.items(), key=lambda item: item[0].encode("utf-8"))
    table_size = table_size_for(len(context_items))
    table = bytearray(table_size * TABLE_ENTRY_SIZE)
    candidate_rows: list[tuple[int, int]] = []
    seen_hashes: dict[int, str] = {}

    for context, candidates in context_items:
        key_hash = xxhash64(context.encode("utf-8"))
        if key_hash == 0:
            raise ValueError(f"xxHash64 reserved zero value for context {context!r}")
        previous = seen_hashes.setdefault(key_hash, context)
        if previous != context:
            raise ValueError(f"xxHash64 collision between {previous!r} and {context!r}")
        candidate_start = len(candidate_rows)
        for word, score in candidates:
            candidate_rows.append((word_ids[word], score))

        slot = key_hash & (table_size - 1)
        while struct.unpack_from("<Q", table, slot * TABLE_ENTRY_SIZE)[0] != 0:
            slot = (slot + 1) & (table_size - 1)
        struct.pack_into(
            "<QIB",
            table,
            slot * TABLE_ENTRY_SIZE,
            key_hash,
            candidate_start,
            len(candidates),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".tmp")
    with temporary_path.open("wb") as output:
        output.write(
            struct.pack(
                "<4sBBIII",
                MAGIC,
                VERSION,
                len(language_bytes),
                len(words),
                table_size,
                len(candidate_rows),
            )
        )
        output.write(language_bytes)
        output.write(struct.pack(f"<{len(offsets)}I", *offsets))
        output.write(pool)
        output.write(table)
        for word_id, score in candidate_rows:
            write_u24(output, word_id)
            output.write(bytes((score,)))
    os.replace(temporary_path, output_path)
    return len(words), table_size, len(candidate_rows)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", action="append", type=Path, default=[], help="UTF-8 text, .gz, or .xz corpus; repeatable")
    parser.add_argument("--lang", default="en", choices=("en", "fr", "ru"), help="model language")
    parser.add_argument("--output", type=Path, help="output .nwlm path")
    parser.add_argument("--tiny", action="store_true", help="build the deterministic built-in test fixture")
    parser.add_argument("--skip-sentences", type=int, default=0, help="reserve a deterministic corpus prefix for evaluation")
    parser.add_argument("--max-sentences", type=int, help="maximum training sentences after the skipped prefix")
    parser.add_argument("--bigram-threshold", type=int, default=8)
    parser.add_argument("--trigram-threshold", type=int, default=4)
    parser.add_argument("--max-bytes", type=int, default=3 * 1024 * 1024)
    args = parser.parse_args(argv)
    if args.tiny and args.corpus:
        parser.error("--tiny cannot be combined with --corpus")
    if not args.tiny and not args.corpus:
        parser.error("provide at least one --corpus or use --tiny")
    if args.output is None:
        if not args.tiny:
            parser.error("--output is required for corpus builds")
        args.output = Path(__file__).resolve().parent / "fixtures" / f"tiny_{args.lang}.nwlm"
    for name in ("skip_sentences", "bigram_threshold", "trigram_threshold", "max_bytes"):
        if getattr(args, name) < 0:
            parser.error(f"--{name.replace('_', '-')} must be non-negative")
    if args.max_sentences is not None and args.max_sentences <= 0:
        parser.error("--max-sentences must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if xxhash64(b"") != 0xEF46DB3751D8E999 or xxhash64(b"hello") != 0x26C7827D889F6DA3:
        raise AssertionError("xxHash64 self-test failed")

    if args.tiny:
        sentences: Iterable[list[str]] = (
            sentence
            for text in TINY_SENTENCES
            for sentence in tokenize_sentences(text)
        )
        bigram_threshold = 1
        trigram_threshold = 1
    else:
        missing = [str(path) for path in args.corpus if not path.is_file()]
        if missing:
            raise FileNotFoundError("missing corpus files: " + ", ".join(missing))
        sentences = iter_corpus_sentences(args.corpus)
        bigram_threshold = args.bigram_threshold
        trigram_threshold = args.trigram_threshold

    bigrams, trigrams, surfaces, sentence_count, token_count = count_ngrams(
        sentences,
        args.lang,
        args.skip_sentences,
        args.max_sentences,
    )
    if sentence_count == 0:
        raise ValueError("no training sentences were read")
    contexts, final_bigram_threshold, final_trigram_threshold = prune_to_size(
        bigrams,
        trigrams,
        args.lang,
        bigram_threshold,
        trigram_threshold,
        args.max_bytes,
    )
    word_count, table_size, candidate_count = serialize_model(
        args.output,
        args.lang,
        contexts,
        choose_surface_forms(surfaces),
    )
    print(f"wrote {args.output}")
    print(f"sentences={sentence_count} tokens={token_count}")
    print(
        f"contexts={len(contexts)} words={word_count} candidates={candidate_count} "
        f"table_size={table_size}"
    )
    print(
        f"bigram_threshold={final_bigram_threshold} "
        f"trigram_threshold={final_trigram_threshold} bytes={args.output.stat().st_size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
