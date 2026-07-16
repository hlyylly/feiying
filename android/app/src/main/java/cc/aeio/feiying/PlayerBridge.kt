package cc.aeio.feiying

import android.content.Context
import android.content.Intent
import android.net.Uri

/** python 侧 state.player 的安卓实现:发 Intent 让外部播放器(mpv-android/VLC/nPlayer)播缓存流。 */
class PlayerBridge(private val ctx: Context) {
    fun play(url: String, title: String) {
        val i = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(Uri.parse(url), "video/*")
            putExtra("title", title)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        val chooser = Intent.createChooser(i, "选择播放器").apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        ctx.startActivity(chooser)
    }
}
