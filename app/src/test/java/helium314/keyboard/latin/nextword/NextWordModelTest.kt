// SPDX-License-Identifier: Apache-2.0 AND GPL-3.0-only
package helium314.keyboard.latin.nextword

import helium314.keyboard.latin.NgramContext
import helium314.keyboard.latin.NgramContext.WordInfo
import java.io.File
import java.nio.file.Files
import java.text.Normalizer
import java.util.Locale
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class NextWordModelTest {
    @Test
    fun readsTinyModelAndSentenceStart() {
        val model = NextWordModel.fromFile(tinyFixture)

        assertEquals("en", model.language)
        assertEquals(listOf("I", "Hello", "It's"), model.predict(NgramContext.BEGINNING_OF_SENTENCE, Locale.ENGLISH).map { it.word })
    }

    @Test
    fun usesTrigramThenBigramBackoff() {
        val model = NextWordModel.fromFile(tinyFixture)
        val exactContext = NgramContext(WordInfo("to"), WordInfo("want"))
        val missingTrigram = NgramContext(WordInfo("to"), WordInfo("unknown"))

        assertEquals(listOf("be", "go", "see"), model.predict(exactContext, Locale.ENGLISH).map { it.word })
        assertEquals(listOf("be", "go", "see"), model.predict(missingTrigram, Locale.ENGLISH).map { it.word })
        assertTrue(model.predict(missingTrigram, Locale.ENGLISH).all { it.score < 255 })
    }

    @Test
    fun normalizesApostrophesAndRejectsSensitiveContexts() {
        val model = NextWordModel.fromFile(tinyFixture)

        assertEquals("a", model.predict(NgramContext(WordInfo("IT’S")), Locale.ENGLISH).first().word)
        assertTrue(model.predict(NgramContext(WordInfo("user@example.com")), Locale.ENGLISH).isEmpty())
        assertTrue(model.predict(NgramContext(WordInfo("room42")), Locale.ENGLISH).isEmpty())
    }

    @Test
    fun rejectsTruncatedModel() {
        val truncated = Files.createTempFile("tiny-truncated", ".nwlm").toFile()
        truncated.writeBytes(tinyFixture.readBytes().copyOf(tinyFixture.length().toInt() - 1))

        assertFailsWith<NextWordModelFormatException> { NextWordModel.fromFile(truncated) }
    }

    @Test
    fun canonicalAccentsAndRussianYoUseTheSameKeys() {
        for ((locale, words) in listOf(Locale.FRENCH to listOf("CAFÉ", "DÉJÀ", "L’HÔTEL"),
            Locale.forLanguageTag("ru") to listOf("ЕЩЁ", "ВСЁ"))) {
            for (word in words) {
                assertEquals(NextWordModel.normalizeKey(word, locale),
                    NextWordModel.normalizeKey(Normalizer.normalize(word, Normalizer.Form.NFD), locale))
            }
        }
        assertEquals("все", NextWordModel.normalizeKey("ВСЕ\u0308", Locale.forLanguageTag("ru")))
    }

    @Test
    fun bundledFrenchModelAcceptsDecomposedAccents() {
        val model = NextWordModel.fromFile(File(repositoryRoot, "app/src/main/assets/nextword/fr.nwlm"))
        val canonical = model.predict(NgramContext(WordInfo("déjà")), Locale.FRENCH)
        assertTrue(canonical.isNotEmpty())
        assertEquals(canonical, model.predict(NgramContext(WordInfo("de\u0301ja\u0300")), Locale.FRENCH))
    }

    companion object {
        private val repositoryRoot: File by lazy {
            val workingDirectory = System.getProperty("user.dir") ?: error("missing user.dir")
            generateSequence(File(workingDirectory).absoluteFile) { it.parentFile }
                .firstOrNull { File(it, "tools/lm/build_model.py").isFile }
                ?: error("could not locate repository root")
        }
        private val tinyFixture: File by lazy {
            val output = Files.createTempFile("tiny-nextword", ".nwlm").toFile()
            val process = ProcessBuilder(
                "python3",
                File(repositoryRoot, "tools/lm/build_model.py").absolutePath,
                "--tiny",
                "--output",
                output.absolutePath
            ).redirectErrorStream(true).start()
            val processOutput = process.inputStream.bufferedReader().use { it.readText() }
            check(process.waitFor() == 0) { "tiny model build failed:\n$processOutput" }
            output
        }
    }
}
