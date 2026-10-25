# DroneXXL (working name)

A drone / experimental instrument for the Akai Force and MPC (Gen1, MPC OS 2.x/3.x), a standalone VST2 plugin by L'Cronx.
It is Neil Baumberger's **AmbientModules** (VCV Rack, GPL-3.0-or-later) run on a small host-free Rack shim:
the original module DSP is compiled unchanged for ARM and drives a 15-module rack.

Rack: 4 Drones, Mixer, Filter, Pads, 2 PapaSrapa, 2 VCO, LFOs, Joystick, Sequencer, Detector.

## Pages
OVERVIEW (the rack; tap a module) - PERFORMANCE (8 macros, LEARN) - PLAY (XY pad and 6 pads) - OUTPUT (brickwall limiter,
ceiling default -3 dBFS, never above -1 dB, no bypass) - RANDOM - per module CONTROLS and PATCH pages - CONNECTED.

Patching: open a module's PATCH page, tap a jack, change page if you like (the first end stays selected), tap the other
end. The CONNECTED page offers DONE, UNPLUG and CANCEL. Jack keys show their state (cable, held, fits, dimmed).

Presets (PRESET menu): Pulsar, Solar 42, Cinematic Performance, Meditations on Death. Only the Lunar modules and the
cables between them were taken from the VCV patches.

## Randomizer
A parameter never lands on the same place within the next 100 runs (1000 places per parameter). Cables are randomized too:
mode OFF / ADD / REWIRE, NEW CABLES sets how many, and an (output, input) pair does not repeat within 100 runs. Scope ALL /
MODULE / MACROS / CABLES, AMOUNT, MIN STEP, UNDO. The history is saved with the project.
Switches with fewer than 100 positions cannot avoid repeats for 100 runs; for them the rule is: no repeat within
(positions - 1) runs.

## Build (ARM only)
`./build.sh` (needs python3 + Pillow, a host gcc for a skin drawing helper, and `pip install ziglang`).
Output: `build/package/L'Cronx - VST - DroneXXL/`. Copy it to `/sdcard/Synths/` on the device.
Offline engine test: `sh test/build_test.sh && qemu-arm-static build/test/engine_test` (static ARM binary under qemu).
Nothing is built or run for x86.

## Credits and licences
- AmbientModules by Neil Baumberger (GPL-3.0-or-later) - the DSP and panels. This plugin is therefore GPL-3.0-or-later;
  source is in this repository.
- Valley (Dale Johnson) DSP used by the modules; VCV Rack / MetaModule SDK headers; WhatTheRack and WhatTheJack
  (WTFPL) as used by AmbientModules.
- mpc-vst-plugins wrapper (vendored, with a patched 64 KB state chunk).
- Titillium Web (SIL OFL), see art/fonts.
No product or brand names appear on the panels.

## Status
See TESTING.md: what has and has not been tested. There has been no test on a real Force yet.
