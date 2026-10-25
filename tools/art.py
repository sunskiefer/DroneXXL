"""The page pictures (stone panel, header, bars, labels, jack lists, module panels) and the small overlay pictures.
Everything here is static; the live parts are the controls MPC draws on top (layout.conf) and the overlays post_skin.py
switches by parameter."""
import os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skinlib as S
import pages as PG
import spec, ui

ROOT = PG.ROOT
INK = S.INK
LIGHT = (233, 228, 217)
T = PG.T


def ink(name):
    return INK if name == "dark" else LIGHT


def header(im, keys, active=None):
    x0, y0, x1, y1 = 26, 20, 1254, 90
    S.bar(im, (x0, y0, x1 - x0, y1 - y0), "", 26)
    for key, label, a, b in keys:
        r = (a, PG.HEAD_Y - 26, b - a, 52)
        S.key(im, r, label, "light" if key == active else "dark", 26, border=14)


def draw_items(im, items):
    for it in items:
        k = it["kind"]
        if k == "bar":
            S.bar(im, (it["x"], it["y"], it["w"], it["h"]), it["text"], it["size"])
        elif k == "text":
            S.draw_text(im, (it["x"], it["y"]), it["text"], it["size"], ink(it["ink"]), it["anchor"])
        elif k == "box":
            S.black_box(im, (it["cx"] - it["w"] // 2, it["cy"] - it["h"] // 2, it["w"], it["h"]))
        elif k == "tap" and it.get("bake"):
            S.key(im, (it["cx"] - it["w"] // 2, it["cy"] - it["h"] // 2, it["w"], it["h"]), it["label"] or "", "light", 24)


def page_main(v):
    im = S.base_page().copy()
    header(im, PG.MAIN_KEYS, PG.MAIN_ACTIVE.get(v))
    draw_items(im, PG.PAGES["main"][v])
    if v == 2:
        draw_play(im)
    if v == 3:
        pass
    return im


def draw_play(im):
    d = ImageDraw.Draw(im)
    x0, y0, w, h = PG.XY_X0, PG.XY_Y0, PG.XY_W, PG.XY_H
    d.rectangle([x0 - 3, y0 - 3, x0 + w + 3, y0 + h + 3], fill=(10, 10, 10, 255))
    pad = S.tex("panel2").resize((w, h), Image.LANCZOS)
    im.alpha_composite(pad, (x0, y0))
    d = ImageDraw.Draw(im)
    for c in range(1, ui.XY_COLS):
        d.line([x0 + w * c / ui.XY_COLS, y0, x0 + w * c / ui.XY_COLS, y0 + h], fill=(70, 66, 60, 120), width=1)
    for r in range(1, ui.XY_ROWS):
        d.line([x0, y0 + h * r / ui.XY_ROWS, x0 + w, y0 + h * r / ui.XY_ROWS], fill=(70, 66, 60, 120), width=1)
    d.line([x0 + w / 2, y0, x0 + w / 2, y0 + h], fill=(10, 10, 10, 255), width=3)
    d.line([x0, y0 + h / 2, x0 + w, y0 + h / 2], fill=(10, 10, 10, 255), width=3)


def page_overview():
    im = S.base_page().copy()
    header(im, PG.MAIN_KEYS, None)
    rack = Image.open(os.path.join(S.ART, "RackThemed2.png")).convert("RGBA")
    sw, sh = int(rack.size[0] * PG.RACK_SCALE), int(rack.size[1] * PG.RACK_SCALE)
    rack = rack.resize((sw, sh), Image.LANCZOS)
    S.shadow(im, (PG.RACK_X, PG.RACK_Y, sw, sh), 6, 5, 150)
    im.alpha_composite(rack, (PG.RACK_X, PG.RACK_Y))
    return im


def page_ctrl(t):
    im = S.base_page().copy()
    header(im, PG.MOD_KEYS, "nav_ctrl")
    draw_items(im, PG.PAGES["type"][t])
    return im


_RACK = None


def panel_image(t, height):
    """the module's panel, cut from the approved rack picture (it carries no product or brand text)"""
    global _RACK
    if _RACK is None:
        _RACK = Image.open(os.path.join(S.ART, "RackThemed2.png")).convert("RGBA")
    slot = next(s for s in range(ui.NSLOT) if spec.SLOT_TYPE[s] == t)
    x0, y0, x1, y1 = PG.RACK_RECTS[slot]
    p = _RACK.crop((x0, y0, x1, y1))
    w = int(round(p.size[0] * height / float(p.size[1])))
    return p.resize((w, height), Image.LANCZOS)


def jack_pos_on_panel(t, kind, n, height, ox, oy):
    """centre of a jack of type t on the panel picture drawn `height` tall at (ox, oy) (layout_mm.json is in mm of a 128.5 mm panel)"""
    j = T[t]["ins" if kind == "i" else "outs"][n]
    k = height / 128.5
    return ox + j["x"] * k, oy + j["y"] * k


def page_patch(t):
    im = S.base_page().copy()
    header(im, PG.MOD_KEYS, "nav_patch")
    p = panel_image(t, PG.PANEL_H)
    S.shadow(im, (PG.PANEL_X, PG.PANEL_Y, p.size[0], p.size[1]), 5, 4, 150)
    im.alpha_composite(p, (PG.PANEL_X, PG.PANEL_Y))
    rows, oy = PG.jack_rows(t)
    S.bar(im, (322, 98, 918, 38), "INPUTS" if T[t]["ins"] else "", 26)
    if T[t]["outs"]:
        S.bar(im, (322, oy, 918, 38), "OUTPUTS", 26)
    for kind, n, label, cx, cy in rows:
        r = (cx - PG.KEY_W // 2, cy - PG.KEY_H // 2, PG.KEY_W, PG.KEY_H)
        S.key(im, r, label, "dark" if kind == "i" else "light", 28, border=14)
    px, py, pw, ph = PG.PATCH_INFO
    S.black_box(im, (px, py, pw, ph))
    return im


def page_conn():
    im = S.base_page().copy()
    header(im, PG.CONN_KEYS, None)
    S.draw_text(im, (640, 54), "CABLE", 34, LIGHT, "mm", True, 2)
    S.bar(im, (680, 98, 560, 36), "FROM", 26)
    S.bar(im, (680, 220, 560, 36), "TO", 26)
    for k, (cx, cy, w, h) in PG.CONN_READ.items():
        S.black_box(im, (cx - w // 2, cy - h // 2, w, h))
    # the cable between the two panels: drawn as a wide orange rope
    d = ImageDraw.Draw(im)
    return im


CONN_L = (60, 100, 440)     # x, y, panel height of the "from" panel
CONN_R = (400, 100, 440)


def conn_panel(t, left=True):
    x, y, h = CONN_L if left else CONN_R
    p = panel_image(t, h)
    out = Image.new("RGBA", (p.size[0] + 20, p.size[1] + 20), (0, 0, 0, 0))
    S.shadow(out, (10, 10, p.size[0], p.size[1]), 5, 4, 150)
    out.alpha_composite(p, (10, 10))
    return out, (x - 10, y - 10)


def cable_arc(size=(560, 120)):
    """a generic orange cable between the panels, with two plugs"""
    import math
    w, h = size
    S3 = 3
    im = Image.new("RGBA", (w * S3, h * S3), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = []
    for i in range(61):
        t = i / 60.0
        x = 20 + (w - 40) * t
        y = 24 + 60 * math.sin(math.pi * t)
        pts.append((x * S3, y * S3))
    d.line(pts, fill=(90, 40, 8, 255), width=16 * S3, joint="curve")
    d.line(pts, fill=S.ORANGE + (255,), width=10 * S3, joint="curve")
    d.line([(x, y - 3 * S3) for x, y in pts], fill=(255, 200, 140, 140), width=3 * S3)
    for x, y in (pts[0], pts[-1]):
        r = 17 * S3
        d.ellipse([x - r, y - r, x + r, y + r], fill=(60, 28, 6, 255))
        d.ellipse([x - r * 0.75, y - r * 0.75, x + r * 0.75, y + r * 0.75], fill=S.ORANGE + (255,))
    return im.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------------------------------------ widget pictures
def keycap_image(w, h, label, style="light", size=26):
    """a flat key cap (no drop shadow, so it fits its box)"""
    name, ink_ = S.KEYS["dark" if style == "dark" else ("light" if style == "light" else "red")]
    b = 14 if style == "dark" else min(20, h // 3)
    if style == "orange":
        k = key_orange_plain(w, h)
        ink_ = INK
    else:
        k = S.nine(S.tex(name), w, h, 30, b)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    im.alpha_composite(k)
    if label:
        sz = size
        while sz > 18 and S.text_w(label, sz) > w - 22:
            sz -= 1
        S.draw_text(im, (w / 2, h / 2 - 1), label, sz, ink_)
    return im


def key_orange_plain(w, h):
    k = S.nine(S.tex("key_on"), w, h, 30, min(20, h // 3))
    r, g, b, a = k.split()
    hsv = Image.merge("RGB", (r, g, b)).convert("HSV")
    hh, ss, vv = hsv.split()
    hh = hh.point(lambda v: (v + 14) % 256)
    k2 = Image.merge("RGB", (hh, ss.point(lambda v: min(255, int(v * 1.25))), vv)).convert("HSV").convert("RGB")
    return Image.merge("RGBA", (*k2.split(), a))


def press_image(w, h):
    return S.press_overlay(w, h)


def blank():
    return Image.new("RGBA", (4, 4), (0, 0, 0, 0))


def ball(d=70):
    S3 = 4
    im = Image.new("RGBA", (d * S3, d * S3), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.ellipse([6 * S3, 10 * S3, (d - 6) * S3, (d - 2) * S3], fill=(0, 0, 0, 90))
    dr.ellipse([4 * S3, 4 * S3, (d - 8) * S3, (d - 8) * S3], fill=(240, 130, 40, 255))
    dr.ellipse([d * 0.22 * S3, d * 0.16 * S3, d * 0.52 * S3, d * 0.40 * S3], fill=(255, 190, 120, 200))
    return im.resize((d, d), Image.LANCZOS)


def state_key(state, w, h):
    """overlay on a patch page's jack key: 1 cable, 2 held, 3 fits, 4 dimmed"""
    S3 = 2
    im = Image.new("RGBA", (w * S3, h * S3), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    box = [2, 2, w * S3 - 3, h * S3 - 3]
    if state == 1:
        d.rounded_rectangle(box, radius=10 * S3, outline=S.ORANGE + (255,), width=5 * S3)
        d.ellipse([w * S3 - 30 * S3, h * S3 / 2 - 7 * S3, w * S3 - 16 * S3, h * S3 / 2 + 7 * S3], fill=S.ORANGE + (255,))
    elif state == 2:
        d.rounded_rectangle(box, radius=10 * S3, fill=S.ORANGE + (190,), outline=(255, 255, 255, 255), width=5 * S3)
    elif state == 3:
        d.rounded_rectangle(box, radius=10 * S3, fill=S.ORANGE + (60,), outline=S.ORANGE + (255,), width=5 * S3)
    elif state == 4:
        d.rounded_rectangle(box, radius=10 * S3, fill=(14, 14, 14, 175))
    return im.resize((w, h), Image.LANCZOS)


def macro_led(n, colour, w=400, h=40):
    return S.led_strip(w, h, n, colour, 22)
