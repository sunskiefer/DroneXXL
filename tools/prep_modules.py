#!/usr/bin/env python3
"""Cut the panels, widgets and menus out of the vendored Lunar module sources, keeping the DSP classes byte for byte.
    python3 tools/prep_modules.py   ->  build/modules/<Name>.cpp
Each module file is: DSP class (and helpers) ... `struct <Name>Widget : ModuleWidget {` ... `Model* model<Name> = createModel<...>`.
Everything from the widget struct to the end is replaced by a plain createModel<Name>() registration."""
import re, os, sys
R = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SRC = os.path.join(R, "third_party/AmbientModules/src"); OUT = os.path.join(R, "build/modules")
os.makedirs(OUT, exist_ok=True)
NAMES = ["Lunar50Drone","LunarDetector","LunarFilter","LunarJoystick","LunarLFO","LunarMixer","LunarPads","LunarPapaSrapa","LunarSequencer","LunarVCO"]
for n in NAMES:
    t = open(f"{SRC}/{n}.cpp").read()
    m = re.search(rf"^struct {n}Widget : ModuleWidget \{{", t, re.M)
    if not m: sys.exit(f"{n}: widget struct not found")
    body = t[:m.start()]
    for inc in ('PanelTheme.hpp', 'Widgets.hpp'):
        body = body.replace(f'#include "{inc}"', '')
    # click-position switch helper (panel only): from its template line to the last `using ClickTarget...;`
    a = body.find('template <typename TBase>\nstruct ClickTargetSwitch')
    if a >= 0:
        e = body.rfind('using ClickTarget'); e = body.find(';', e) + 1
        body = body[:a] + body[e:]
    body += f'\nModel* model{n} = createModel<{n}>("{n}");\n'
    open(f"{OUT}/{n}.cpp", "w").write(body)
print("prepared", len(NAMES), "modules")
