"""本地媒体库索引(DATA_DIR/library.json)。
NAS 版的"库"是 .strm 目录(给飞牛影视/Emby 扫),desktop 版没有外部媒体服务器,
用这份索引做应用内的库页面;入库时两个出口都写,互不影响。"""
import json, os, time
from .config import DATA_DIR

PATH = os.path.join(DATA_DIR, "library.json")


def items():
    try:
        return json.load(open(PATH, encoding="utf-8"))
    except Exception:
        return []


def _save(lst):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    json.dump(lst, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def _find(lst, lid):
    for it in lst:
        if it["id"] == lid:
            return it
    return None


def add_series(title, channel, episodes, season=1):
    """episodes=[{mid,ep,filename}];已存在则合并新集(追更走这里,clear 语义与 strm 一致:入库重写、追更合并)。"""
    lst = items()
    lid = "s:%s:%d" % (title, season)
    it = _find(lst, lid)
    eps = {e["ep"]: {"ep": e["ep"], "mid": e["mid"], "filename": e.get("filename", "")}
           for e in episodes}
    if it is None:
        it = {"id": lid, "type": "series", "title": title, "season": season,
              "channel": channel, "episodes": [], "ts": int(time.time())}
        lst.insert(0, it)
    else:
        it["channel"] = channel
        for e in it["episodes"]:
            eps.setdefault(e["ep"], e)
    it["episodes"] = [eps[k] for k in sorted(eps)]
    _save(lst)
    return it


def add_movie(title, year, channel, mid, filename):
    lst = items()
    lid = "m:%s:%s" % (title, year or "")
    lst = [x for x in lst if x["id"] != lid]
    it = {"id": lid, "type": "movie", "title": title, "year": year,
          "channel": channel, "mid": mid, "filename": filename or "",
          "ts": int(time.time())}
    lst.insert(0, it)
    _save(lst)
    return it


def add_movie_parts(title, year, channel, parts):
    """分段电影:与 strm 同语义,当成一季剧存(part=集)。"""
    return add_series("%s (%s)" % (title, year) if year else title, channel,
                      [{"mid": p["mid"], "ep": p["ep"], "filename": p.get("filename", "")}
                       for p in parts])


def remove(lid):
    lst = [x for x in items() if x["id"] != lid]
    _save(lst)


def series_eps(title, season=1):
    """给 updater 用:库里这部剧已有的集号(desktop 版没有 .strm,以此为准)。"""
    it = _find(items(), "s:%s:%d" % (title, season))
    return {e["ep"] for e in it["episodes"]} if it else set()
