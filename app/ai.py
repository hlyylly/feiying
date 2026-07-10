"""deepseek(OpenAI 兼容): ① 片名规范化(自然语言→确切片名) ② 从候选消息里选正确成套剧集。
无 key / 失败时用正则兜底(逻辑取自 addshow.py)。"""
import json, re, httpx
from . import state


async def _chat(messages, json_mode=True, timeout=45):
    cfg = state.cfg
    if not cfg.deepseek_key:
        return None
    base = (cfg.deepseek_base or "https://api.deepseek.com/v1").rstrip("/")
    payload = {"model": cfg.deepseek_model, "messages": messages, "temperature": 0}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=timeout) as h:
        r = await h.post(base + "/chat/completions",
                         headers={"Authorization": "Bearer " + cfg.deepseek_key},
                         json=payload)
        # 部分 OpenAI 兼容服务(某些本地/Ollama 模型)不支持 response_format=json_object,
        # 报 4xx 时去掉它重试一次,最大化多接口兼容性(deepseek/OpenAI 正常路径不受影响)。
        if r.status_code >= 400 and json_mode:
            payload.pop("response_format", None)
            r = await h.post(base + "/chat/completions",
                             headers={"Authorization": "Bearer " + cfg.deepseek_key},
                             json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def normalize(text):
    """自然语言/模糊描述 → 规范片名。看着已是片名就直通,不花 token。"""
    text = (text or "").strip()
    if len(text) <= 12 and not re.search(r"[的了讲主演导演去年今年那部那个哪部]", text):
        return text
    try:
        out = await _chat([
            {"role": "system", "content": "你是影视搜索助手。把用户的模糊描述转成最可能的确切影视作品名称,只输出JSON {\"title\":\"片名\"}。"},
            {"role": "user", "content": text}])
        if out:
            return json.loads(out).get("title", text) or text
    except Exception as e:
        print("[ai] normalize 失败:", repr(e), flush=True)
    return text


# ---- 正则兜底(取自 addshow.py) ----
def _parse_ep(fn):
    for pat in [r"[Ee](\d{1,3})(?!\d)", r"第\s*(\d{1,3})\s*集", r"EP\.?(\d{1,3})"]:
        m = re.search(pat, fn or "")
        if m:
            return int(m.group(1))
    return None


def _title_hit(fn, q):
    core = re.sub(r"[\s\d季集第部]", "", q)
    return sum(1 for c in core if c in (fn or "")) >= max(1, len(core) - 1)


def _regex_select(film, candidates):
    from collections import defaultdict
    bych = defaultdict(dict)
    for c in candidates:
        fn = c["filename"]
        if re.search(r"[Ee]\d{1,3}\s*-\s*\d", fn):   # 合集范围打包文件,跳过
            continue
        ep = _parse_ep(fn)
        if ep and _title_hit(fn, film) and ep not in bych[c["channel"]]:
            bych[c["channel"]][ep] = c
    if not bych:
        return None
    ch = max(bych, key=lambda k: len(bych[k]))
    eps = bych[ch]
    return {"channel": ch, "season": 1,
            "episodes": [{"mid": eps[e]["mid"], "ep": e, "filename": eps[e]["filename"]}
                         for e in sorted(eps)]}


async def analyze(film, candidates):
    """判断电影还是剧集并挑资源。返回:
       剧集 {type:'series', channel, season, episodes:[{mid,ep,filename}]}
       电影 {type:'movie', channel, mid, filename, title, year}
       无匹配 None。无 key 时用正则兜底(只认剧集)。"""
    if not candidates:
        return None
    if not state.cfg.deepseek_key:
        r = _regex_select(film, candidates)
        if r:
            r["type"] = "series"
        return r
    lst = [{"mid": c["mid"], "channel": c["channel"], "filename": c["filename"],
            "sizeMB": round(c["size"] / 1048576)} for c in candidates[:150]]
    prompt = ("片名: %s\n候选视频消息(来自不可信的TG聚合搜索):\n%s\n\n"
              "⚠️重要:候选来自公开聚合搜索,里面**大量混有色情/擦边/垃圾内容,它们常盗用热门影视名当诱饵**"
              "(如把黄片命名成'沙丘.2021.mp4',或频道名含 NoMask/无码/AV 等)。你**只能看到文件名**,必须严格甄别。\n"
              "选片规则:\n"
              "· 只选**真正的正片**:文件名应符合正规影视命名——含年份、分辨率(1080p/2160p/4K)、来源(WEB-DL/BluRay/HDR/REMUX)或发布组等特征。\n"
              "· **凡疑似色情/擦边/写真/福利/无码/AV/番号/来源可疑/命名不像正规影视的,一律排除**,不管文件名写没写目标片名。\n"
              "· 剧集:挑成套正剧,排除预告/花絮/合集打包(单文件E01-10)/同名其它作品,优先集数最全+清晰度最高的**一个**频道,给每集集号。\n"
              "· 电影:挑**单个**最佳文件——确认是该影片+年份,清晰度最高(4K>1080),排除预告/花絮/枪版CAM/合集/彩蛋。\n"
              "· **若无法确信任何候选就是《%s》本身的正片,返回 none——宁可没有,也绝不能返回色情或错误内容。**\n"
              "严格只输出JSON,三选一:\n"
              "剧集: {\"type\":\"series\",\"channel\":\"频道\",\"season\":1,\"episodes\":[{\"mid\":123,\"ep\":1}]}\n"
              "电影: {\"type\":\"movie\",\"channel\":\"频道\",\"mid\":123,\"title\":\"沙丘\",\"year\":2021}\n"
              "无匹配: {\"type\":\"none\"}") % (film, json.dumps(lst, ensure_ascii=False), film)
    try:
        out = await _chat([{"role": "system", "content": "你是精准的影视资源整理器,严格只输出JSON。"},
                           {"role": "user", "content": prompt}])
        data = json.loads(out)
        bymid = {c["mid"]: c for c in candidates}
        typ = data.get("type")
        if typ == "movie":
            c = bymid.get(data.get("mid"))
            if not c:
                return _series_fallback(film, candidates)
            return {"type": "movie", "channel": c["channel"], "mid": c["mid"],
                    "filename": c["filename"], "title": data.get("title") or film,
                    "year": data.get("year")}
        if typ == "series":
            res = []
            for e in data.get("episodes") or []:
                c = bymid.get(e.get("mid"))
                if c and e.get("ep"):
                    res.append({"mid": c["mid"], "ep": int(e["ep"]), "filename": c["filename"]})
            if not res:
                return _series_fallback(film, candidates)
            channel = data.get("channel") or bymid[res[0]["mid"]]["channel"]
            res = [r for r in res if bymid[r["mid"]]["channel"] == channel] or res
            return {"type": "series", "channel": channel, "season": data.get("season", 1),
                    "episodes": sorted(res, key=lambda x: x["ep"])}
        return None   # type == none
    except Exception as e:
        print("[ai] analyze 失败,正则兜底:", repr(e), flush=True)
        return _series_fallback(film, candidates)


async def pick_deeplink(film, items):
    """深链bot条目挑选。items=[{token,title,bot}](title是描述如'沙丘 上集 英配 2021')。
    返回 {type:'movie|series|none', title, year, season, picks:[{i,ep}]}。i=items下标。"""
    lst = [{"i": i, "title": items[i]["title"]} for i in range(len(items))]
    if not state.cfg.deepseek_key:
        # 无AI兜底:标题含片名核心字 + 解析集/part
        core = re.sub(r"[\s\d季集第部]", "", film)
        picks = []
        for it in lst:
            t = it["title"]
            if all(ch in t for ch in core[:2]) if core else False:
                ep = _parse_ep(t) or (len(picks) + 1)
                picks.append({"i": it["i"], "ep": ep})
        if not picks:
            return None
        return {"type": "series", "title": film, "picks": picks}
    prompt = ("片名: %s\n搜索bot返回的资源条目(每条一个视频,i是下标):\n%s\n\n"
              "判断《%s》是**电影**还是**剧集**,从条目里挑出属于它的:\n"
              "⚠️同一部片常有**多个版本**(不同配音/字幕组/清晰度/发布组),每个版本各自被切成若干段"
              "(上集/下集、上/中/下、01/02…)。例:'上集'+'下集' 是一个版本;'上集 字幕组'+'下集 字幕组' 是**另一个**版本。\n"
              "· 电影:**只选其中ONE个版本**,并选该版本的**全部段**,按段顺序给ep(1,2,3…)。"
              "**绝对不要把不同版本的段混在一起**(否则会重复/错乱)。版本优先:有国语配音的完整版>字幕组>其它;同版本段要连续完整。\n"
              "· 剧集:选成套各集(01,02…),同样**只选一个版本/清晰度**,ep给集号。\n"
              "· 排除**不同作品**:如'剧版/剧集版/电视剧/番外/预告/花絮',以及'沙丘2'/'沙丘:预言'这类续作衍生;排除色情/擦边。\n"
              "· 若都不匹配返回 none。\n"
              "严格只输出JSON: {\"type\":\"movie|series|none\",\"title\":\"沙丘\",\"year\":2021,\"season\":1,"
              "\"version\":\"所选版本简述\",\"picks\":[{\"i\":0,\"ep\":1}]},picks按ep升序。") % (film, json.dumps(lst, ensure_ascii=False), film)
    try:
        out = await _chat([{"role": "system", "content": "你是精准的影视资源整理器,严格只输出JSON。"},
                           {"role": "user", "content": prompt}])
        data = json.loads(out)
        if data.get("type") not in ("movie", "series") or not data.get("picks"):
            return None
        picks = [{"i": int(p["i"]), "ep": int(p.get("ep") or (n + 1))}
                 for n, p in enumerate(data["picks"]) if p.get("i") is not None]
        print("[ai] pick_deeplink type=%s version=%s picks=%d" %
              (data["type"], data.get("version"), len(picks)), flush=True)
        return {"type": data["type"], "title": data.get("title") or film,
                "year": data.get("year"), "season": data.get("season", 1),
                "version": data.get("version"), "picks": picks}
    except Exception as e:
        print("[ai] pick_deeplink 失败,正则兜底:", repr(e), flush=True)
        core = re.sub(r"[\s\d季集第部]", "", film)
        picks = []
        for it in lst:
            t = it["title"]
            if (all(ch in t for ch in core[:2]) if core else False):
                ep = _parse_ep(t) or (len(picks) + 1)
                picks.append({"i": it["i"], "ep": ep})
        return {"type": "series", "title": film, "picks": picks} if picks else None


def _series_fallback(film, candidates):
    r = _regex_select(film, candidates)
    if r:
        r["type"] = "series"
    return r


async def select(film, candidates):
    """(旧接口,保留)只挑剧集。返回 {channel, season, episodes} 或 None。"""
    if not candidates:
        return None
    if not state.cfg.deepseek_key:
        return _regex_select(film, candidates)
    lst = [{"mid": c["mid"], "channel": c["channel"], "filename": c["filename"],
            "sizeMB": round(c["size"] / 1048576)} for c in candidates[:120]]
    prompt = ("片名: %s\n候选视频消息(来自TG群/频道):\n%s\n\n"
              "任务:挑出属于该片名的**成套正剧剧集**。排除:预告/花絮/彩蛋/合集打包(如单文件E01-10)/同名其它作品。"
              "同一部剧优先选集数最全、清晰度最高(4K>1080p)的那**一个**频道。为每集给出集数(整数)。"
              "只输出JSON: {\"channel\":\"频道名\",\"season\":1,\"episodes\":[{\"mid\":123,\"ep\":1}]},episodes按ep升序。"
              "没有任何匹配就返回 {\"episodes\":[]}。") % (film, json.dumps(lst, ensure_ascii=False))
    try:
        out = await _chat([{"role": "system", "content": "你是精准的影视资源整理器,严格只输出JSON。"},
                           {"role": "user", "content": prompt}])
        data = json.loads(out)
        eps = data.get("episodes") or []
        if not eps:
            return _regex_select(film, candidates)
        bymid = {c["mid"]: c for c in candidates}
        res = []
        for e in eps:
            c = bymid.get(e.get("mid"))
            if c and e.get("ep"):
                res.append({"mid": c["mid"], "ep": int(e["ep"]), "filename": c["filename"]})
        if not res:
            return _regex_select(film, candidates)
        channel = data.get("channel") or bymid[res[0]["mid"]]["channel"]
        # 只保留选定频道那部分(AI 可能混入别的频道)
        res = [r for r in res if bymid[r["mid"]]["channel"] == channel] or res
        return {"channel": channel, "season": data.get("season", 1),
                "episodes": sorted(res, key=lambda x: x["ep"])}
    except Exception as e:
        print("[ai] select 失败,正则兜底:", repr(e), flush=True)
        return _regex_select(film, candidates)
