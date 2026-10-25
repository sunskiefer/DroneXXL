"""Art primitives for the skin: the approved look (stone panel with a rusty rim and screws, black label bars, 9-slice keycaps,
silver/colour knobs with a turning body under a fixed ring), rasterized with PIL from the textures in art/."""
import math
import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ART = os.path.join(ROOT, "art")
W, H = 1280, 628
INK = (29, 26, 23)
BAR_INK = (233, 228, 217)
RED_TEXT = (138, 42, 34)
ORANGE = (255, 138, 31)
COLOURS = ["red", "orange", "yellow", "green", "blue", "purple", "pink", "grey", "lgrey", "volt"]
SIZES = {"L": 58, "M": 48, "S": 38}      # knob classes: the layout radius picks the strip (colour and size)


def radius_of(colour, size):
    return SIZES[size] - COLOURS.index(colour)


def class_of_radius(r):
    for sz, base in SIZES.items():
        if base - 9 <= r <= base:
            return COLOURS[base - r], sz
    return None


@lru_cache(None)
def font(size, bold=True):
    return ImageFont.truetype(os.path.join(ART, "fonts", "TitilliumWeb-%s.ttf" % ("Bold" if bold else "SemiBold")), int(size))


@lru_cache(None)
def tex(name):
    return Image.open(os.path.join(ART, "tex", name + ".png")).convert("RGBA")


def text_w(s, size, bold=True):
    return font(size, bold).getlength(s)


def draw_text(im, xy, s, size, fill=INK, anchor="mm", bold=True, spacing=0, shadow=None):
    d = ImageDraw.Draw(im)
    f = font(size, bold)
    if spacing:
        w = sum(f.getlength(c) + spacing for c in s) - spacing
        x, y = xy
        x0 = x - w / 2 if anchor[0] == "m" else x
        for c in s:
            if shadow:
                d.text((x0 + 1, y + 2), c, font=f, fill=shadow, anchor="l" + anchor[1])
            d.text((x0, y), c, font=f, fill=fill, anchor="l" + anchor[1])
            x0 += f.getlength(c) + spacing
        return
    if shadow:
        d.text((xy[0] + 1, xy[1] + 2), s, font=f, fill=shadow, anchor=anchor)
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def nine(src, w, h, slice_=30, border=20):
    """CSS border-image: slice_ px of the source cut off as corners, drawn border px wide."""
    sw, sh = src.size
    b = min(border, w // 2, h // 2)
    s = slice_
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    xs, ys = [0, s, sw - s, sw], [0, s, sh - s, sh]
    xd, yd = [0, b, w - b, w], [0, b, h - b, h]
    for i in range(3):
        for j in range(3):
            box = (xs[i], ys[j], xs[i + 1], ys[j + 1])
            tw, th = xd[i + 1] - xd[i], yd[j + 1] - yd[j]
            if tw <= 0 or th <= 0:
                continue
            out.alpha_composite(src.crop(box).resize((tw, th), Image.LANCZOS), (xd[i], yd[j]))
    return out


def shadow(im, rect, blur=4, dy=4, alpha=140):
    x, y, w, h = rect
    sh = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([20, 20 + dy, 20 + w, 20 + h + dy], radius=6, fill=(0, 0, 0, alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    im.alpha_composite(sh, (x - 20, y - 20))


KEYS = {"light": ("key_off", INK), "red": ("key_on", INK), "dark": ("key_dark", BAR_INK)}


def key(im, rect, label, style="light", size=26, border=None):
    x, y, w, h = rect
    name, ink = KEYS[style]
    b = border or (14 if style == "dark" else min(20, h // 3))
    shadow(im, rect)
    im.alpha_composite(nine(tex(name), w, h, 30, b), (x, y))
    if style == "orange":
        pass
    if label:
        draw_text(im, (x + w / 2, y + h / 2 - 1), label, size, ink)


def key_orange(im, rect, label, size=26):
    """The lit pad: the red key hue-shifted to the design's orange."""
    x, y, w, h = rect
    k = nine(tex("key_on"), w, h, 30, min(20, h // 3))
    r, g, b, a = k.split()
    hsv = Image.merge("RGB", (r, g, b)).convert("HSV")
    hh, ss, vv = hsv.split()
    hh = hh.point(lambda v: (v + 14) % 256)
    k2 = Image.merge("RGB", (hh, ss.point(lambda v: min(255, int(v * 1.25))), vv)).convert("HSV").convert("RGB")
    k2 = Image.merge("RGBA", (*k2.split(), a))
    shadow(im, rect)
    im.alpha_composite(k2, (x, y))
    draw_text(im, (x + w / 2, y + h / 2 - 1), label, size, INK)


def bar(im, rect, label, size=26):
    x, y, w, h = rect
    b = tex("bar").resize((w, h), Image.LANCZOS)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=3, fill=255)
    b.putalpha(m)
    shadow(im, rect, 3, 3, 120)
    im.alpha_composite(b, (x, y))
    if label:
        draw_text(im, (x + w / 2, y + h / 2), label, size, BAR_INK, spacing=2, shadow=(0, 0, 0))


def black_box(im, rect, r=4):
    x, y, w, h = rect
    ImageDraw.Draw(im).rounded_rectangle([x, y, x + w, y + h], radius=r, fill=(10, 10, 10, 255), outline=(40, 40, 40, 255))


@lru_cache(None)
def base_page():
    """The stone panel, the rusty rim (taken from the approved page) and the four screws."""
    page = tex("panel2").resize((W, H), Image.LANCZOS).copy()
    ref = Image.open(os.path.join(ART, "ref_main.png")).convert("RGBA")
    m = 14
    for box in ((0, 0, W, m), (0, H - m, W, H), (0, 0, m, H), (W - m, 0, W, H)):
        page.paste(ref.crop(box), box[:2])
    sc = tex("screw").resize((34, 34), Image.LANCZOS)
    for p in ((10, 10), (W - 44, 10), (10, H - 44), (W - 44, H - 44)):
        sh = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([8, 11, 42, 45], fill=(0, 0, 0, 120))
        page.alpha_composite(sh.filter(ImageFilter.GaussianBlur(2)), (p[0] - 8, p[1] - 8))
        page.alpha_composite(sc, p)
    return page


def dark_page():
    return Image.new("RGBA", (W, H), (14, 14, 14, 255))


# ------------------------------------------------------------------------------------------------ knobs
@lru_cache(None)
def knob_assets(colour):
    ring = Image.open(os.path.join(ART, "kn", colour + "_ring.png")).convert("RGBA")
    body = Image.open(os.path.join(ART, "kn", colour + "_body.png")).convert("RGBA")
    # where does the pointer point in the unrotated body? (the grey bodies were drawn with it off the top)
    px, py, n = 0.0, 0.0, 0
    c = body.size[0] / 2.0
    lum = body.convert("L")
    A = body.getchannel("A")
    for yy in range(0, body.size[1], 2):
        for xx in range(0, body.size[0], 2):
            if A.getpixel((xx, yy)) > 200:
                l = lum.getpixel((xx, yy))
                r, g, b, _ = body.getpixel((xx, yy))
                hot = (max(r, g, b) - min(r, g, b) > 90 and l > 90) if colour not in ("grey", "lgrey") else l > 205
                if hot and math.hypot(xx - c, yy - c) > c * 0.55:
                    px += xx - c; py += yy - c; n += 1
    off = math.degrees(math.atan2(px, -py)) if n > 20 and colour != "volt" else 0.0
    if colour == "volt":
        off = 0.0
    return ring, body, off


SWEEP = 150.0


def knob_frame(colour, R, angle):
    F = 2 * R + 10
    ring, body, off = knob_assets(colour)
    D = 2 * R
    S = 3
    cv = Image.new("RGBA", (F * S, F * S), (0, 0, 0, 0))
    sh = Image.new("RGBA", (F * S, F * S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([(F / 2 - R + 1) * S, (F / 2 - R + 3) * S, (F / 2 + R + 1) * S, (F / 2 + R + 4) * S], fill=(0, 0, 0, 120))
    cv.alpha_composite(sh.filter(ImageFilter.GaussianBlur(2 * S)))
    b = body.rotate(off - angle, resample=Image.BICUBIC).resize((D * S, D * S), Image.LANCZOS)
    r = ring.resize((D * S, D * S), Image.LANCZOS)
    o = (F * S - D * S) // 2
    cv.alpha_composite(b, (o, o))
    cv.alpha_composite(r, (o, o))
    return cv.resize((F, F), Image.LANCZOS)


def knob_strip(colour, R, frames=128):
    F = 2 * R + 10
    strip = Image.new("RGBA", (F, F * frames), (0, 0, 0, 0))
    for i in range(frames):
        strip.paste(knob_frame(colour, R, -SWEEP + 2 * SWEEP * i / (frames - 1)), (0, i * F))
    return strip


def knob_static(im, cx, cy, colour, R, value=0.5):
    f = knob_frame(colour, R, -SWEEP + 2 * SWEEP * value)
    im.alpha_composite(f, (int(cx - f.size[0] / 2), int(cy - f.size[1] / 2)))


# ------------------------------------------------------------------------------------------------ small art
def led_strip(w, h, lit, colour, n=22, glow=True):
    """n LED capsules; the first `lit` are lit."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pitch = (w - 14) / n
    for i in range(n):
        x = 7 + i * pitch
        on = i < lit
        col = colour if on else (34, 34, 34)
        d.ellipse([x + 2, h * 0.22, x + pitch - 3, h * 0.78], fill=col + (255,))
        if on:
            d.ellipse([x + pitch * 0.28, h * 0.32, x + pitch * 0.62, h * 0.5], fill=tuple(min(255, c + 70) for c in colour) + (255,))
    return im


def jack_state_image(state, size=52):
    """1 cable, 2 held, 3 fits, 4 dim: drawn over a jack of the module panel."""
    S = 4
    im = Image.new("RGBA", (size * S, size * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = size * S / 2
    if state == 1:
        d.ellipse([c - 17 * S, c - 17 * S, c + 17 * S, c + 17 * S], outline=ORANGE + (255,), width=3 * S)
        d.ellipse([c - 6 * S, c - 6 * S, c + 6 * S, c + 6 * S], fill=ORANGE + (255,))
    elif state == 2:
        d.ellipse([c - 22 * S, c - 22 * S, c + 22 * S, c + 22 * S], fill=ORANGE + (200,), outline=(255, 255, 255, 255), width=4 * S)
    elif state == 3:
        d.ellipse([c - 22 * S, c - 22 * S, c + 22 * S, c + 22 * S], fill=ORANGE + (46,), outline=ORANGE + (255,), width=5 * S)
    elif state == 4:
        d.ellipse([c - 22 * S, c - 22 * S, c + 22 * S, c + 22 * S], fill=(14, 14, 14, 180))
    return im.resize((size, size), Image.LANCZOS)


def press_overlay(w, h, r=8):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=(255, 255, 255, 70), outline=ORANGE + (255,), width=4)
    return im


def blank(w=4, h=4):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))
