// SPDX-License-Identifier: GPL-3.0-only
package helium314.keyboard.keyboard

import android.content.Context
import android.content.SharedPreferences
import android.graphics.drawable.Drawable
import android.os.Build
import androidx.core.content.edit
import androidx.core.graphics.toColorInt
import helium314.keyboard.latin.common.Colors
import helium314.keyboard.latin.common.DefaultColors
import helium314.keyboard.latin.settings.Defaults
import helium314.keyboard.latin.settings.Settings
import helium314.keyboard.latin.utils.prefs

/** Appearance choices only: applying a style must never reset layouts or input preferences. */
object NextBoardStyle {
    enum class Palette { NEXTBOARD, WALLPAPER, KEEP }

    fun apply(prefs: SharedPreferences, palette: Palette) {
        val theme = when (palette) {
            Palette.NEXTBOARD -> KeyboardTheme.THEME_NEXTBOARD
            Palette.WALLPAPER -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
                KeyboardTheme.THEME_DYNAMIC else KeyboardTheme.THEME_NEXTBOARD
            Palette.KEEP -> null
        }
        prefs.edit {
            putString(Settings.PREF_THEME_STYLE, KeyboardTheme.STYLE_NEXTBOARD)
            putBoolean(Settings.PREF_THEME_KEY_BORDERS, true)
            if (theme != null) {
                putString(Settings.PREF_THEME_COLORS, theme)
                putString(Settings.PREF_THEME_COLORS_NIGHT, theme)
            }
        }
    }

    fun previewColors(context: Context, palette: Palette, isNight: Boolean): Colors {
        val prefs = context.prefs()
        val theme = when (palette) {
            Palette.NEXTBOARD -> KeyboardTheme.THEME_NEXTBOARD
            Palette.WALLPAPER -> KeyboardTheme.THEME_DYNAMIC
            Palette.KEEP -> if (isNight)
                prefs.getString(Settings.PREF_THEME_COLORS_NIGHT, Defaults.PREF_THEME_COLORS_NIGHT)!!
            else prefs.getString(Settings.PREF_THEME_COLORS, Defaults.PREF_THEME_COLORS)!!
        }
        return KeyboardTheme.getThemeColors(theme, KeyboardTheme.STYLE_NEXTBOARD,
            Settings.getDayNightContext(context, isNight), prefs, isNight, hasBorders = true)
    }

    fun colors(style: String, borders: Boolean, night: Boolean, background: Drawable? = null): Colors =
        DefaultColors(
            style, borders,
            (if (night) "#A8C7FA" else "#C2E7FF").toColorInt(), // primary container / action
            (if (night) "#14171C" else "#F0F4F9").toColorInt(), // surface
            (if (night) "#30343B" else "#FFFFFF").toColorInt(), // character keys
            (if (night) "#3D4756" else "#DEE3EB").toColorInt(), // secondary container
            (if (night) "#3D4756" else "#DFE7F2").toColorInt(), // space
            (if (night) "#E3E3E3" else "#1F1F1F").toColorInt(), // on surface
            (if (night) "#C4C7C5" else "#444746").toColorInt(), // on surface variant
            gesture = (if (night) "#A8C7FA" else "#0B57D0").toColorInt(),
            keyboardBackground = background
        )
}
