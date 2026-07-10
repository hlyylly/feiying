"""把 vmess:// / vless:// 分享链接解析成 xray 配置,并以子进程跑 xray。
对外暴露 socks5 127.0.0.1:1080 + http 127.0.0.1:1081 给 telethon / deepseek 用。"""
import base64, json, os, subprocess, urllib.parse, time

XRAY_BIN = os.environ.get("XRAY_BIN", "/usr/local/bin/xray")
XRAY_CONFIG = "/tmp/xray_config.json"
SOCKS_PORT = 1080
HTTP_PORT = 1081


def _b64pad(s):
    return s + "=" * (-len(s) % 4)


def _stream_settings(net, tls, host, path, sni, htype):
    net = net or "tcp"
    ss = {"network": net, "security": "tls" if tls in ("tls", "reality", "xtls") else "none"}
    if ss["security"] == "tls":
        ss["tlsSettings"] = {"serverName": sni or host or "", "allowInsecure": False}
    if net == "ws":
        ss["wsSettings"] = {"path": path or "/", "headers": ({"Host": host} if host else {})}
    elif net in ("grpc", "gun"):
        ss["network"] = "grpc"
        ss["grpcSettings"] = {"serviceName": path or ""}
    elif net == "h2" or net == "http":
        ss["network"] = "http"
        ss["httpSettings"] = {"path": path or "/", "host": [host] if host else []}
    elif net == "tcp" and htype == "http":
        ss["tcpSettings"] = {"header": {"type": "http",
                                        "request": {"path": [path or "/"],
                                                    "headers": {"Host": [host] if host else []}}}}
    return ss


def parse_proxy_url(url):
    """外部代理地址 → telethon proxy 元组。支持 socks5://[user:pass@]host:port 和 http://。"""
    u = urllib.parse.urlparse(url.strip())
    scheme = {"socks5": "socks5", "socks": "socks5", "http": "http", "https": "http"}.get(u.scheme)
    if not scheme or not u.hostname:
        raise ValueError("代理地址格式应为 socks5://host:port 或 http://host:port: " + url[:40])
    t = (scheme, u.hostname, u.port or (1080 if scheme == "socks5" else 8080))
    if u.username:
        t += (True, u.username, u.password or "")
    return t


def telethon_proxy(cfg):
    """按配置决定 telethon 代理:外部代理 > 内置 xray > 直连(None)。"""
    if cfg.proxy_url:
        return parse_proxy_url(cfg.proxy_url)
    if cfg.vmess:
        return ("socks5", "127.0.0.1", SOCKS_PORT)
    return None


def parse_link(link):
    """返回一个 xray outbound dict。支持 vmess:// 和 vless://。"""
    link = link.strip()
    if link.startswith("vmess://"):
        raw = base64.b64decode(_b64pad(link[8:])).decode("utf-8", "ignore")
        c = json.loads(raw)
        net, tls, host = c.get("net", "tcp"), c.get("tls", ""), c.get("host", "")
        path, sni, htype = c.get("path", ""), c.get("sni", ""), c.get("type", "")
        return {
            "protocol": "vmess",
            "settings": {"vnext": [{
                "address": c["add"], "port": int(c["port"]),
                "users": [{"id": c["id"], "alterId": int(c.get("aid", 0)),
                           "security": c.get("scy", "auto")}],
            }]},
            "streamSettings": _stream_settings(net, tls, host, path, sni, htype),
        }
    if link.startswith("vless://"):
        u = urllib.parse.urlparse(link)
        q = dict(urllib.parse.parse_qsl(u.query))
        return {
            "protocol": "vless",
            "settings": {"vnext": [{
                "address": u.hostname, "port": u.port or 443,
                "users": [{"id": u.username, "encryption": q.get("encryption", "none"),
                           "flow": q.get("flow", "")}],
            }]},
            "streamSettings": _stream_settings(
                q.get("type", "tcp"), q.get("security", ""),
                q.get("host", ""), q.get("path", q.get("serviceName", "")),
                q.get("sni", ""), q.get("headerType", "")),
        }
    raise ValueError("不支持的链接(只支持 vmess:// / vless://): " + link[:20])


def build_config(link):
    out = parse_link(link)
    out["tag"] = "proxy"
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {"tag": "socks", "listen": "127.0.0.1", "port": SOCKS_PORT,
             "protocol": "socks", "settings": {"udp": True}},
            {"tag": "http", "listen": "127.0.0.1", "port": HTTP_PORT, "protocol": "http"},
        ],
        "outbounds": [out, {"protocol": "freedom", "tag": "direct"}],
    }


class XrayProxy:
    def __init__(self, link):
        self.link = link
        self.proc = None

    def start(self):
        if not self.link:
            return False
        cfg = build_config(self.link)
        json.dump(cfg, open(XRAY_CONFIG, "w"))
        if not os.path.exists(XRAY_BIN):
            print("[proxy] xray 二进制不存在:", XRAY_BIN, flush=True)
            return False
        self.proc = subprocess.Popen([XRAY_BIN, "run", "-c", XRAY_CONFIG],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        print("[proxy] xray 已启动 pid", self.proc.pid, flush=True)
        return True

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try: self.proc.kill()
                except Exception: pass
            self.proc = None

    def restart(self):
        self.stop()
        return self.start()

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None
