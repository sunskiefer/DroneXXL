#!/bin/sh
# Builds the offline engine test for ARM (static musl) and runs it under qemu-arm-static. Nothing here is built for x86.
set -e
R="$(cd "$(dirname "$0")/.." && pwd)"
cd "$R"
python3 tools/gen_params.py >/dev/null
mkdir -p build/test
OBJS=""
for f in build/modules/*.cpp; do
  o="build/test/$(basename "$f" .cpp).o"
  if [ ! -f "$o" ] || [ "$f" -nt "$o" ]; then sh tools/arm_static.sh "$o" -c "$f" & fi
  OBJS="$OBJS $o"
done
wait
sh tools/arm_static.sh build/test/engine.o -c -I"$R/build/gen" -I"$R/third_party/mpc-vst-plugins/wrapper" src/engine.cc
sh tools/arm_static.sh build/test/engine_test -I"$R/build/gen" -I"$R/third_party/mpc-vst-plugins/wrapper" test/engine_test.cc build/test/engine.o $OBJS
echo built
