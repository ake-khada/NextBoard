// SPDX-License-Identifier: Apache-2.0 AND GPL-3.0-only
package helium314.keyboard.latin.nextword

import kotlin.test.Test
import kotlin.test.assertEquals

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
}
