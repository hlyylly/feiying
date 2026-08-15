"""只靠 moov 判断 MP4 音视频交错得好不好,不用下整集。

有些压制版把音频和视频各自成块地写,同一时刻的画面和声音在文件里能隔上几百 MB。
本地播放无所谓(寻道免费),但走 .strm+HTTP 时播放器每跳一次就要重建一次 TCP,
每秒只跑得动几个请求,吞吐喂不饱码率,表现就是看两秒卡一下。

moov 里的 stco/co64 就是每个轨道的数据块偏移表,取回 moov 就能算,
不需要真的读到媒体数据,所以只下几 MB 就能判。
"""
import struct

_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl"}


def _boxes(buf, start=0, end=None):
    """遍历一层 box,产出 (类型, 内容起点, 内容终点)。"""
    if end is None:
        end = len(buf)
    off = start
    while off + 8 <= end:
        size = struct.unpack(">I", buf[off:off + 4])[0]
        typ = buf[off + 4:off + 8]
        body = off + 8
        if size == 1:                       # 64 位长度
            if off + 16 > end:
                return
            size = struct.unpack(">Q", buf[off + 8:off + 16])[0]
            body = off + 16
        elif size == 0:                     # 一直到文件尾
            size = end - off
        if size < 8 or off + size > end:
            return
        yield typ, body, off + size
        off += size


def top_level_layout(head):
    """从文件开头几十字节推断顶层 box 的位置,用来定位 moov。
    返回 [(类型, 起点, 长度)];遇到读不全的 box 就停,长度仍然是可信的。"""
    out = []
    off = 0
    while off + 8 <= len(head):
        size = struct.unpack(">I", head[off:off + 4])[0]
        typ = head[off + 4:off + 8]
        if size == 1:
            if off + 16 > len(head):
                break
            size = struct.unpack(">Q", head[off + 8:off + 16])[0]
        if size < 8:
            break
        out.append((typ, off, size))
        off += size
    return out


def box_header(buf):
    """读一个 box 的头,返回 (类型, 整体长度);读不出返回 None。"""
    if len(buf) < 8:
        return None
    size = struct.unpack(">I", buf[:4])[0]
    typ = buf[4:8]
    if size == 1:
        if len(buf) < 16:
            return None
        size = struct.unpack(">Q", buf[8:16])[0]
    if size < 8:
        return None
    return typ, size


def moov_range(head, file_size):
    """定位 moov,返回 (起点, 长度)。
    faststart 的片子 moov 在开头,能直接从 head 里读出来。
    没做 faststart 的 moov 在 mdat 后面,而 mdat 动辄上 GB,肯定超出了 head,
    这时返回 (下一个 box 的起点, None),让调用方去那儿读 16 字节头再来一次。
    真的没有就返回 None。"""
    off = 0
    for typ, boff, size in top_level_layout(head):
        if typ == b"moov":
            return boff, size
        off = boff + size
    if 0 < off < file_size:
        return off, None            # 还没走到头,moov 多半在这儿
    return None


def _chunk_offsets(stbl_buf, s, e):
    for typ, b, en in _boxes(stbl_buf, s, e):
        if typ in (b"stco", b"co64"):
            n = struct.unpack(">I", stbl_buf[b + 4:b + 8])[0]
            p = b + 8
            wide = typ == b"co64"
            step = 8 if wide else 4
            if p + n * step > en:
                n = max(0, (en - p) // step)
            fmt = ">Q" if wide else ">I"
            return [struct.unpack(fmt, stbl_buf[p + i * step:p + i * step + step])[0]
                    for i in range(n)]
    return []


def _handler(mdia_buf, s, e):
    for typ, b, en in _boxes(mdia_buf, s, e):
        if typ == b"hdlr" and b + 12 <= en:
            return mdia_buf[b + 8:b + 12]
    return None


def _find(buf, s, e, want):
    for typ, b, en in _boxes(buf, s, e):
        if typ == want:
            return b, en
    return None


def _u32s(buf, b, e, per):
    """读 full box 里的表:4字节版本标志 + 4字节条目数 + n×per 个 u32。"""
    if b + 8 > e:
        return []
    n = struct.unpack(">I", buf[b + 4:b + 8])[0]
    p = b + 8
    n = min(n, max(0, (e - p) // (4 * per)))
    return [struct.unpack(">%dI" % per, buf[p + i * 4 * per:p + (i + 1) * 4 * per])
            for i in range(n)]


def _track(buf, tb, te):
    """解析一条 trak,拿到判交错要用的四张表。"""
    mdia = _find(buf, tb, te, b"mdia")
    if not mdia:
        return None
    kind = _handler(buf, *mdia)
    mdhd = _find(buf, mdia[0], mdia[1], b"mdhd")
    if not kind or not mdhd:
        return None
    ver = buf[mdhd[0]]
    timescale = struct.unpack(">I", buf[mdhd[0] + (20 if ver == 1 else 12):
                                        mdhd[0] + (24 if ver == 1 else 16)])[0]
    minf = _find(buf, mdia[0], mdia[1], b"minf")
    stbl = _find(buf, minf[0], minf[1], b"stbl") if minf else None
    if not stbl or not timescale:
        return None
    sb, se = stbl
    stts = _find(buf, sb, se, b"stts")
    stsc = _find(buf, sb, se, b"stsc")
    return {
        "kind": kind.decode("latin1", "ignore"),
        "timescale": timescale,
        "stts": _u32s(buf, *stts, per=2) if stts else [],
        "stsc": [(x[0], x[1]) for x in (_u32s(buf, *stsc, per=3) if stsc else [])],
        "stco": _chunk_offsets(buf, sb, se),
    }


def _moov_body(moov_buf):
    start, end = 0, len(moov_buf)
    hb = box_header(moov_buf)
    if hb and hb[0] == b"moov":                 # 带头:进到 moov 里面去
        start = 16 if struct.unpack(">I", moov_buf[:4])[0] == 1 else 8
        end = min(end, hb[1])
    return start, end


def tracks(moov_buf):
    out = []
    s, e = _moov_body(moov_buf)
    for typ, b, en in _boxes(moov_buf, s, e):
        if typ == b"trak":
            t = _track(moov_buf, b, en)
            if t and t["stco"]:
                out.append(t)
    return out


def _offset_at(tr, sec):
    """这条轨道在第 sec 秒的数据,落在文件的哪个字节附近。"""
    stts, stsc, stco = tr["stts"], tr["stsc"], tr["stco"]
    if not stts or not stco:
        return None
    # 时间 → 样本序号
    target = sec * tr["timescale"]
    acc_t = acc_n = 0
    sample = None
    for cnt, delta in stts:
        span = cnt * delta
        if acc_t + span > target:
            sample = acc_n + (int((target - acc_t) // delta) if delta else 0)
            break
        acc_t += span
        acc_n += cnt
    if sample is None:
        sample = max(0, acc_n - 1)
    # 样本序号 → 块序号(stsc 是"从第几块起每块几个样本"的游程表)
    if not stsc:
        return stco[min(len(stco) - 1, sample)]
    seen = 0
    nch = len(stco)
    for i, (first, spc) in enumerate(stsc):
        last = (stsc[i + 1][0] - 1) if i + 1 < len(stsc) else nch
        runs = max(0, last - first + 1)
        if spc and seen + runs * spc > sample:
            k = (sample - seen) // spc
            return stco[min(nch - 1, first - 1 + k)]
        seen += runs * spc
    return stco[nch - 1]


def interleave_gap(moov_buf, duration=None):
    """同一时刻的画面和声音在文件里最远隔多少字节。
    必须按时间对齐来比 —— 两条轨道块数不同,按"各自进度百分比"比会全是 0,看不出毛病。
    交错正常的片子是 0~几 MB,坏的能到几百 MB。判不了返回 -1。"""
    ts = tracks(moov_buf)
    v = next((t for t in ts if t["kind"] == "vide"), None)
    a = next((t for t in ts if t["kind"] == "soun"), None)
    if not v or not a:
        return -1                      # 单轨(或没解出来),没有交错可言
    if not duration:
        duration = sum(c * d for c, d in v["stts"]) / float(v["timescale"] or 1)
    if duration <= 0:
        return -1
    worst = 0
    for frac in (0.2, 0.35, 0.5, 0.65, 0.8):
        t = duration * frac
        vo, ao = _offset_at(v, t), _offset_at(a, t)
        if vo is None or ao is None:
            continue
        worst = max(worst, abs(vo - ao))
    return worst
