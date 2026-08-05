"""启动自检:把最容易配错、又最难自己发现的几项打进日志。

fpk/安卓用户看不到 docker logs,配错了往往只看到「入库成功但飞牛里没有」这类
无从下手的现象。最典型的三个坑:
  ① 媒体目录没真正挂载宿主目录 —— .strm 只写进容器可写层,飞牛根本看不到
  ② stream_base 填成目录/容器 IP/127.0.0.1 —— 写进 .strm 的地址谁也打不开
  ③ 目录属主和容器 uid:gid 对不上 —— 写入直接 Permission denied
"""
import os
from . import state, __version__
from .config import DATA_DIR, normalize_stream_base

IN_DOCKER = os.path.exists("/.dockerenv")
_ran = [False]


def run_once():
    """给 create_app 兜底用(desktop/安卓不走 app.main),已经跑过就别重复刷屏。"""
    if not _ran[0]:
        run()


def _check_dir(label, path):
    """返回 (一行说明, 问题描述或 None)。"""
    if not path:
        return "%s 未配置" % label, "%s 未配置" % label
    if not os.path.isdir(path):
        return ("%s %s → 目录不存在" % (label, path),
                "%s %s 不存在" % (label, path))
    if IN_DOCKER and not os.path.ismount(path):
        # 容器里绑定挂载的目录 st_dev 与父目录不同;不是挂载点 = 宿主没映射进来
        return ("%s %s → ⚠ 没挂载宿主目录" % (label, path),
                "%s(%s)没挂载宿主目录:.strm 只存在容器里,飞牛/Emby 看不到。"
                "去 fpk 安装向导把目录填成 NAS 绝对路径,然后**重新安装**(改了设置不重装不生效)"
                % (label, path))
    if not os.access(path, os.W_OK):
        return ("%s %s → ⚠ 不可写" % (label, path),
                "%s(%s)不可写:检查目录属主是否和容器的 uid:gid(默认 1000:1001)一致"
                % (label, path))
    return ("%s %s → %s可写" % (label, path,
                               "已挂载宿主目录, " if IN_DOCKER else ""), None)


def run():
    """打印自检结果,并把问题列表存进 state.problems 供 Web 首页展示。"""
    _ran[0] = True
    cfg = state.cfg
    problems, lines = [], []

    lines.append("飞影 v%s | 数据目录 %s%s"
                 % (__version__, DATA_DIR, " | 容器内运行" if IN_DOCKER else ""))

    for label, path in (("剧集目录", cfg.media_dir), ("电影目录", cfg.movie_dir)):
        line, prob = _check_dir(label, path)
        lines.append(line)
        if prob:
            problems.append(prob)

    if cfg.media_dir and cfg.media_dir == cfg.movie_dir:
        problems.append("剧集目录和电影目录填成了同一个:飞牛的电视剧库和电影库会互相扫到对方的内容,建议分开")
        lines.append("⚠ 剧集/电影目录是同一个,飞牛两个库会互相扫到对方")

    sb, sb_err = normalize_stream_base(cfg.stream_base)
    lines.append("stream_base %s → %s" % (cfg.stream_base or "(空)", sb_err or "OK"))
    if sb_err:
        problems.append(sb_err)

    srcs = cfg.sources()
    lines.append("资源源 %d 个: %s" % (len(srcs), ", ".join(srcs) or "(未配置)"))
    if not srcs:
        problems.append("没配资源源(种子群/频道/搜索bot),搜不到任何东西")

    lines.append("AI: %s | 模型 %s"
                 % ("已配 key" if (cfg.deepseek_key or "").strip() else "未配 key(退化为正则匹配)",
                    cfg.deepseek_model))
    lines.append("代理: %s | TG: %s"
                 % ("外部代理" if cfg.proxy_url else "内置 xray" if cfg.vmess else "直连",
                    "已登录" if cfg.session else "未登录"))

    for ln in lines:
        print("[自检] " + ln, flush=True)
    if problems:
        print("[自检] ⚠ 共 %d 处需要处理,见上面带 ⚠ 的行" % len(problems), flush=True)
    else:
        print("[自检] 配置看起来没问题", flush=True)

    state.problems = problems
    return problems
