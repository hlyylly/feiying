package cc.aeio.feiying

import android.annotation.SuppressLint
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.TextUtils
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import java.io.File

class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView
    private val url = "http://127.0.0.1:27125/"   // 与 mobile_shell.WEB_PORT 一致
    private val handler = Handler(Looper.getMainLooper())
    private var fails = 0

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val svc = Intent(this, CoreService::class.java)
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(svc) else startService(svc)

        web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.webViewClient = object : WebViewClient() {
            override fun onReceivedError(v: WebView?, req: WebResourceRequest?, err: WebResourceError?) {
                if (req?.isForMainFrame != true) return
                fails++
                // 前 20 次(约 30 秒)按"服务还在启动"处理:显示过渡页并重试;仍不通亮崩溃日志
                if (fails >= 20) { showCrash(); return }
                showSplash()
                handler.postDelayed({ web.loadUrl(url) }, 1500)
            }
        }
        setContentView(web)
        web.loadUrl(url)
    }

    private fun showSplash() {
        val html = "<html><body style='background:#0f1115;color:#8b93a7;display:flex;" +
            "align-items:center;justify-content:center;height:95vh;font-family:sans-serif'>" +
            "<div style='text-align:center'><div style='font-size:44px'>🎬</div>" +
            "<div style='margin-top:12px'>飞影核心服务启动中…</div></div></body></html>"
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
    }

    private fun showCrash() {
        fails = 0
        val py = File(filesDir, "feiying/android_crash.log")
        val kt = File(filesDir, "feiying/kotlin_crash.log")
        val txt = buildString {
            append("核心服务启动失败。请把下面的信息截图反馈:\n\n")
            if (kt.exists()) append(kt.readText()).append("\n")
            if (py.exists()) append(py.readText())
            if (!kt.exists() && !py.exists()) append("(没有崩溃日志——服务可能还在首次解包依赖,可点下方重试)")
        }
        val html = "<html><body style='background:#0f1115;color:#e6e8ee;font-family:monospace;" +
            "white-space:pre-wrap;word-break:break-all;padding:16px;font-size:12px'>" +
            TextUtils.htmlEncode(txt) +
            "<br><br><a href='$url' style='color:#58a6ff;font-size:16px'>↻ 重试</a></body></html>"
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
    }

    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }
}
