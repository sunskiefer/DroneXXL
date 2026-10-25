#!/bin/sh
# arm_static.sh <out> <src.cc>...  : static ARM (musl) binary for running under qemu-arm-static, build-time helpers and offline tests
R="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$1"; shift
exec python3 -m ziglang c++ -target arm-linux-musleabihf -mcpu=cortex_a17 -std=gnu++17 -O1 -w -I"$R/src/shim" -I"$R/third_party/rack-sdk/include" -I"$R/third_party/rack-sdk/dep/include" -I"$R/third_party/AmbientModules/src" -I"$R/src" "$@" -o "$OUT"
