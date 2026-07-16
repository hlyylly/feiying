package cc.aeio.feiying

import android.content.Context
import android.content.Intent
import android.net.Uri

/** python 侧 state.player 的安卓实现:调内置 ExoPlayer 播放页(格式不支持时页内可转外部播放器)。 */
class PlayerBridge(private val ctx: Context) {
    fun play(url: String, title: String) {
        val i = Intent(ctx, PlayerActivity::class.java).apply {
            putExtra("url", url)
            putExtra("title", title)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        ctx.startActivity(i)
    }
}
