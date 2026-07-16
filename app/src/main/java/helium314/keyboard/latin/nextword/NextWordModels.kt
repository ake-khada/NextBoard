// SPDX-License-Identifier: Apache-2.0 AND GPL-3.0-only
package helium314.keyboard.latin.nextword

import android.content.Context
import helium314.keyboard.latin.NgramContext
import helium314.keyboard.latin.SuggestedWords.SuggestedWordInfo
import helium314.keyboard.latin.dictionary.Dictionary
import helium314.keyboard.latin.settings.Settings
import helium314.keyboard.latin.utils.InputTypeUtils
import helium314.keyboard.latin.utils.Log
import java.io.IOException
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap

object NextWordModels {
    private const val TAG = "NextWord"
    private const val ASSET_DIRECTORY = "nextword"
    private const val STATIC_SCORE_CEILING = 96
    private const val TYPE_NEXT_WORD = "nextword"

    private val supportedLanguages = setOf("en", "fr", "ru")
    private val models = ConcurrentHashMap<String, NextWordModel>()
    private val unavailableLanguages = ConcurrentHashMap.newKeySet<String>()
    private val loadLock = Any()
    private val sourceDictionary = Dictionary.PhonyDictionary(TYPE_NEXT_WORD)

    fun getSuggestions(context: Context, locale: Locale, ngramContext: NgramContext): List<SuggestedWordInfo> {
        Settings.getValues()?.mInputAttributes?.let { inputAttributes ->
            if (inputAttributes.mIsPasswordField || InputTypeUtils.isUriOrEmailType(inputAttributes.mInputType)) {
                return emptyList()
            }
        }
        val language = locale.language.lowercase(Locale.ROOT)
        val model = getModel(context, language) ?: return emptyList()
        return model.predict(ngramContext, locale).map { candidate ->
            SuggestedWordInfo(
                candidate.word,
                "",
                (candidate.score * STATIC_SCORE_CEILING / 255).coerceAtLeast(1),
                SuggestedWordInfo.KIND_PREDICTION,
                sourceDictionary,
                SuggestedWordInfo.NOT_AN_INDEX,
                SuggestedWordInfo.NOT_A_CONFIDENCE
            )
        }
    }

    private fun getModel(context: Context, language: String): NextWordModel? {
        if (language !in supportedLanguages || language in unavailableLanguages) return null
        models[language]?.let { return it }
        synchronized(loadLock) {
            models[language]?.let { return it }
            if (language in unavailableLanguages) return null
            val started = System.nanoTime()
            return try {
                val assetPath = "$ASSET_DIRECTORY/$language.nwlm"
                val model = context.applicationContext.assets.openFd(assetPath).use(NextWordModel::fromAsset)
                if (model.language != language) {
                    throw NextWordModelFormatException(
                        "asset language ${model.language} does not match $language"
                    )
                }
                models[language] = model
                val elapsedMillis = (System.nanoTime() - started) / 1_000_000.0
                Log.i(
                    TAG,
                    "model-load lang=$language bytes=${model.fileSize} loadMs=${"%.3f".format(Locale.ROOT, elapsedMillis)}"
                )
                model
            } catch (exception: IOException) {
                unavailableLanguages.add(language)
                Log.e(TAG, "model-load failed lang=$language", exception)
                null
            } catch (exception: RuntimeException) {
                unavailableLanguages.add(language)
                Log.e(TAG, "model-load failed lang=$language", exception)
                null
            }
        }
    }
}
