# NextBoard language-model tools

These dependency-free Python tools build and evaluate the static `.nwlm` next-word models bundled with NextBoard. They intentionally share tokenization, normalization, and xxHash64 code so training and evaluation use the same keys as the Kotlin reader.

## Tiny fixture

Generate the deterministic reader-test fixture with:

```bash
python3 tools/lm/build_model.py --tiny
```

The default output is `tools/lm/fixtures/tiny_en.nwlm`. Tests may pass `--output` to place the fixture in a temporary build directory instead. `--tiny` uses embedded sentences and candidate thresholds of one; it is format coverage, not a quality model.

## Corpus build

The builder accepts plain UTF-8, `.gz`, and `.xz` monolingual text. Reserve the first 50,000 sentences for held-out evaluation and train from the remaining deterministic suffix:

```bash
python3 tools/lm/build_model.py \
  --lang en \
  --corpus tools/lm/corpus/en.txt.gz \
  --skip-sentences 50000 \
  --output app/src/main/assets/nextword/en.nwlm

python3 tools/lm/eval_model.py \
  --model app/src/main/assets/nextword/en.nwlm \
  --corpus tools/lm/corpus/en.txt.gz \
  --sentences 50000
```

The default candidate thresholds are eight for bigrams and four for trigrams. If the packed file exceeds 3 MiB, the builder deterministically raises the threshold for the larger context class until it fits. It retains at most four candidates per context.

Tokenization keeps Unicode letters, with ASCII apostrophe, U+2019, and hyphen allowed only inside a token. Periods, exclamation points, question marks, and newlines split sentences. Keys are lowercased, U+2019 is folded to ASCII apostrophe, and Russian `ё` is folded to `е` in keys while the most frequent candidate surface form is retained.

## Reproducibility check

Build the same inputs twice and compare the bytes:

```bash
python3 tools/lm/build_model.py --tiny --output /tmp/tiny-a.nwlm
python3 tools/lm/build_model.py --tiny --output /tmp/tiny-b.nwlm
cmp /tmp/tiny-a.nwlm /tmp/tiny-b.nwlm
```

All context and vocabulary traversal is byte-sorted. There is no randomized iteration or sampling.

## Corpus provenance

The production models will use OPUS OpenSubtitles monolingual exports. No production corpus has been downloaded yet. Before model assets are committed, this section must record each exact source URL, download date, compressed byte size, checksum, held-out split, and number of training sentences. Total corpus downloads must remain below approximately 2 GB.
