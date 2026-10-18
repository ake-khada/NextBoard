// SPDX-License-Identifier: GPL-3.0-only
package helium314.keyboard

import android.content.Context
import androidx.core.content.edit
import androidx.core.graphics.ColorUtils
import helium314.keyboard.keyboard.KeyboardTheme
import helium314.keyboard.keyboard.NextBoardStyle
import helium314.keyboard.latin.common.ColorType
import helium314.keyboard.latin.settings.Settings
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

@RunWith(RobolectricTestRunner::class)
class NextBoardStyleTest {
    private val prefs get() = RuntimeEnvironment.getApplication().getSharedPreferences("style-test", Context.MODE_PRIVATE)

    @Test fun applyPreservesInputPreferencesAndSavedCustomThemes() {
        prefs.edit {
            clear()
            putString(Settings.PREF_THEME_STYLE, KeyboardTheme.STYLE_MATERIAL)
            putBoolean(Settings.PREF_THEME_KEY_BORDERS, false)
            putString(Settings.PREF_THEME_COLORS, "my-day")
            putString(Settings.PREF_THEME_COLORS_NIGHT, "my-night")
            putBoolean(Settings.PREF_THEME_DAY_NIGHT, false)
            putFloat(Settings.PREF_FONT_SCALE, 1.2f)
            putBoolean(Settings.PREF_BIGRAM_PREDICTIONS, false)
            putString(Settings.PREF_USER_COLORS_PREFIX + "my-day", "saved-theme")
        }
        val original = prefs.all
        NextBoardStyle.apply(prefs, NextBoardStyle.Palette.KEEP)
        val changed = setOf(Settings.PREF_THEME_STYLE, Settings.PREF_THEME_KEY_BORDERS)
        assertEquals(original.filterKeys { it !in changed }, prefs.all.filterKeys { it !in changed })
        assertEquals(KeyboardTheme.STYLE_NEXTBOARD, prefs.getString(Settings.PREF_THEME_STYLE, null))
        assertTrue(prefs.getBoolean(Settings.PREF_THEME_KEY_BORDERS, false))
    }

    @Test fun bothPalettesApplyWithoutChangingDayNightPreference() {
        for ((palette, theme) in listOf(NextBoardStyle.Palette.NEXTBOARD to KeyboardTheme.THEME_NEXTBOARD,
            NextBoardStyle.Palette.WALLPAPER to KeyboardTheme.THEME_DYNAMIC)) {
            prefs.edit { clear(); putBoolean(Settings.PREF_THEME_DAY_NIGHT, false) }
            NextBoardStyle.apply(prefs, palette)
            assertEquals(theme, prefs.getString(Settings.PREF_THEME_COLORS, null))
            assertEquals(theme, prefs.getString(Settings.PREF_THEME_COLORS_NIGHT, null))
            assertEquals(false, prefs.getBoolean(Settings.PREF_THEME_DAY_NIGHT, true))
        }
    }

    @Test fun tonalPalettesKeepTextLegibleOnEachKeyRole() {
        for (night in listOf(false, true)) {
            val colors = NextBoardStyle.colors(KeyboardTheme.STYLE_NEXTBOARD, true, night)
            val pairs = listOf(
                ColorType.KEY_TEXT to ColorType.KEY_BACKGROUND,
                ColorType.KEY_HINT_TEXT to ColorType.KEY_BACKGROUND,
                ColorType.FUNCTIONAL_KEY_TEXT to ColorType.FUNCTIONAL_KEY_BACKGROUND,
                ColorType.SPACE_BAR_TEXT to ColorType.SPACE_BAR_BACKGROUND,
                ColorType.SUGGESTED_WORD to ColorType.STRIP_BACKGROUND,
                ColorType.ACTION_KEY_ICON to ColorType.ACTION_KEY_BACKGROUND
            )
            for ((text, background) in pairs)
                assertTrue(ColorUtils.calculateContrast(colors.get(text), colors.get(background)) >= 4.5,
                    "$text contrast in night=$night")
        }
    }
}
