# 飞牛 fnOS 原生应用包（.fpk）

给不会用 Docker 的飞牛用户提供的一键安装包。fpk 内部仍然是 Docker（fnOS 的 docker-project 机制托管 compose），镜像用 Docker Hub 的 `mn4940128/feiying:latest`，通过飞牛内置镜像加速拉取。

## 用户安装方式

1. 从 [Releases](https://github.com/hlyylly/feiying/releases) 下载 `feiying_x.y.z_x86_64.fpk`
2. 飞牛桌面 → 应用中心 → 右上角「手动安装」→ 选择 fpk 文件
3. 安装向导里填：剧集库目录、电影库目录（NAS 绝对路径）、媒体用户 uid:gid（默认 1000:1001）、Web/流端口（默认 8080/8890，被占用才需要改）
4. 安装完成后点桌面「飞影」图标进入 Web 配置页，照常配置代理/登录 TG/资源 bot

## 目录结构

```
project/
  manifest                    应用元数据(名称/版本/端口/图标入口)
  feiying.sc                  端口协议声明(8080 web + 8890 流)
  app/docker/docker-compose.yaml   实际运行的 compose(fnOS 注入 DOCKER_MIRROR/TRIM_PKGVAR)
  app/ui/config               fnOS 桌面图标 → http://IP:8080/
  cmd/main                    status 探测(docker inspect feiying-app)
  cmd/apply-settings          向导变量 → sed 改写 compose,并持久化到 PKGVAR
  cmd/install_callback        安装后:建数据目录+套用向导+chmod(回调非 root,不能 chown)
  cmd/upgrade_callback        升级后:重放已保存的目录/端口/uid 设置
  wizard/install              安装向导表单(目录/uid:gid/端口)
  config/resource             docker-project 声明 + 端口协议文件
```

## 构建

```bash
./build.sh        # 产出 feiying_<version>_x86_64.fpk
```

发新版：改 `project/manifest` 的 `version` → `./build.sh` → 传到 GitHub Release。镜像本身是 `latest`，容器重装时自动拉新，fpk 只需要在结构变化时发新版。

## 踩坑记录

- fnpack `build` 不打包根目录的 `*.sc`，`build.sh` 里手动补
- fnOS 只在**安装时** compose up 创建容器；`appcenter-cli start` 只是 `docker start`。所以端口/目录必须在安装向导阶段就定好（apply-settings 在 install_callback 里跑）
- install_callback 以包用户身份运行，`chown` 无效，用 `chmod 0777` 保证容器内任意 uid 可写
- fnOS 的 compose 项目名 = manifest appname。如果宿主机上已有同名 compose 项目（比如手动 docker compose 部署的），卸载 fpk 时会把同名项目的容器一起清掉——**不要与手动 Docker 部署混用**
- `appcenter-cli install-fpk` 走 CLI 不弹向导，全默认值；向导只在应用中心网页安装时出现
