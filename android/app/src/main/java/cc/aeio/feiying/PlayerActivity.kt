package cc.aeio.feiying

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView

/** 内置播放器(Media3/ExoPlayer):硬解 + 标准 HTTP Range seek,配合缓存流拖动不卡。
 *  格式不支持时提示并可一键转外部播放器。 */
class PlayerActivity : AppCompatActivity() {
    private var player: ExoPlayer? = null
    private lateinit var view: PlayerView

    @SuppressLint("UnsafeOptInUsageError")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val url = intent.getStringExtra("url") ?: return finish()
        val title = intent.getStringExtra("title") ?: "飞影"

        view = PlayerView(this)
        view.setShowNextButton(false)
        view.setShowPreviousButton(false)

        // 左上角返回按钮,跟播放控制条一起显示/隐藏
        val back = TextView(this)
        back.text = "‹ 返回"
        back.textSize = 17f
        back.setTextColor(Color.WHITE)
        back.setPadding(44, 28, 44, 28)
        back.setBackgroundColor(0x66000000)
        back.setOnClickListener { finish() }
        view.setControllerVisibilityListener(
            PlayerView.ControllerVisibilityListener { v -> back.visibility = v })

        val root = FrameLayout(this)
        root.addView(view, FrameLayout.LayoutParams(-1, -1))
        val lp = FrameLayout.LayoutParams(-2, -2, Gravity.TOP or Gravity.START)
        lp.setMargins(24, 24, 0, 0)
        root.addView(back, lp)
        setContentView(root)

        val p = ExoPlayer.Builder(this).build()
        player = p
        view.player = p
        p.setMediaItem(
            MediaItem.Builder().setUri(Uri.parse(url))
                .setMediaMetadata(MediaMetadata.Builder().setTitle(title).build()).build())
        p.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                showFallback(url, title, error.errorCodeName)
            }
        })
        p.prepare()
        p.play()
    }

    /** 硬解不支持该格式时:提示 + 转外部播放器 */
    private fun showFallback(url: String, title: String, err: String) {
        val tv = TextView(this)
        tv.text = "内置播放器不支持该格式($err)\n\n点这里用外部播放器打开"
        tv.setPadding(60, 120, 60, 60)
        tv.textSize = 16f
        tv.setTextColor(0xFFE6E8EE.toInt())
        tv.setBackgroundColor(0xFF0F1115.toInt())
        tv.setOnClickListener {
            val i = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(Uri.parse(url), "video/*")
                putExtra("title", title)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(Intent.createChooser(i, "选择播放器"))
            finish()
        }
        setContentView(tv)
    }

    override fun onStop() {
        super.onStop()
        player?.pause()
    }

    override fun onDestroy() {
        super.onDestroy()
        player?.release()
        player = null
    }
}
