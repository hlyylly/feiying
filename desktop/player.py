"""mpv 播放器封装:子进程调 mpv.exe 播缓存流 URL(mpv 自带窗口/seek/字幕/音轨)。
查找顺序: FEIYING_MPV 环境变量 → 打包目录 bin/mpv.exe → PATH。"""
import os
import shutil
import subprocess
import sys


def _base_dir():
    # PyInstaller 打包后资源在 exe 同级;开发态在本文件同级
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def mpv_path():
    p = os.environ.get("FEIYING_MPV")
    if p and os.path.exists(p):
        return p
    p = os.path.join(_base_dir(), "bin", "mpv.exe")
    if os.path.exists(p):
        return p
    return shutil.which("mpv")


def play(url, title=""):
    """调起 mpv 播放。找不到 mpv 抛 RuntimeError(由 /play 接口转成友好提示)。"""
    mpv = mpv_path()
    if not mpv:
        raise RuntimeError("没找到 mpv.exe:放到程序目录 bin\\mpv.exe,或设 FEIYING_MPV 环境变量")
    args = [mpv,
            "--force-window=immediate",       # 秒开窗口,不等首帧
            "--force-media-title=" + (title or "飞影"),
            "--cache=yes",
            url]
    subprocess.Popen(args, close_fds=True)
    print("[player] mpv 播放:", title, url, flush=True)
