#!/bin/bash
# 构建飞牛 fnOS 的 .fpk 安装包。
# 依赖: fnpack (https://static2.fnnas.com/fnpack/, MIT) 在 PATH 里,或放本目录。
# fnpack 不会打包根目录的 *.sc(端口协议文件),所以 build 后需要重新打包补进去。
set -e
cd "$(dirname "$0")"

FNPACK="${FNPACK:-fnpack}"
command -v "$FNPACK" >/dev/null || FNPACK=./fnpack

VERSION=$(grep '^version' project/manifest | awk -F'=' '{print $2}' | tr -d ' ')
OUT="feiying_${VERSION}_x86_64.fpk"

rm -rf .build "$OUT"
"$FNPACK" build -d project
mkdir .build
tar -xf feiying.fpk -C .build
rm feiying.fpk
cp project/feiying.sc .build/
(cd .build && tar -czf "../$OUT" app.tgz cmd config wizard manifest ICON.PNG ICON_256.PNG feiying.sc)
rm -rf .build
echo "构建完成: fpk/$OUT"
