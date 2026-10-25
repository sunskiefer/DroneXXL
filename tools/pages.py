"""Page geometry: every page of the plugin as data (skin pixels, 1280x628, y down from the top of the plugin area).

    from pages import PAGES, ...     -> items per page, the header keys, the overview tap rectangles
    python3 tools/pages.py           -> writes build/layout.conf (the controls MPC will draw and touch)

An item is a dict:
  knob   idx/key, cx, cy, size (L/M/S), side (bw, bh) or None, colour
  key    a two-state key cap (a toggle): key, cx, cy, w, h, labels (off, on), style
  seg    a row/grid of segments (an enum): key, cx, cy, sw, sh, rows
  tap    a transparent touch box on a trigger: key, cx, cy, w, h
  bar    baked black bar with text: x, y, w, h, text
  text   baked text: x, y, text, size, ink, anchor
  box    black readout bar for a live text: key, cx, cy, w, h, size
Everything that is "baked" is drawn into the page picture by tools/post_skin.py; the others are layout lines.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec, ui
from skinlib import COLOURS, radius_of

ROOT = spec.ROOT
T = spec.types()
Y0 = 86                      # layout y = skin y + 86 (the plugin area starts at y 86 of the Force screen)
QCOL = ["red", "orange", "yellow", "green", "blue", "purple", "pink", "lgrey"]

# the header: (key, label, x0, x1) -- one row at y 28..80
HEAD_Y, HEAD_H = 54, 52
MAIN_KEYS = [("nav_ov", "OVERVIEW", 40, 250), ("nav_prev", "<", 262, 346), ("nav_next", ">", 356, 440),
             ("nav_perf", "PERFORMANCE", 514, 768), ("nav_play", "PLAY", 778, 896), ("nav_out", "OUTPUT", 906, 1062),
             ("nav_rand", "RANDOM", 1072, 1238)]
MOD_KEYS = [("nav_ov", "OVERVIEW", 40, 250), ("nav_prev", "<", 262, 346), ("nav_next", ">", 356, 440),
            ("nav_ctrl", "CONTROLS", 800, 1010), ("nav_patch", "PATCH", 1030, 1238)]
CONN_KEYS = [("nav_ov", "OVERVIEW", 40, 250)]
MAIN_ACTIVE = {1: "nav_perf", 2: "nav_play", 3: "nav_out", 4: "nav_rand"}
TITLE_BOX = (460, 790)       # the live page title between the arrows and CONTROLS/PATCH

# the rack picture on the overview (RackThemed2.png is 1842 x 1287, drawn at 0.3947 from (277, 98))
RACK_SCALE, RACK_X, RACK_Y = 727.0 / 1842, 277, 98
RACK_RECTS = [  # by slot, in rack-picture pixels: x0, y0, x1, y1
    (0, 0, 278, 645), (278, 0, 556, 645), (556, 0, 834, 645), (834, 0, 1011, 645), (1011, 0, 1289, 645),
    (1289, 0, 1566, 645), (1566, 0, 1842, 645),
    (53, 647, 331, 1287), (331, 647, 608, 1287), (608, 647, 709, 1287), (709, 647, 936, 1287), (936, 647, 1113, 1287),
    (1113, 647, 1214, 1287), (1214, 647, 1491, 1287), (1491, 647, 1768, 1287)]


def rack_rect(slot):
    x0, y0, x1, y1 = RACK_RECTS[slot]
    s = RACK_SCALE
    return (int(RACK_X + x0 * s), int(RACK_Y + y0 * s), int((x1 - x0) * s), int((y1 - y0) * s))


PANEL_FILE = {"dr": "Drone", "mx": "Mixer", "fl": "Filter", "pd": "Pads", "pp": "PapaSrapa", "vc": "VCO", "lf": "LFO",
              "js": "Joystick", "sq": "Seq", "dt": "Detect"}

# ------------------------------------------------------------------------------------------------ builders
def knob(key, cx, cy, size="M", colour=None, side=None, name=None, bw=None):
    return dict(kind="knob", key=key, cx=cx, cy=cy, size=size, colour=colour, side=side, name=name, bw=bw)


def keycap(key, cx, cy, w=210, h=56, labels=None, style="light", on_style="red"):
    return dict(kind="key", key=key, cx=cx, cy=cy, w=w, h=h, labels=labels, style=style, on_style=on_style)


def seg(key, cx, cy, sw, sh, rows=1):
    return dict(kind="seg", key=key, cx=cx, cy=cy, sw=sw, sh=sh, rows=rows)


def tap(key, cx, cy, w, h, label=None, style=None, bake=False):
    return dict(kind="tap", key=key, cx=cx, cy=cy, w=w, h=h, label=label, style=style, bake=bake)


def bar(x, y, w, h, text, size=26):
    return dict(kind="bar", x=x, y=y, w=w, h=h, text=text, size=size)


def text(x, y, s, size=30, ink="dark", anchor="mm"):
    return dict(kind="text", x=x, y=y, text=s, size=size, ink=ink, anchor=anchor)


def box(key, cx, cy, w, h, size=30, ink="light"):
    return dict(kind="box", key=key, cx=cx, cy=cy, w=w, h=h, size=size, ink=ink)


def tkey(t, i):
    return "%s_%d" % (T[t]["key"], i)


def qslot(t, i):
    return ui.ctrl_order(T[t]).index(i)


def tk(t, i, cx, cy, size="M", side=None, bw=None):
    """a knob of module type t, param i, coloured by its Q-Link slot"""
    return knob(tkey(t, i), cx, cy, size, QCOL[qslot(t, i) % 8], side, None, bw)


def tkey_cap(t, i, cx, cy, w=210, h=56, style="light"):
    p = T[t]["params"][i]
    nm = p["name"]
    lab = [short(l) for l in p["labels"]]
    if lab[0] in ("OFF", "INACTIVE") or lab[1] in ("ON", "ACTIVE"):
        labels = (nm, nm)
    else:
        labels = (lab[0], lab[1])
    return keycap(tkey(t, i), cx, cy, w, h, labels, style)


def short(s):
    return ui.short_opt(s).upper()


# ------------------------------------------------------------------------------------------------ module pages
def page_drone():
    t = 0
    it = [bar(40, 98, 215, 38, "MUTE"), bar(265, 98, 330, 38, "TUNE"), bar(605, 98, 190, 38, "MOD"), bar(830, 98, 410, 38, "SOUND")]
    for k in range(5):
        y = 190 + 88 * k
        it.append(text(24, y, str(k + 1), 34, "dark", "mm"))
        it.append(tkey_cap(t, 5 + k, 160, y, 190, 56))
        it.append(tk(t, k, 430, y, "S", side=(250, 86)))
        it.append(tkey_cap(t, 10 + k, 700, y, 190, 56))
    it += [tk(t, 19, 930, 190, "M"), tk(t, 15, 1140, 190, "M"), tk(t, 17, 930, 395, "M"), tk(t, 18, 1140, 395, "M"),
           tkey_cap(t, 16, 1035, 583, 230, 52)]
    return it


def page_mixer():
    t = 1
    names = ["DRONE 1", "DRONE 2", "DRONE 3", "VCO A", "AUDIO", "VCO B", "DRONE 4", "DRONE 5", "DRONE 6"]
    it = []
    for blk, x0 in ((0, 40), (1, 660)):
        it += [bar(x0, 98, 160, 38, "INPUT"), bar(x0 + 170, 98, 200, 38, "LEVEL"), bar(x0 + 380, 98, 200, 38, "PAN")]
    for ch in range(9):
        x0 = 40 if ch < 5 else 660
        y = 190 + 88 * (ch if ch < 5 else ch - 5)
        it.append(text(x0 + 80, y, names[ch], 28, "dark", "mm"))
        it.append(tk(t, 9 + ch, x0 + 270, y, "S", side=(200, 86)))
        it.append(tk(t, ch, x0 + 480, y, "S", side=(200, 86)))
    y = 190 + 88 * 4
    it.append(text(660 + 80, y, "MASTER", 28, "dark", "mm"))
    it.append(tk(t, 18, 660 + 270, y, "S", side=(200, 86)))
    it.append(tkey_cap(t, 19, 660 + 480, y, 200, 56))
    return it


def page_filter():
    t = 2
    it = [bar(40, 98, 1200, 38, "L FILTER  /  R FILTER  /  DISTORTION  /  INSERT FX", 26)]
    row1 = [0, 1, 6, 3, 4, 7]
    row2 = [10, 8, 9, 12, 14, 13]
    for k, i in enumerate(row1):
        it.append(tk(t, i, 140 + 200 * k, 208, "S", bw=196))
    for k, i in enumerate(row2):
        it.append(tk(t, i, 140 + 200 * k, 398, "S", bw=196))
    it += [tkey_cap(t, 2, 250, 580, 230, 52), tkey_cap(t, 5, 520, 580, 230, 52), tkey_cap(t, 11, 790, 580, 230, 52)]
    return it


def page_pads():
    t = 3
    it = [bar(40, 98, 1200, 38, "PADS  (LATCHED: TAP TO HOLD A GATE HIGH)", 26)]
    for k in range(6):
        c, r = k // 3, k % 3
        it.append(keycap(tkey(t, k), 340 + 600 * c, 230 + 140 * r, 520, 110, ("PAD %d" % (k + 1),) * 2, "dark", "orange"))
    return it


def page_papasrapa():
    t = 4
    it = [bar(40, 98, 1200, 38, "LFO  /  PITCH  /  NOISE  /  ENVELOPE", 26)]
    for k, i in enumerate([0, 4, 5, 1, 6]):
        it.append(tk(t, i, 140 + 250 * k, 208, "S"))
    it += [tk(t, 8, 140, 398, "S"), tk(t, 9, 390, 398, "S"),
           tkey_cap(t, 2, 690, 380, 230, 56), tkey_cap(t, 3, 940, 380, 230, 56),
           tkey_cap(t, 7, 690, 470, 230, 56), tkey_cap(t, 10, 940, 470, 230, 56)]
    return it


def page_vco():
    t = 5
    it = [bar(40, 98, 1200, 38, "WAVE  /  SHAPE  /  FM  /  ENVELOPE", 26),
          seg(tkey(t, 0), 620, 178, 190, 56, 1)]
    for k, i in enumerate([1, 5, 6, 7]):
        it.append(tk(t, i, 140 + 250 * k, 300, "S"))
    for k, i in enumerate([8, 9, 10, 11]):
        it.append(tk(t, i, 140 + 250 * k, 480, "S"))
    for k, i in enumerate([2, 3, 4, 12, 13]):
        it.append(tkey_cap(t, i, 1120, 262 + 70 * k, 220, 56))
    return it


def page_lfo():
    t = 6
    it = [bar(40, 98, 580, 38, "LFO A"), bar(660, 98, 580, 38, "LFO B")]
    it += [tk(t, 1, 210, 300, "L"), tk(t, 0, 450, 300, "L"), tk(t, 3, 830, 300, "L"), tk(t, 2, 1070, 300, "L")]
    return it


def page_joystick():
    t = 7
    it = [bar(40, 98, 580, 38, "X"), bar(660, 98, 580, 38, "Y")]
    it += [tk(t, 0, 210, 270, "L"), tk(t, 2, 450, 270, "L"), tk(t, 1, 830, 270, "L"), tk(t, 3, 1070, 270, "L"),
           text(330, 440, "RANGE", 28, "dark"), seg(tkey(t, 4), 330, 510, 200, 56, 2),
           text(950, 440, "RANGE", 28, "dark"), seg(tkey(t, 5), 950, 510, 200, 56, 2)]
    return it


def page_seq():
    t = 8
    it = [bar(40, 98, 300, 38, "STEP"), bar(350, 98, 260, 38, "GATE"), bar(680, 98, 560, 38, "CLOCK")]
    for k in range(5):
        y = 190 + 88 * k
        it.append(text(24, y, str(k + 1), 34, "dark"))
        it.append(tk(t, k, 190, y, "S", side=(270, 86)))
        it.append(tkey_cap(t, 5 + k, 480, y, 200, 56))
    it += [tk(t, 11, 830, 300, "L"), text(1090, 230, "STAGES", 30, "dark"), seg(tkey(t, 10), 1090, 300, 100, 60, 1)]
    return it


def page_detect():
    t = 9
    it = [bar(40, 98, 1200, 38, "ENVELOPE FOLLOWER", 26)]
    it += [tk(t, 0, 240, 290, "L"), tk(t, 1, 640, 290, "L"), tk(t, 2, 1040, 290, "L")]
    return it


TYPE_PAGES = [page_drone, page_mixer, page_filter, page_pads, page_papasrapa, page_vco, page_lfo, page_joystick, page_seq,
              page_detect]


# ------------------------------------------------------------------------------------------------ main pages
def page_perf():
    it = [bar(40, 98, 1200, 38, "MACROS")]
    for m in range(ui.NMACRO):
        c, r = m % 4, m // 4
        it.append(knob("m%d" % (m + 1), 190 + 300 * c, 200 + 200 * r, "M", QCOL[m % 8]))
    it += [keycap("learn", 150, 576, 220, 56, ("LEARN: OFF", "LEARN: ON")),
           box("perf_info", 650, 576, 740, 56, 28),
           tap("m_clear", 1140, 576, 196, 56, "CLEAR", "light")]
    return it


XY_X0, XY_Y0, XY_W, XY_H = 42, 146, 556, 280


def page_play():
    it = [bar(40, 98, 560, 38, "JOYSTICK"), bar(624, 98, 616, 38, "PADS")]
    cw, ch = XY_W / float(ui.XY_COLS), XY_H / float(ui.XY_ROWS)
    for r in range(ui.XY_ROWS):
        for c in range(ui.XY_COLS):
            it.append(tap("xy_%d_%d" % (c, r), int(XY_X0 + cw * (c + 0.5)), int(XY_Y0 + ch * (r + 0.5)), int(cw), int(ch)))
    it.append(box("xy_text", XY_X0 + 160, XY_Y0 + XY_H - 24, 300, 40, 28, "dark"))
    it += [tk(7, 2, 160, 470, "S"), tk(7, 3, 480, 470, "S")]
    for k in range(6):
        c, r = k % 2, k // 2
        it.append(keycap(tkey(3, k), 774 + 310 * c, 200 + 130 * r, 296, 112, ("PAD %d" % (k + 1),) * 2, "dark", "orange"))
    return it


def page_output():
    it = [bar(40, 98, 1200, 38, "LIMITER"),
          knob("level", 190, 300, "L", "red"), knob("ceil", 430, 300, "L", "orange"), knob("rel", 670, 300, "L", "yellow"),
          bar(840, 200, 400, 38, "GAIN REDUCTION"), bar(840, 348, 400, 38, "OUTPUT PEAK"),
          bar(40, 552, 1200, 54, "ALWAYS ON. CEILING NEVER ABOVE -1 dB.", 28)]
    return it


def page_random():
    it = [bar(40, 98, 1200, 38, "RANDOMIZER"),
          knob("r_amount", 140, 290, "L", "red"), knob("r_min", 380, 290, "L", "orange"),
          knob("r_cables", 620, 290, "L", "yellow", name="NEW CABLES"),
          tap("r_go", 1000, 270, 470, 88, "RANDOMIZE", "red"),
          tap("r_undo", 880, 392, 230, 62, "UNDO", "light"),
          tap("r_mode_step", 1120, 392, 230, 62, None, "light", True)]
    for k, nm in enumerate(("ALL", "MODULE", "MACROS", "CABLES")):
        it.append(tap("sc_%d" % k, 821 + 118 * k, 480, 112, 56, nm, "light", True))
    return it


# ------------------------------------------------------------------------------------------------ patch pages
KEY_W, KEY_H, KEY_PX, KEY_PY = 290, 54, 300, 62
PANEL_X, PANEL_Y, PANEL_H = 40, 96, 520


def jack_rows(t):
    """-> [(kind, n, label, cx, cy)] the tap key of every jack of type t"""
    out = []
    ins, outs = T[t]["ins"], T[t]["outs"]
    for n, j in enumerate(ins):
        out.append(("i", n, j["name"], 475 + KEY_PX * (n % 3), 172 + KEY_PY * (n // 3)))
    R = (max(len(ins), 1) + 2) // 3
    oy = 62 * R + 151                       # top of the OUTPUTS bar
    for n, j in enumerate(outs):
        out.append(("o", n, j["name"], 475 + KEY_PX * (n % 3), oy + 77 + KEY_PY * (n // 3)))
    return out, oy


def jack_key(t, kind, n):
    return "%s_%s%d" % (T[t]["key"], kind, n)


PATCH_INFO = (322, 530, 640, 54)
PATCH_CANCEL = (1108, 557, 262, 54)
CONN_KEYS_ROW = {"pk_done": (330, 560, 220, 56), "pk_unplug": (590, 560, 220, 56), "pk_cancel": (850, 560, 220, 56)}
CONN_READ = {"conn_a": (960, 170, 560, 50), "conn_b": (960, 292, 560, 50)}


# ------------------------------------------------------------------------------------------------ the page table
def build():
    P = {}
    P["main"] = {0: [], 1: page_perf(), 2: page_play(), 3: page_output(), 4: page_random()}
    P["type"] = [f() for f in TYPE_PAGES]
    return P


PAGES = build()


# ------------------------------------------------------------------------------------------------ layout.conf
def lay(y):
    return int(y) + Y0


def knob_class(it):
    colour = it["colour"] or "red"
    return colour, it["size"]


def knob_line(it, when):
    colour, size = knob_class(it)
    r = radius_of(colour, size)
    key = it["key"]
    nm = it["name"]
    if nm is None:
        nm = key
    if it["side"]:
        bw, bh = it["side"]
        return 'knob cx=%d cy=%d r=%d label="%s" key=%s lay=side bw=%d bh=%d vs=34 ink=1d1a17 %s' % (
            it["cx"], lay(it["cy"]), r, nm, key, bw, bh, when)
    return 'knob cx=%d cy=%d r=%d label="%s" key=%s bw=%d ink=1d1a17 ink_dim=8a2a22 %s' % (
        it["cx"], lay(it["cy"]), r, nm, key, it.get("bw") or (236 if nm == "NEW CABLES" else 214), when)


def item_lines(it, when):
    k = it["kind"]
    if k == "knob":
        return [knob_line(it, when)]
    if k == "key":
        return ['toggle cx=%d cy=%d label="%s" key=%s bw=%d ns=0 %s' % (it["cx"], lay(it["cy"]), it["labels"][0], it["key"], it["w"], when)]
    if k == "seg":
        return ['enum_h cx=%d cy=%d label="" key=%s sw=%d sh=%d rows=%d %s' % (it["cx"], lay(it["cy"]), it["key"], it["sw"], it["sh"], it["rows"], when)]
    if k == "tap":
        return ['button cx=%d cy=%d label="%s" key=%s w=%d h=%d %s' % (it["cx"], lay(it["cy"]), it.get("label") or "", it["key"], it["w"], it["h"], when)]
    if k == "box":
        return ['readout cx=%d cy=%d w=%d h=%d label="" key=%s tsize=%d tweight=700 tcolor=%s %s' % (it["cx"], lay(it["cy"]), it["w"], it["h"], it["key"], it["size"], "e9e4d9" if it["ink"] == "light" else "1d1a17", when)]
    return []


def layout_text():
    L = ["# DroneXXL page layout. GENERATED by tools/pages.py -- edit that, not this.",
         "# One tab. Each page is a mode panel shown while 'view' (or the type page vt / pt) is at it.",
         "# Controls are placed here; the picture of every page is baked by tools/post_skin.py.",
         "scale_names=1", "label_scale=1.7",
         "theme_bg=b4ac9f", "theme_panel=b4ac9f", "theme_line=1d1a17", "theme_ink=1d1a17", "theme_ink_dim=8a2a22",
         "theme_ink_faint=1d1a17", "theme_accent=ff8a1f", "theme_accent_hi=ffffff", "theme_knob_face=1c1c1c",
         "theme_knob_ring=3a3a3a", "theme_knob_dot=ffffff", "theme_bar=0e0e0e", "theme_seg_active=ff8a1f",
         "theme_seg_inactive=1c1c1c", "theme_seg_active_tx=111111", "theme_btn_text=e9e4d9", "theme_tab_on=ff8a1f",
         "theme_tab_on_tx=111111", "theme_lcd=0e0e0e", "theme_box=1c1c1c",
         "qlinks_track = " + ",".join("ql%d" % (i + 1) for i in range(16)), "", "[tab DroneXXL]"]
    # headers
    for nm, keys, when in (("main", MAIN_KEYS, "when=hm:0"), ("mod", MOD_KEYS, "when=hm:1"), ("conn", CONN_KEYS, "when=hm:2")):
        for key, label, x0, x1 in keys:
            L.append('button cx=%d cy=%d label="" key=%s w=%d h=%d %s' % ((x0 + x1) // 2, lay(HEAD_Y), key, x1 - x0, HEAD_H, when))
    L.append('readout cx=%d cy=%d w=%d h=%d label="" key=ttl tsize=34 tweight=700 tcolor=e9e4d9 when=hm:1' % (
        sum(TITLE_BOX) // 2, lay(HEAD_Y), TITLE_BOX[1] - TITLE_BOX[0], 50))
    # overview: a tap box per module
    for s in range(ui.NSLOT):
        x, y, w, h = rack_rect(s)
        L.append('button cx=%d cy=%d label="" key=go_%d w=%d h=%d when=view:0' % (x + w // 2, lay(y + h // 2), s, w, h))
    # main pages
    for v, items in PAGES["main"].items():
        for it in items:
            L += item_lines(it, "when=view:%d" % v) if v else []
    # type pages
    for t, items in enumerate(PAGES["type"]):
        for it in items:
            L += item_lines(it, "when=vt:%d" % (t + 1))
    # patch pages: a tap key per jack
    for t in range(len(T)):
        rows, _ = jack_rows(t)
        for kind, n, label, cx, cy in rows:
            L.append('button cx=%d cy=%d label="" key=%s w=%d h=%d when=pt:%d' % (cx, lay(cy), jack_key(t, kind, n), KEY_W, KEY_H, t + 1))
    px, py, pw, ph = PATCH_INFO
    for t in range(len(T)):
        L.append('readout cx=%d cy=%d w=%d h=%d label="" key=patch_info tsize=28 tweight=700 tcolor=e9e4d9 when=pt:%d' % (
            px + pw // 2, lay(py + ph // 2), pw, ph, t + 1))
    L.append('button cx=%d cy=%d label="CANCEL" key=pk_cancel w=%d h=%d when=pk_c:1' % (
        PATCH_CANCEL[0], lay(PATCH_CANCEL[1]), PATCH_CANCEL[2], PATCH_CANCEL[3]))
    # the connected page
    for key, (cx, cy, w, h) in CONN_KEYS_ROW.items():
        L.append('button cx=%d cy=%d label="" key=%s w=%d h=%d when=hm:2' % (cx, lay(cy), key, w, h))
    for key, (cx, cy, w, h) in CONN_READ.items():
        L.append('readout cx=%d cy=%d w=%d h=%d label="" key=%s tsize=30 tweight=700 tcolor=e9e4d9 when=hm:2' % (cx, lay(cy), w, h, key))
    L.append('qlinks "DroneXXL" = ' + ",".join("ql%d" % (i + 1) for i in range(16)))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    out = os.path.join(ROOT, "build", "layout.conf")
    open(out, "w").write(layout_text())
    n = sum(len(v) for v in PAGES["main"].values()) + sum(len(v) for v in PAGES["type"])
    print("pages: %d items, layout -> %s" % (n, out))
