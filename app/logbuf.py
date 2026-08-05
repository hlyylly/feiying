"""内存环形日志:把 stdout/stderr 接一份到内存,给 Web 的 /logs 看。
fpk/安卓装的用户进不去 docker logs,出问题只能干瞪眼,所以日志得能在网页上看到。"""
import re, sys, time
from collections import deque

BUF = deque(maxlen=800)
_installed = False

# 日志页在局域网裸奔(整个配置页都没鉴权),别把密钥/手机号漏出去。
# 手机号规则必须写窄:日志里满是消息 id、文件大小、UUID 这类长数字,
# 一个宽松的「一串数字」规则会把它们也打码,日志就没法看了。
_MASK = (
    (re.compile(r"(sk-[A-Za-z0-9]{4})[A-Za-z0-9]{8,}"), r"\1***"),
    (re.compile(r"(\+\d{2,3})\d{4,}(\d{2})(?!\d)"), r"\1***\2"),        # +8613812345678
    (re.compile(r"(?<![\d\w])(1[3-9])\d{7}(\d{2})(?![\d\w])"), r"\1***\2"),  # 11 位手机号
)


def _scrub(s):
    for pat, rep in _MASK:
        s = pat.sub(rep, s)
    return s


class _Null:
    """desktop 的 GUI 模式下 sys.stdout 可能是 None。"""
    encoding = "utf-8"

    def write(self, s):
        return len(s or "")

    def flush(self):
        pass

    def isatty(self):
        return False


class _Tee:
    def __init__(self, orig):
        self._orig = orig

    def write(self, s):
        try:
            self._orig.write(s)
        except Exception:
            pass
        for ln in (s or "").splitlines():
            if ln.strip():
                BUF.append("%s %s" % (time.strftime("%m-%d %H:%M:%S"), _scrub(ln)))
        return len(s or "")

    def flush(self):
        try:
            self._orig.flush()
        except Exception:
            pass

    def isatty(self):
        return False

    def __getattr__(self, k):
        return getattr(self._orig, k)


def install():
    """幂等。main 和 create_app 都会调,谁先跑到算谁的。"""
    global _installed
    if _installed:
        return
    _installed = True
    sys.stdout = _Tee(sys.stdout or _Null())
    sys.stderr = _Tee(sys.stderr or _Null())


def tail(n=400):
    return list(BUF)[-n:]
