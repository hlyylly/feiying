package cc.aeio.feiying

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/** 前台服务:承载 python 核心(telethon + FastAPI + 缓存流 + 追更)。 */
class CoreService : Service() {

    companion object {
        @Volatile private var started = false
    }

    override fun onCreate() {
        super.onCreate()
        val chanId = "feiying_core"
        if (Build.VERSION.SDK_INT >= 26) {
            val chan = NotificationChannel(chanId, "飞影后台服务", NotificationManager.IMPORTANCE_LOW)
            (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(chan)
        }
        val notif: Notification = androidx.core.app.NotificationCompat.Builder(this, chanId)
            .setContentTitle("飞影运行中")
            .setContentText("TG 搜片 · 缓存流播 · 追更")
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setOngoing(true)
            .build()
        startForeground(1, notif)

        if (!started) {
            started = true
            Thread {
                try {
                    if (!Python.isStarted()) Python.start(AndroidPlatform(this))
                    val py = Python.getInstance()
                    py.getModule("mobile_shell").callAttr(
                        "start",
                        filesDir.absolutePath,
                        applicationInfo.nativeLibraryDir,
                        PlayerBridge(this)
                    )
                } catch (e: Throwable) {
                    // python 起不来时把 Kotlin 侧堆栈也落盘,MainActivity 会显示出来
                    try {
                        val dir = java.io.File(filesDir, "feiying").apply { mkdirs() }
                        java.io.File(dir, "kotlin_crash.log")
                            .appendText(android.util.Log.getStackTraceString(e) + "\n")
                    } catch (_: Exception) {}
                }
            }.apply { isDaemon = true }.start()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int) = START_STICKY
    override fun onBind(intent: Intent?): IBinder? = null
}
