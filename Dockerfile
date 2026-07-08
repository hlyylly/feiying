# xray 二进制从 teddysun/xray 拷贝(飞牛上能拉,避免 github 下载)
FROM teddysun/xray:latest AS xraybin

FROM python:3.12-slim
COPY --from=xraybin /usr/bin/xray /usr/local/bin/xray
RUN chmod +x /usr/local/bin/xray

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN chmod -R a+rX /app        # 允许任意 uid(如以 admin 1000 跑) 读代码

ENV TGFLIX_DATA=/data XRAY_BIN=/usr/local/bin/xray PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080 8890
CMD ["python", "-m", "app.main"]
