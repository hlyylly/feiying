# 飞影 feiying — 发个片名，自动入库到飞牛/Emby

在 Telegram **收藏夹发一个片名**（电影或剧名，甚至"诺兰讲原子弹那部"这种模糊描述），飞影 就自动帮你搜到、生成 `.strm`、进媒体库，**点开秒播、边看边缓存、剧集自动追更**。

把「TG 资源发现 → 智能匹配 → 缓存流播 → 飞牛/Emby 入库」全流程做成了一个自托管的小软件，一个 Docker 容器搞定。

## 能干什么
- 🔎 **多种资源源**：TG 频道直传视频 / 搜索 bot（如极搜）/ 深链令牌 bot（如 Youxiu_bot，自动翻页收全集）/ 多源兜底
- 🧠 **AI 智能匹配**（deepseek）：从一堆杂乱结果里挑出正确的正片，解析集数，自然语言片名理解，排除色情/盗名/预告/花絮
- 🎬 **电影 & 剧集自动分类**：电影进电影库、剧集进剧集库；分段电影做成上下集顺序播
- ⚡ **缓存流播**：秒开、多连接预取、看过的本地秒回、滚动预取下一集、LRU 自动淘汰
- 📺 **自动追更**：入库的剧自动追，定时查新集、只补新增、更新发到你的 TG 收藏夹
- 🔒 **内置翻墙**：填一个 vmess/vless 链接即可，内置 xray
- 🛠 **Web 配置/状态页** + 进程内自愈看门狗

## 你只需要准备 5 样
1. **TG 账户**（手机号，用来登录/搜索/拉流）
2. **一个资源 bot 或群/频道**（如 `Youxiu_bot`、极搜 `jisou`，或你自己的影视频道）
3. **一个 vmess:// 或 vless:// 链接**（翻墙节点）
4. **一个 deepseek API key**（AI 匹配；留空则退化为正则匹配）
5. **两个媒体文件夹**（剧集库 + 电影库，挂进容器，媒体服务器指向它们）

## 部署
```yaml
# docker-compose.yml
services:
  feiying:
    image: YOURNAME/feiying:latest      # ← 换成实际的 Docker Hub 镜像名
    container_name: feiying
    restart: unless-stopped
    user: "1000:1001"                  # ← 你媒体服务器用户的 uid:gid(飞牛 admin 一般是1000:1001,`id 用户名` 查)
    ports:
      - "8080:8080"                    # Web 配置/状态页
      - "8890:8890"                    # 缓存流服务(媒体库 .strm 指向这里)
    volumes:
      - ./data:/data                   # config/session/缓存(想放大盘就把它指到大盘)
      - /path/to/your/tv:/media/tv         # ← 剧集库目录
      - /path/to/your/movies:/media/movies # ← 电影库目录
```
```bash
docker compose up -d
# 浏览器打开 http://<主机IP>:8080
```

首次配置（Web 面板）：
1. **先填 vmess/vless 链接 → 保存**（代理起来才能连 TG）
2. **登录**：填手机号 → 发送验证码 → 手机 Telegram 收码 → 填码登录（有两步验证就填密码）
3. 填**资源 bot/群**、**deepseek key**、**stream_base**（见下），保存
4. 媒体服务器里建两个库：**电视剧** → `/media/tv` 挂载对应的宿主目录，**电影** → `/media/movies` 对应目录
5. 收藏夹发片名（或 Web 里输入）→ 入库 → 媒体库刷新即可观看

## 关键配置
- **stream_base**：媒体服务器访问缓存流服务的地址，必须是 `http://<主机局域网IP>:8890`，否则 .strm 指不到本机。
- **user (uid:gid)**：容器以你媒体服务器用户的身份写文件，写出的 `.strm` 媒体服务器才读得到。飞牛 admin 一般 `1000:1001`。
- **预取并发**：默认 4，**别调高于 5** —— 会触发 TG flood-wait 限流反而降速。
- **缓存放大盘**：`./data` 里含缓存，想放大盘就把 data 卷指到大盘目录。
- **update_interval_hours**：追更检查间隔，默认 12 小时。

## 注意（TG 账户）
- 本软件用你的号**独立登录**生成自己的 session = 多设备，和你手机/其它设备并存，不互踢。
- 别把同一份 session 复制到两台同时跑（会互踢/风控）。一实例一账号。

## 隐私
镜像**不含任何隐私**——session、deepseek key、节点、cookie 全在你挂载的 `./data` 卷里，不在镜像内。公开镜像是安全的。

## 结构
```
app/
  main.py        入口(uvicorn+telethon+流服务+看门狗+追更 同一事件循环)
  config.py      配置读写      state.py  共享状态     service.py 生命周期编排
  proxy.py       vmess/vless→xray          tg.py     登录(send_code/sign_in/2FA)
  ai.py          deepseek 匹配/判定(正则兜底)         finder.py 多源搜索(discover/materialize)
  cache_server.py 块缓存流播(预取/环形/滚动/LRU)      strm.py   生成 .strm
  control.py     收藏夹监听→入库           follows.py 追更列表   updater.py 定时追更
  watchdog.py    进程内自愈                web/      FastAPI 配置/状态页
```

## 技术栈
Python 3.12 · telethon+cryptg · FastAPI/uvicorn · 内置 xray · deepseek(OpenAI 兼容 API)

## License
MIT
