// SPDX-License-Identifier: GPL-3.0-only
package helium314.keyboard.settings.dialogs

import android.os.Build
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import helium314.keyboard.keyboard.KeyboardSwitcher
import helium314.keyboard.keyboard.NextBoardStyle
import helium314.keyboard.keyboard.NextBoardStyle.Palette
import helium314.keyboard.keyboard.internal.KeyboardIconsSet
import helium314.keyboard.latin.R
import helium314.keyboard.latin.common.ColorType
import helium314.keyboard.latin.common.Colors
import helium314.keyboard.latin.utils.ResourceUtils
import helium314.keyboard.latin.utils.prefs

@Composable
fun NextBoardStyleDialog(onDismissRequest: () -> Unit) {
    val context = LocalContext.current
    var palette by rememberSaveable { mutableStateOf(Palette.NEXTBOARD) }
    var night by rememberSaveable { mutableStateOf(ResourceUtils.isNight(context.resources)) }
    val colors = remember(context, palette, night) { NextBoardStyle.previewColors(context, palette, night) }
    ThreeButtonAlertDialog(
        onDismissRequest = onDismissRequest,
        title = { Text(stringResource(R.string.apply_nextboard_style)) },
        confirmButtonText = stringResource(R.string.nextboard_style_apply),
        scrollContent = true,
        onConfirmed = {
            NextBoardStyle.apply(context.prefs(), palette)
            KeyboardIconsSet.needsReload = true
            KeyboardSwitcher.getInstance().setThemeNeedsReload()
        },
        content = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.nextboard_style_description))
                Text(stringResource(R.string.nextboard_style_preview), style = MaterialTheme.typography.labelLarge)
                KeyPreview(colors)
                Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)
                    .toggleable(night, role = Role.Switch, onValueChange = { night = it }), verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(stringResource(R.string.nextboard_style_dark_preview), Modifier.weight(1f))
                    Switch(checked = night, onCheckedChange = null)
                }
                Column(Modifier.selectableGroup()) {
                    val options = listOfNotNull(
                        Palette.NEXTBOARD to R.string.nextboard_style_tones,
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
                            Palette.WALLPAPER to R.string.nextboard_style_wallpaper else null,
                        Palette.KEEP to R.string.nextboard_style_keep
                    )
                    options.forEach { (option, label) ->
                        Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)
                            .selectable(palette == option, role = Role.RadioButton, onClick = { palette = option }),
                            verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = palette == option, onClick = null)
                            Text(stringResource(label), Modifier.padding(start = 12.dp))
                        }
                    }
                }
            }
        }
    )
}

/** Swatches for key roles, not an interactive keyboard or a preview of a custom background image. */
@Composable
private fun KeyPreview(colors: Colors) {
    Surface(color = Color(colors.get(ColorType.MAIN_BACKGROUND)), shape = RoundedCornerShape(16.dp)) {
        Row(Modifier.fillMaxWidth().padding(8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            val backgrounds = listOf(ColorType.KEY_BACKGROUND, ColorType.FUNCTIONAL_KEY_BACKGROUND,
                ColorType.SPACE_BAR_BACKGROUND, ColorType.ACTION_KEY_BACKGROUND)
            val texts = listOf("a", "?123", "␣", "↵")
            backgrounds.forEachIndexed { index, role ->
                val foreground = when (role) {
                    ColorType.SPACE_BAR_BACKGROUND -> colors.get(ColorType.SPACE_BAR_TEXT)
                    ColorType.ACTION_KEY_BACKGROUND -> colors.get(ColorType.ACTION_KEY_ICON)
                    else -> colors.get(ColorType.KEY_TEXT)
                }
                Surface(modifier = Modifier.weight(if (index == 2) 1.7f else 1f).height(48.dp),
                    shape = RoundedCornerShape(if (index >= 2) 24.dp else 12.dp),
                    color = Color(colors.get(role)), contentColor = Color(foreground)) {
                    Box(contentAlignment = Alignment.Center) { Text(texts[index]) }
                }
            }
        }
    }
}
