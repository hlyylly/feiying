# 飞影 Android 版

同一套核心（`app/`）的第三个壳：Chaquopy 把 Python 核心嵌进安卓 App，前台服务常驻，WebView 承载现有配置页 + 媒体库页，播放调**外部播放器**（推荐 [mpv-android](https://github.com/mpv-android/mpv-android) / VLC / nPlayer）播 `http://127.0.0.1:8890/...` 缓存流。

## 架构

```
MainActivity  WebView → http://127.0.0.1:8080 (现有 Web 页面原样)
CoreService   前台服务,线程里跑 mobile_shell.start()
              └ python: telethon + FastAPI + 缓存流 + 追更(与 NAS/桌面同一份 app/)
PlayerBridge  state.player 的安卓实现:Intent ACTION_VIEW → 弹播放器选择
jniLibs/libxray.so   安卓版 xray(vmess),从 nativeLibraryDir 执行
```

## 构建

本地不需要 Android Studio——GitHub Actions 云端构建：
Actions → build-android → Run workflow（填 release tag 则自动挂附件）。

CI 做的事：拷 `app/` 进 `src/main/python/`、下载安卓版 xray 放 jniLibs、`gradle assembleDebug`。

## 已知限制（v1 MVP）

- **仅 arm64**（近 8 年的手机都是）
- **TG 下载速度**：安卓上没有 cryptg，telethon 走纯 Python AES 解密，长视频拉流可能跑不满带宽。后续计划：给 Android 交叉编译 cryptg wheel
- **后台驻留**：追更/缓存依赖前台服务，国产 ROM 需要给「自启动/无限制后台」权限，否则锁屏久了会被杀
- **播放器需自装**：首次点播放会弹选择器；没有装播放器的话装个 mpv-android 或 VLC
- debug 签名（sideload 安装用），不能传应用商店
