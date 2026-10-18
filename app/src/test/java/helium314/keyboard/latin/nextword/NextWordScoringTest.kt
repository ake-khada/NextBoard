// SPDX-License-Identifier: Apache-2.0 AND GPL-3.0-only
package helium314.keyboard.latin.nextword

import helium314.keyboard.latin.SuggestedWords.SuggestedWordInfo
import helium314.keyboard.latin.dictionary.Dictionary
import helium314.keyboard.latin.utils.SuggestionResults
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class NextWordScoringTest {
    @Test
    fun keepsSingleLocaleScoresInStaticBand() {
        assertEquals(96, scoreNextWordCandidate(255, 1f))
        assertEquals(37, scoreNextWordCandidate(100, 1f))
        assertEquals(1, scoreNextWordCandidate(1, 1f))
    }

    @Test
    fun lowersScoresForLessLikelyLocales() {
        assertEquals(48, scoreNextWordCandidate(255, 0.5f))
        assertEquals(64, scoreNextWordCandidate(200, 0.85f))
        assertEquals(1, scoreNextWordCandidate(1, 0.5f))
    }

    @Test
    fun boundsInvalidWeightsWithoutEscapingStaticBand() {
        assertEquals(96, scoreNextWordCandidate(255, 2f))
        assertEquals(1, scoreNextWordCandidate(255, -1f))
        assertEquals(96, scoreNextWordCandidate(255, Float.NaN))
    }

    @Test
    fun preservesModelOrderThroughTheRealSuggestionComparator() {
        val candidates = listOf(NextWordCandidate("later", 231), NextWordCandidate("again", 229), NextWordCandidate("in", 226))
        for (weight in listOf(1f, 0.85f, 0.5f, 0.01f, 0f, Float.NaN)) {
            val ranked = NextWordModels.rankCandidates(candidates, weight)
            val merged = SuggestionResults(18, false, false).apply { addAll(ranked) }
            assertEquals(listOf("later", "again", "in"), merged.map { it.word })
            assertTrue(ranked.all { it.mScore in 1..96 && it.isKindOf(SuggestedWordInfo.KIND_PREDICTION) })
        }
    }

    @Test
    fun keepsBackoffBehindSpecificContextWithoutRaisingTheHistoryCeiling() {
        val ranked = NextWordModels.rankCandidates(listOf(NextWordCandidate("specific", 100), NextWordCandidate("backoff", 240)), 1f)
        val history = SuggestedWordInfo("learned", "", 97, SuggestedWordInfo.KIND_PREDICTION,
            Dictionary.PhonyDictionary(Dictionary.TYPE_USER_HISTORY), SuggestedWordInfo.NOT_AN_INDEX, SuggestedWordInfo.NOT_A_CONFIDENCE)
        val merged = SuggestionResults(18, false, false).apply { addAll(ranked); add(history) }
        assertEquals(listOf("learned", "specific", "backoff"), merged.map { it.word })
        assertTrue(NextWordModels.rankCandidates(emptyList(), 1f).isEmpty())
    }
}
