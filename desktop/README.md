# 飞影 Windows 桌面版

同一套核心（`app/`）换个壳：pywebview 应用窗口承载现有 Web 配置页 + 内嵌媒体库页，播放调 mpv 直连本机缓存流（`http://127.0.0.1:8890/...`），秒开/预取/边看边缓存/LRU 与 NAS 版完全一致。

## 与 NAS 版差异

| | NAS 版 | 桌面版 |
|---|---|---|
| 库 | .strm 目录，飞牛影视/Emby 扫 | `library.json` 索引 + 应用内媒体库页 |
| 播放 | 媒体服务器拉流 | 内置调 mpv 播同一个流地址 |
| 数据目录 | `/data`（挂载卷） | `%APPDATA%\feiying` |
| 追更 | 7×24 | 应用开着才追 |

## 开发运行

```powershell
python -m venv .venv
.venv\Scripts\pip install -r desktop\requirements.txt
.venv\Scripts\python -m desktop.shell
```

播放需要 mpv：把 `mpv.exe` 放 `desktop\bin\mpv.exe`（或设 `FEIYING_MPV`，或在 PATH 里）。
vmess 代理需要 xray：`desktop\bin\xray.exe`（或设 `XRAY_BIN`）。都不放也能跑，直连/外部代理模式不受影响。

## 打包发布

```powershell
.venv\Scripts\pip install pyinstaller
cd desktop && ..\.venv\Scripts\pyinstaller feiying.spec
# 把 mpv.exe、xray.exe 放进 dist\feiying\bin\，整个 dist\feiying 目录 zip 发 Release
```

- mpv: https://mpv.io/installation/ (windows builds，取 mpv.exe 即可)
- xray: https://github.com/XTLS/Xray-core/releases (Xray-windows-64.zip 里的 xray.exe)
