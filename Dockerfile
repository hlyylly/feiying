# xray 二进制从 teddysun/xray 拷贝(飞牛上能拉,避免 github 下载)
FROM teddysun/xray:latest AS xraybin
FROM mwader/static-ffmpeg:7.1 AS ffbin

FROM python:3.12-slim
COPY --from=xraybin /usr/bin/xray /usr/local/bin/xray
# 坏交错片源转封装用(-c copy 不解码);静态二进制,不走 apt 免得拖一堆依赖
COPY --from=ffbin /ffmpeg /usr/local/bin/ffmpeg
RUN chmod +x /usr/local/bin/xray /usr/local/bin/ffmpeg

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN chmod -R a+rX /app        # 允许任意 uid(如以 admin 1000 跑) 读代码

ENV FEIYING_DATA=/data XRAY_BIN=/usr/local/bin/xray PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080 8890
CMD ["python", "-m", "app.main"]
