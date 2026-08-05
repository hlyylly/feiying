"""配置读写。所有配置落地 DATA_DIR/config.json，单实例单账号。"""
import json, os, re

DATA_DIR = os.environ.get("FEIYING_DATA", "/data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
CACHE_DIR = os.path.join(DATA_DIR, "cache")

# api_id/hash 默认用公共的 TDesktop 值(my.telegram.org 建应用常失败),用户可覆盖
DEFAULTS = {
    "api_id": 2040,
    "api_hash": "b18441a1ff607e10a989891a5462e627",
    "phone": "",
    "session": "",            # telethon StringSession,登录后写入
    "source": "",             # 种子群/频道 username,多个用逗号分隔
    "vmess": "",              # vmess:// 或 vless:// 分享链接
    "proxy_url": "",          # 外部代理 socks5://host:port 或 http://host:port,填了则不起内置 xray;和 vmess 都留空=直连
    "deepseek_key": "",
    "deepseek_base": "https://api.deepseek.com",
    "deepseek_model": "deepseek-chat",
    "media_dir": "/media/tv",     # 剧集 .strm 输出根(容器内挂载)
    "movie_dir": "/media/movies", # 电影 .strm 输出根
    "stream_base": "",        # 飞牛访问缓存流服务的地址,如 http://192.168.3.8:8890
    "stream_port": 8890,
    "cache_quota_gb": 18,     # LRU 配额
    "prefetch_workers": 4,    # 预取并发,别调高(>5 触发 TG flood-wait)
    "dl_sem": 5,              # 全局下载并发上限
    "update_interval_hours": 12,  # 追更检查间隔(小时)
}


_self_ip = []


def _own_ip():
    if not _self_ip:
        import socket
        try:
            k = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            k.connect(("223.5.5.5", 80))
            _self_ip.append(k.getsockname()[0])
            k.close()
        except Exception:
            _self_ip.append("")
    return _self_ip[0]


def _is_container_ip(host):
    """172.16-31.x 且正好等于本机地址 = Docker bridge 里容器自己的 IP,容器外谁也到不了。
    host 网络模式下本机 IP 是真实局域网地址(192.168/10.x),不会命中这里。"""
    if not re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host or ""):
        return False
    return bool(_own_ip()) and _own_ip() == host


def normalize_stream_base(s):
    """规范化 stream_base 并校验。返回 (规范值, 错误提示或 None)。
    常见误填:把它当成一个**目录**填了 NAS 路径 —— 它是飞牛/播放器访问流服务的 URL。"""
    s = (s or "").strip().rstrip("/")
    if not s:
        return "", "未填 stream_base,.strm 会指向 127.0.0.1,飞牛和播放器都打不开"
    if s.startswith("/") or "\\" in s or re.match(r"^[A-Za-z]:", s):
        return "", "stream_base 是访问地址不是目录,应形如 http://192.168.3.8:8890"
    if not s.startswith(("http://", "https://")):
        s = "http://" + s                      # 只填了 IP:端口 → 自动补协议
    if not re.match(r"^https?://[^/\s:]+(:\d+)?$", s):
        return s, "stream_base 格式不对,应形如 http://192.168.3.8:8890(不带路径)"
    host = re.sub(r"^https?://", "", s).split(":")[0]
    if host in ("127.0.0.1", "localhost", "0.0.0.0"):
        return s, "stream_base 不能填 127.0.0.1/localhost,要填飞牛的**局域网 IP**"
    if _is_container_ip(host):
        return s, ("%s 是 Docker 容器自己的内网 IP,容器外(飞牛媒体库、PotPlayer)都到不了。"
                   "要填**飞牛主机**的局域网 IP,就是你现在打开这个配置页用的那个 IP" % host)
    return s, None


class Config:
    def __init__(self, data=None):
        self._d = dict(DEFAULTS)
        if data:
            self._d.update({k: v for k, v in data.items() if k in DEFAULTS})

    @classmethod
    def load(cls):
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        if os.path.exists(CONFIG_PATH):
            try:
                return cls(json.load(open(CONFIG_PATH, encoding="utf-8")))
            except Exception:
                pass
        return cls()

    def save(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        json.dump(self._d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)

    def __getattr__(self, k):
        try:
            return self.__dict__["_d"][k]
        except KeyError:
            raise AttributeError(k)

    def set(self, **kw):
        for k, v in kw.items():
            if k in DEFAULTS:
                self._d[k] = v
        self.save()

    def sources(self):
        """中英文逗号、分号、空格、换行都能当分隔符 —— 中文输入法打出的「，」很常见,
        只认英文逗号的话整串会被当成一个源名,全部解析失败。"""
        return [s.strip().lstrip("@")
                for s in re.split(r"[,，;；、\s]+", self.source or "") if s.strip()]

    def public_dict(self):
        """给 Web 用,隐藏敏感值。"""
        d = dict(self._d)
        d["session"] = "已登录" if d["session"] else ""
        if d["deepseek_key"]:
            d["deepseek_key"] = d["deepseek_key"][:6] + "..."
        return d
