#!/usr/bin/env bash
# Build DroneXXL for MPC OS Gen1 / Force (armv7-a hard-float, glibc <= 2.31). ARM only: nothing here builds for x86.
#   ./build.sh          (MPC_VST=... to use another framework checkout)
# Needs: python3 + Pillow, a host gcc (for shadow_art, a skin drawing helper) and Zig (pip install ziglang).
# Output: build/package/L'Cronx - VST - DroneXXL/  (skin + dronexxl.so)
set -euo pipefail
cd "$(dirname "$0")"
MPC_VST="${MPC_VST:-$PWD/third_party/mpc-vst-plugins}"
ZIG="${ZIG:-python3 -m ziglang}"
NAME="L'Cronx - VST - DroneXXL"
mkdir -p build/host build/arm build/modules
sh build/skin.sh
[ -x build/host/shadow_art ] || gcc -O2 -w -I"$MPC_VST/tools/vendor/force-shadow/tools" -x c -o build/host/shadow_art "$MPC_VST/tools/shadow_art.c" -lm
TGT="-target arm-linux-gnueabihf.2.31 -mcpu=cortex_a17"
COMMON="-O2 -fPIC -fvisibility=hidden -ffunction-sections -fdata-sections -DNDEBUG -w -ffp-contract=off"
# the ten module sources (Neil Baumberger's AmbientModules, unchanged DSP; tools/prep_modules.py wrote build/modules/*.cpp)
OBJS=""
for f in build/modules/*.cpp; do
  o="${f%.cpp}.o"
  [ "$o" -nt "$f" ] || sh build/cc.sh "$f" "$o"
  OBJS="$OBJS $o"
done
$ZIG c++ $TGT $COMMON -std=gnu++17 -fno-rtti -Isrc -Ibuild/gen -Isrc/shim -Ithird_party/rack-sdk/include -Ithird_party/rack-sdk/dep/include \
  -Ithird_party/AmbientModules/src -I"$MPC_VST/wrapper" -c src/engine.cc -o build/arm/engine.o
$ZIG cc $TGT $COMMON -std=gnu11 -Ibuild -I"$MPC_VST/wrapper" -c "$MPC_VST/wrapper/vst2_wrap.c" -o build/arm/vst2_wrap.o
printf '{\n  global: VSTPluginMain;\n  local: *;\n};\n' > build/arm/exports.map
$ZIG c++ $TGT -shared -fPIC -Wl,--no-undefined -Wl,--version-script=build/arm/exports.map -Wl,--gc-sections -Wl,-s \
  $OBJS build/arm/engine.o build/arm/vst2_wrap.o -lm -ldl -lpthread -o build/arm/dronexxl.so
PKG="build/package/$NAME"
rm -rf build/package && mkdir -p "$PKG"
cp -r "build/skin/$NAME/." "$PKG/"
cp build/arm/dronexxl.so "$PKG/"
echo "-> $PKG"
