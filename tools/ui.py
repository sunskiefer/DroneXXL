"""UI vocabulary shared by gen_params.py (params, gen.h) and the skin tools: pages, macro and pad counts, XY grid."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec

NSLOT = len(spec.SLOTS)
V_OVERVIEW, V_PERF, V_PLAY, V_OUTPUT, V_RANDOM = 0, 1, 2, 3, 4
V_CTRL0 = 5                  # + slot: that module's CONTROLS page
V_PATCH0 = V_CTRL0 + NSLOT   # + slot: that module's PATCH page
V_CONN = V_PATCH0 + NSLOT    # the connected-cable page
NVIEW = V_CONN + 1
NMACRO, NPAD = 8, 6
XY_COLS, XY_ROWS = 7, 5      # the tap grid on the PLAY page
MAX_CABLES = 64
HIST = 100                   # runs remembered by the randomizer
BINS = 1000

def view_names():
    n = ["Overview", "Performance", "Play", "Output", "Random"]
    n += ["%s Controls" % spec.slot_title(s).title() for s in range(NSLOT)]
    n += ["%s Patch" % spec.slot_title(s).title() for s in range(NSLOT)]
    n += ["Connected"]
    return n

def ctrl_order(t):
    """a type's controls in reading order (top row left to right, then the next) -> list of param indices"""
    ps = t["params"]
    return sorted(range(len(ps)), key=lambda i: (round((ps[i]["y"] or 0) / 60.0), ps[i]["x"] or 0, i))

def short_opt(s):
    return s.split(" (")[0].replace("Saw to inv. saw", "Saw blend").replace("Sine to saw", "Sine-saw blend")[:22]
