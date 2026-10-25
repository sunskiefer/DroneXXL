# What is tested, what is not

Tested offline (ARM static build under qemu-arm-static, `test/engine_test.cc`):
- all 4 presets render finite, audible, no DC, under the ceiling;
- limiter ceiling clamps at -1 dBFS whatever is asked;
- macros move controls, LEARN assigns, page-following Q-Links;
- patching: tap, page change keeps the held end, connect, unplug;
- randomizer: no parameter lands on a used place within 100 runs (checked on FREQ L), cables, UNDO;
- state: save, load, save is identical; also works in an 8 KB buffer (shorter history);
- PLAY pad latch and XY.
The skin was composed and looked at offline (build/preview/*.png); `skin_check` runs in the build.

NOT tested:
- anything on a real Force / MPC: loading, touch, Q-Links, redraws, state save in the host;
- CPU: 15 Rack modules at 44.1 kHz on the device are unmeasured (no BENCH run);
- audio listening beyond level and DC checks; the Pulsar preset is quiet at the default level.

Known limits:
- Pads are host latches (module latch mode is a widget-only setting); presets start with all pads ON.
- The CONNECTED page shows a generic cable between the two module panels, not the exact jacks.
- PLAY has no X/Y RANGE controls (they are on the Joystick CONTROLS page).
- OUTPUT meters are LED pictures without numeric readout; the overview shows no live cables.
- Q-Links follow the first 16 controls of a page (Drone and Mixer have 20).
- Knob size is capped (filmstrip limit).
- The randomizer's history needs the patched 64 KB state chunk in the vendored wrapper; in a smaller buffer it shortens.
