#!/usr/bin/env python3
"""Evaluate a .nwlm model on a deterministic held-out corpus prefix."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import struct
import sys

from build_model import (
    BOS_CONTEXT,
    CONTEXT_SEPARATOR,
    DEFAULT_SPLIT_SEED,
    MAGIC,
    TABLE_ENTRY_SIZE,
    TINY_SENTENCES,
    VERSION,
    iter_corpus_sentences,
    is_held_out,
    normalize_key,
    tokenize_sentences,
    xxhash64,
)


BACKOFF_PENALTY = 11
MAX_RESULTS = 3


@dataclass(frozen=True)
class Candidate:
    word: str
    score: int


class Model:
    def __init__(self, path: Path) -> None:
        self.data = path.read_bytes()
        if len(self.data) < 18:
            raise ValueError("model is shorter than its header")
        magic, version, language_length, self.word_count, self.table_size, candidate_count = struct.unpack_from(
            "<4sBBIII", self.data, 0
        )
        if magic != MAGIC or version != VERSION:
            raise ValueError("unsupported .nwlm magic or version")
        if self.table_size == 0 or self.table_size & (self.table_size - 1):
            raise ValueError("table size is not a power of two")
        position = 18
        self.language = self.data[position : position + language_length].decode("utf-8")
        position += language_length
        offsets_size = 4 * (self.word_count + 1)
        if position + offsets_size > len(self.data):
            raise ValueError("truncated word offsets")
        offsets = struct.unpack_from(f"<{self.word_count + 1}I", self.data, position)
        position += offsets_size
        pool_size = offsets[-1]
        if position + pool_size > len(self.data):
            raise ValueError("truncated word pool")
        pool = self.data[position : position + pool_size]
        self.words = [
            pool[offsets[index] : offsets[index + 1]].decode("utf-8")
            for index in range(self.word_count)
        ]
        position += pool_size
        self.table_offset = position
        self.candidates_offset = self.table_offset + self.table_size * TABLE_ENTRY_SIZE
        expected_size = self.candidates_offset + candidate_count * 4
        if expected_size != len(self.data):
            raise ValueError(f"model size mismatch: expected {expected_size}, got {len(self.data)}")
        self.candidate_count = candidate_count

    def lookup(self, context: str) -> list[Candidate]:
        key_hash = xxhash64(context.encode("utf-8"))
        if key_hash == 0:
            return []
        slot = key_hash & (self.table_size - 1)
        for _ in range(self.table_size):
            offset = self.table_offset + slot * TABLE_ENTRY_SIZE
            stored_hash, candidate_start, candidate_count = struct.unpack_from("<QIB", self.data, offset)
            if stored_hash == 0:
                return []
            if stored_hash == key_hash:
                if candidate_count > 4 or candidate_start + candidate_count > self.candidate_count:
                    raise ValueError("candidate range outside model")
                result: list[Candidate] = []
                for index in range(candidate_start, candidate_start + candidate_count):
                    candidate_offset = self.candidates_offset + index * 4
                    word_id = int.from_bytes(self.data[candidate_offset : candidate_offset + 3], "little")
                    score = self.data[candidate_offset + 3]
                    if word_id >= self.word_count or score == 0:
                        raise ValueError("invalid candidate row")
                    result.append(Candidate(self.words[word_id], score))
                return result
            slot = (slot + 1) & (self.table_size - 1)
        raise ValueError("model table contains no empty slot")

    def predict(self, previous: list[str]) -> list[Candidate]:
        if not previous:
            return self.lookup(BOS_CONTEXT)[:MAX_RESULTS]
        normalized = [normalize_key(word, self.language) for word in previous[-2:]]
        result: list[Candidate] = []
        seen: set[str] = set()
        if len(normalized) == 2:
            for candidate in self.lookup(normalized[0] + CONTEXT_SEPARATOR + normalized[1]):
                key = normalize_key(candidate.word, self.language)
                if key not in seen:
                    result.append(candidate)
                    seen.add(key)
                if len(result) == MAX_RESULTS:
                    return result
        for candidate in self.lookup(normalized[-1]):
            key = normalize_key(candidate.word, self.language)
            if key not in seen:
                result.append(Candidate(candidate.word, max(1, candidate.score - BACKOFF_PENALTY)))
                seen.add(key)
            if len(result) == MAX_RESULTS:
                break
        return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--corpus", action="append", default=[], type=Path)
    parser.add_argument("--tiny", action="store_true", help="evaluate against the builder's embedded fixture sentences")
    parser.add_argument("--sentences", type=int, default=50_000, help="held-out sentence count")
    parser.add_argument("--skip-sentences", type=int, default=0)
    parser.add_argument("--holdout-modulus", type=int, help="evaluate the fixed-seed 1/N sentence partition")
    parser.add_argument("--split-seed", type=int, default=DEFAULT_SPLIT_SEED)
    args = parser.parse_args(argv)
    if args.sentences <= 0 or args.skip_sentences < 0:
        parser.error("sentence counts must be positive")
    if args.holdout_modulus is not None and args.holdout_modulus < 2:
        parser.error("--holdout-modulus must be at least 2")
    if args.holdout_modulus is not None and args.skip_sentences:
        parser.error("--holdout-modulus cannot be combined with --skip-sentences")
    if args.tiny and args.corpus:
        parser.error("--tiny cannot be combined with --corpus")
    if not args.tiny and not args.corpus:
        parser.error("provide at least one --corpus or use --tiny")
    missing = [str(path) for path in args.corpus if not path.is_file()]
    if missing:
        parser.error("missing corpus files: " + ", ".join(missing))
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    model = Model(args.model)
    sentence_count = 0
    event_count = 0
    covered_count = 0
    top1_hits = 0
    top3_hits = 0
    skipped = 0
    sentences = (
        (sentence for text in TINY_SENTENCES for sentence in tokenize_sentences(text))
        if args.tiny
        else iter_corpus_sentences(args.corpus)
    )
    for source_index, sentence in enumerate(sentences):
        if args.holdout_modulus is not None and not is_held_out(
            source_index, args.holdout_modulus, args.split_seed
        ):
            continue
        if args.holdout_modulus is None and skipped < args.skip_sentences:
            skipped += 1
            continue
        if sentence_count >= args.sentences:
            break
        previous: list[str] = []
        for expected in sentence:
            predictions = model.predict(previous)
            expected_key = normalize_key(expected, model.language)
            predicted_keys = [normalize_key(candidate.word, model.language) for candidate in predictions]
            event_count += 1
            if predictions:
                covered_count += 1
            if predicted_keys and predicted_keys[0] == expected_key:
                top1_hits += 1
            if expected_key in predicted_keys[:3]:
                top3_hits += 1
            previous.append(expected)
        sentence_count += 1

    if sentence_count == 0 or event_count == 0:
        raise ValueError("no held-out sentences were evaluated")
    print(f"model={args.model} language={model.language} bytes={args.model.stat().st_size}")
    print(f"sentences={sentence_count} events={event_count} coverage={covered_count / event_count:.4%}")
    print(f"top1={top1_hits / event_count:.4%} ({top1_hits}/{event_count})")
    print(f"top3={top3_hits / event_count:.4%} ({top3_hits}/{event_count})")
    if sentence_count < args.sentences:
        print(f"warning: requested {args.sentences} sentences but corpus supplied {sentence_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
