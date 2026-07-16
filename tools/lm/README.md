# NextBoard language-model tools

These dependency-free Python tools build and evaluate the static `.nwlm` next-word models bundled with NextBoard. They intentionally share tokenization, normalization, and xxHash64 code so training and evaluation use the same keys as the Kotlin reader.

## Tiny fixture

Generate the deterministic reader-test fixture with:

```bash
python3 tools/lm/build_model.py --tiny
```

The default output is `tools/lm/fixtures/tiny_en.nwlm`. Tests may pass `--output` to place the fixture in a temporary build directory instead. `--tiny` uses embedded sentences and candidate thresholds of one; it is format coverage, not a quality model.

## Corpus build

The builder accepts plain UTF-8, `.gz`, and `.xz` monolingual text. Use the fixed-seed SplitMix64 partition to distribute held-out sentences across an ordered subtitle archive. With roughly 10 million sentences, modulus 200 yields about 50,000 held-out sentences:

```bash
python3 tools/lm/build_model.py \
  --lang en \
  --corpus tools/lm/corpus/en.txt.gz \
  --holdout-modulus 200 \
  --max-sentences 10000000 \
  --output app/src/main/assets/nextword/en.nwlm

python3 tools/lm/eval_model.py \
  --model app/src/main/assets/nextword/en.nwlm \
  --corpus tools/lm/corpus/en.txt.gz \
  --sentences 50000 \
  --holdout-modulus 200
```

The default candidate thresholds are eight for bigrams and four for trigrams. If the packed file exceeds 3 MiB, the builder deterministically raises the admission threshold for the larger context class until it fits. Candidates within an admitted context still have to meet the base 8/4 threshold, which preserves useful second and third choices instead of wasting space at a power-of-two table boundary. It retains at most four candidates per context.

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

Production models were built on 2026-07-16 from the official OPUS OpenSubtitles v2016 Moses packages. The later v2024 release does not provide compiled plain-text downloads. OPUS asks users of OpenSubtitles data to acknowledge [OpenSubtitles](http://www.opensubtitles.org/) and the Lison–Tiedemann 2016 corpus paper.

Downloaded archives (1,508,876,295 bytes total):

| Languages used | URL | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| en, fr | `https://object.pouta.csc.fi/OPUS-OpenSubtitles/v2016/moses/en-fr.txt.zip` | 1,058,609,221 | `b353aa9c49a5a33f56c410e5be61ec54ea619e3bc1c1d632a55309d75043b32b` |
| ru | `https://object.pouta.csc.fi/OPUS-OpenSubtitles/v2016/moses/fr-ru.txt.zip` | 450,267,074 | `1f85f8ec9843971b5e5f08dfd4bebf2034eef489028d7ecbd9285e0d9bb54b3c` |

For each language, the first 10,050,000 aligned lines of the named archive member were recompressed with `gzip -n`. These snapshots are build inputs, not repository files:

| Language | Archive member | Snapshot bytes | Snapshot SHA-256 |
| --- | --- | ---: | --- |
| en | `OpenSubtitles.en-fr.en` | 130,687,358 | `2622ba1b817b174cece95f3e0750e11c94ff45fd3e2aa4d983f5d1ced7c598bd` |
| fr | `OpenSubtitles.en-fr.fr` | 125,816,466 | `e974c8e61faf5693aa93eef8ec794e8baf3f8c9dcdb494e77f09a2f71f993d12` |
| ru | `OpenSubtitles.fr-ru.ru` | 173,760,945 | `98365df8bd730d3feb15ca392cc221a606b5cf1178a458ed936d1dbf6e3329cd` |

The fixed split seed is `0x4E574C4D`; `--holdout-modulus 200` assigns approximately one sentence in 200 to evaluation. Each model uses exactly 10,000,000 non-held-out training sentences. Evaluation stops after 50,000 held-out sentences.

## Production results

| Language | Model bytes | Admission thresholds (bi/tri) | Top-1 | Top-3 | SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| en | 2,784,269 | 8 / 11 | 16.6249% | 28.4482% | `116735ce9bc378f05fd97ffdf365f7d16b69823b5513dd44a72955ed68425855` |
| fr | 2,793,815 | 8 / 12 | 15.7507% | 27.3222% | `eb4795692ddd1d4488dfbb813483f0902536164b3c22872491c2ff4bd12a3235` |
| ru | 2,843,773 | 8 / 12 | 13.8996% | 23.1018% | `189cb7f07c943970f5a35ce9ce2efed9291be3428d9db4b40ca1fa091ca50f4e` |

All model files remain below 3 MiB. English clears the 28% top-3 gate; French and Russian clear their 22% gates.
