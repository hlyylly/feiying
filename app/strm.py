"""生成 .strm 到 media_dir/<剧名>/Season NN/,内容指向缓存流服务(逻辑同 addshow.py)。"""
import glob
import os
from . import state


def _clear(d):
    """入库前清掉目录里旧的 .strm,避免换源重搜时混源/残留。"""
    for f in glob.glob(os.path.join(d, "*.strm")):
        try:
            os.remove(f)
        except OSError:
            pass


def _base():
    cfg = state.cfg
    return (cfg.stream_base or "http://127.0.0.1:%d" % cfg.stream_port).rstrip("/")


def write_movie(title, year, channel, mid, filename):
    cfg = state.cfg
    name = "%s (%d)" % (title, year) if year else title
    d = os.path.join(cfg.movie_dir, name)
    os.makedirs(d, exist_ok=True)
    _clear(d)
    ext = os.path.splitext(filename or "")[1] or ".mp4"
    url = "%s/%s/%d/movie%s" % (_base(), channel, mid, ext)
    open(os.path.join(d, name + ".strm"), "w", encoding="utf-8").write(url)
    return 1, d


def write_movie_parts(title, year, channel, parts):
    """飞牛不支持电影多文件分段拼接(当成多版本让选)。分段电影改放**剧集库**做成一季,
    每段=一集(part1=上集/E01…),飞牛按剧集放完自动续下一集,实现上下集顺序播。"""
    cfg = state.cfg
    name = "%s (%d)" % (title, year) if year else title
    d = os.path.join(cfg.media_dir, name, "Season 01")
    os.makedirs(d, exist_ok=True)
    _clear(d)
    for p in parts:
        ext = os.path.splitext(p.get("filename", "") or "")[1] or ".mp4"
        url = "%s/%s/%d/movie%s" % (_base(), channel, p["mid"], ext)
        open(os.path.join(d, "%s - S01E%02d.strm" % (name, p["ep"])), "w", encoding="utf-8").write(url)
    return len(parts), d


def write_strm(show, channel, episodes, season=1, clear=True):
    cfg = state.cfg
    base = (cfg.stream_base or "http://127.0.0.1:%d" % cfg.stream_port).rstrip("/")
    d = os.path.join(cfg.media_dir, show, "Season %02d" % season)
    os.makedirs(d, exist_ok=True)
    if clear:                 # 追更时 clear=False,只追加新集不清旧
        _clear(d)
    n = 0
    for e in episodes:
        mid, ep, fn = e["mid"], e["ep"], e.get("filename", "")
        ext = os.path.splitext(fn)[1] or ".mp4"
        url = "%s/%s/%d/ep%02d%s" % (base, channel, mid, ep, ext)
        p = os.path.join(d, "%s - S%02dE%02d.strm" % (show, season, ep))
        open(p, "w", encoding="utf-8").write(url)
        n += 1
    return n, d
