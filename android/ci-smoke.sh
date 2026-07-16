#!/bin/bash
# 模拟器冒烟测试:装 APK → 起服务 → / 和 /library 都 200 才算过。
# emulator-runner 的 script 逐行执行,多行控制流必须放脚本文件里。
set -e
APK="$1"

adb install "$APK"
adb shell am start -n cc.aeio.feiying/.MainActivity
adb forward tcp:27125 tcp:27125

ok=0
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:27125/ | grep -q "飞影"; then ok=1; break; fi
  sleep 3
done
if [ "$ok" = "1" ]; then
  curl -sf http://127.0.0.1:27125/library > /dev/null || ok=0
fi

echo "---- logcat(python相关) ----"
adb logcat -d | grep -iE "python|chaquo|AndroidRuntime|feiying" | tail -60 || true

[ "$ok" = "1" ] || { echo "smoke FAILED"; exit 1; }
echo "smoke ok: / 和 /library 都 200"
