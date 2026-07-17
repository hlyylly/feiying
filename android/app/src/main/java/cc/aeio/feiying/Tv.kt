package cc.aeio.feiying

import android.app.UiModeManager
import android.content.Context
import android.content.res.Configuration

object Tv {
    fun isTv(ctx: Context): Boolean {
        val ui = ctx.getSystemService(Context.UI_MODE_SERVICE) as UiModeManager
        return ui.currentModeType == Configuration.UI_MODE_TYPE_TELEVISION
    }
}
