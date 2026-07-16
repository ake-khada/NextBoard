# NEXTWORD_SPEC.md — Static n-gram next-word prediction for HeliBoard fork

Status: ready to implement. Integration points verified against Helium314/HeliBoard master, 2026-07-08. Line numbers will drift; class/function names are the anchors.

## Goal
After committing a word (space/punctuation), show up to 3 plausible next words in the suggestion strip, offline, for en/fr/ru, from a bundled pruned 3-gram model. Suggestions only — never autocorrect.

## Non-goals (v1)
- NO autocorrect behavior changes. Predictions use `SuggestedWordInfo.KIND_PREDICTION`; `Suggest.kt` already never auto-corrects when not composing.
- NO network. HeliBoard has no INTERNET permission; keep it that way.
- NO native/JNI code. Pure Kotlin over a memory-mapped buffer. C++ buys nothing here.
- NO ONNX / transformers / GGUF.
- NO custom personal learning. `UserHistoryDictionary` (TYPE_USER_HISTORY) already learns n-grams from the user with decay and feeds predictions. The static model only fixes cold start. Do not duplicate it.
- NO changes to the native dictionary format or dicttool.

## Verified integration map (package `helium314.keyboard.latin`)
- `dictionary/Dictionary.java` — base class; `getSuggestions(ComposedData, NgramContext, proximityInfoHandle, SettingsValuesForSuggestion, sessionId, weightForLocale, weightOfLangModelVsSpatialModel)` returns `ArrayList<SuggestedWordInfo>`.
- `DictionaryFacilitatorImpl.kt` — `getSuggestionResults(...)` fans out per `DictionaryGroup` (one per active locale), each group runs private `getSuggestions(...)` looping `ALL_DICTIONARY_TYPES` via `dictGroup.getDict(type)`. `DictionaryGroup` is a private class in the same file; its `subDicts` map is typed `ExpandableBinaryDictionary` (native-backed), so do NOT force the predictor in there.
- **Injection point:** inside the private per-group `getSuggestions(...)` in `DictionaryFacilitatorImpl.kt`: if `composedData.mTypedWord.isEmpty()`, query `NextWordModel` for `dictGroup.locale` and append results. ~10-line guarded block. This is the entire diff to existing suggestion code.
- `NgramContext.java` — carries up to `MAX_PREV_WORD_COUNT_FOR_N_GRAM = 3` previous words and has first-class beginning-of-sentence support (`BEGINNING_OF_SENTENCE_TAG = "<S>"`, `isBeginningOfSentenceContext`). Use it; do not re-derive context from the input connection.
- `inputlogic/InputLogic.java` (~line 1733) — empty-composing lookups are already gated on `settingsValues.mBigramPredictionEnabled` (pref `next_word_prediction`, `Settings.PREF_BIGRAM_PREDICTIONS`, default true) and `needsToLookupSuggestions()` (covers password/noSuggestion fields). **Reuse this pref. Zero new settings in v1.**
- `SuggestedWords.java` — `SuggestedWordInfo.KIND_PREDICTION = 8`.
- `app/build.gradle.kts` — add `androidResources { noCompress += "nwlm" }` so assets can be mmap'd via `AssetManager.openFd()` (fails on compressed assets).

## New files
```
app/src/main/java/helium314/keyboard/latin/nextword/NextWordModel.kt      // mmap reader + lookup
app/src/main/java/helium314/keyboard/latin/nextword/NextWordModels.kt    // per-locale cache, asset discovery
app/src/main/assets/nextword/en.nwlm
app/src/main/assets/nextword/fr.nwlm
app/src/main/assets/nextword/ru.nwlm
tools/lm/build_model.py    // corpus -> .nwlm
tools/lm/eval_model.py     // held-out top-k hit rate
tools/lm/README.md
```

## .nwlm binary format (little-endian, v1)
```
Header:  magic "NWLM", u8 version=1, u8 langTagLen, langTag bytes,
         u32 wordCount, u32 tableSize (power of 2), u32 candidateCount
Words:   u32 offsets[wordCount+1] into UTF-8 pool, then pool bytes
Table:   open-addressing, linear probe, load factor <= 0.7
         entry = { u64 keyHash (0 = empty), u32 candStart, u8 candCount }
Cands:   { u24 wordId, u8 score }  // score = quantized log-prob, 1..255
```
- keyHash = xxhash64 of normalized context: trigram `"w1\u0001w2"`, bigram `"w2"`, sentence start `"\u0002"` (maps from NgramContext BoS).
- 64-bit hashes over <1M contexts: collision odds ~1e-8, and a collision yields a wrong-but-valid word, not a crash. Acceptable; no key strings stored.
- Runtime: `AssetFileDescriptor` → `FileChannel.map()` → `MappedByteBuffer`. Zero parse, zero heap blowup, page cache does the work. Lookup = 1–2 probes + candidate reads.

## Runtime rules
1. Fire only when composing region is empty (already guaranteed at injection point) and a model exists for the group's locale.
2. Context from `NgramContext`: take last 2 words; if BoS flag set, use the `\u0002` key. Skip entirely if context contains digits or looks like URL/email fragments.
3. **Normalization (must exactly match the training pipeline):**
   - locale-aware lowercase for keys; U+2019 → U+0027; fr: elided forms (`j'ai`) are single tokens because `'` is a word connector; ru: fold ё→е in keys only, store candidates in most-frequent surface form.
4. Lookup: trigram first; if fewer than 3 candidates, back off to bigram with score penalty −11 (≈ stupid backoff α=0.4 in the quantization scale); dedupe against already-collected candidates case-insensitively.
5. Emit `SuggestedWordInfo(word, "", score, KIND_PREDICTION, dictionaryFacade, INDEX_OF_LAST_UNIGRAM_OR_NOT_A_MATCH, NOT_AN_AUTO_CORRECTION)` — mirror how existing prediction infos are built. Capitalization at sentence start is handled downstream; verify with a `. ` context in testing.
6. **Score calibration (one debug session, mandatory):** logcat-dump scores of user-history predictions for empty input, then map model scores into a band *below* user history so personalization always outranks the static model on ties. Make the band a single constant.
7. Max 3 candidates emitted per group. No allocation-heavy code in the lookup path.

## Training pipeline (tools/lm/)
- Corpus: OpenSubtitles (OPUS) per language — conversational register matches keyboard text far better than Wikipedia. Optionally blend Leipzig news 20%.
- Tokenizer mirrors keyboard word connectors: letters plus `'` and `-` inside tokens; sentence-split on `.!?` and newlines; emit `\u0002` as BoS token.
- Count 2-grams and 3-grams. Prune: trigram count ≥ 4, bigram count ≥ 8, keep top-4 candidates per context, then raise thresholds until file ≤ 3 MB per language.
- Score: `clamp(round(255 + 8 * log2(p(w|ctx))), 1, 255)`.
- `eval_model.py`: 50k held-out sentences → top-1/top-3 next-word hit rate. Gate: en top-3 ≥ 28%, fr/ru ≥ 22%. Print before/after on any pipeline change; this replaces "feels good" with a number.
- Pipeline is deterministic (sorted iteration, fixed seed) so models are reproducible from a corpus snapshot.

## Acceptance criteria
1. en: typing `I want to ` shows plausible continuations (go/see/be...) within one frame; no jank in systrace/logcat.
2. After `. ` predictions are sentence starters, capitalized.
3. fr: context `je vais` and elided contexts (`j'ai`) both resolve. ru: contexts typed with е match ё-corpus forms.
4. Password/email/URL fields: nothing fires (verify, don't assume — it's gated upstream but test it).
5. Toggling the existing "next_word_prediction" setting off kills it.
6. Choosing a prediction never replaces typed text; backspace after accepting behaves like normal word commit.
7. User-history predictions still appear and rank above static ones for learned bigrams.
8. APK grows ≤ 9 MB (3 × ≤3 MB, stored uncompressed). Cold model map < 10 ms.
9. Diff to existing files: `DictionaryFacilitatorImpl.kt` (one block), `build.gradle.kts` (noCompress). Everything else is new files — keeps upstream rebases cheap.

## Deferred (do not build now)
- User-importable `.nwlm` files (piggyback on HeliBoard's dictionary-import UX) instead of bundling — kills APK growth.
- 4-grams, class-based smoothing, neural reranker. A pruned trigram + user history likely saturates suggestion-strip quality; treat anything neural as a separate research track.

## Validation workflow
Build via `./gradlew :app:assembleDebug`, install to emulator, validate by real typing on-screen (no scripted swipe/tap for gesture-adjacent checks), one fix per commit.
