#!/usr/bin/env python3
"""Turn the generated skin into the DroneXXL panel.

    python3 tools/post_skin.py "<skin dir>/Plugin Skins" [--preview build/preview]

gen_vst.py builds a working skin from build/layout.conf (tools/pages.py): one tab, every control placed. This script
then, in the built skin:
  - drops the framework's baked backgrounds and puts the approved stone panel under everything;
  - redraws the knob filmstrips as the coloured knobs (colour and size by the layout radius), the toggles as key caps with
    their own labels, the segments and styled buttons as key caps, and makes header, jack and rack taps transparent;
  - injects one picture per page (header, bars, labels, jack lists, module panels), switched by view / vt / pt / hm,
  - and the live overlays: the XY puck, the limiter meters, the randomizer's mode and scope, the jack states, the
    two module panels on the connected page. All are IndexedEnabling images right after the background, so every
    control stays on top and keeps its touches.
"""
import json, os, re, sys, copy

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import skinlib as S
import pages as PG
import art as A
import spec, ui

W, H = S.W, S.H
TAB = "DroneXXL|DroneXXL"
T = PG.T


# ------------------------------------------------------------------------------------------------ the skin's data
def load_param_keys():
    keys = []
    for line in open(os.path.join(ROOT, "build", "params.h")):
        m = re.match(r'\s*\{"([^"]+)",', line)
        if m:
            keys.append(m.group(1))
    return keys


class Skin:
    def __init__(self, folder):
        self.dir = folder
        self.path = os.path.join(folder, "TUI.json")
        self.tui = json.load(open(self.path))
        self.defs_list = self.tui["pageData"]["componentDefinitions"]["localComponentDefinitions"]
        self.defs = {d["key"]: d["value"] for d in self.defs_list}
        self.page = self.defs[TAB]
        self.keys = load_param_keys()
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.params = {p["key"]: p for p in json.load(open(os.path.join(ROOT, "params.json")))["params"]}

    def param_of(self, inst):
        for m in inst["handle remapping"]["map"]:
            if m["key"] == "Data" and m["value"].startswith("Parameter "):
                return self.keys[int(m["value"].split()[1])]
        return None

    def add_def(self, key, value):
        self.defs_list.append({"key": key, "value": value})
        self.defs[key] = value

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.tui, f, separators=(",", ":"))

    def save_img(self, name, im):
        im.save(os.path.join(self.dir, name), optimize=True)


def bounds(b):
    return [int(round(float(x))) for x in b.split()]


def bstr(x, y, w, h):
    return "%d %d %d %d" % (x, y, w, h)


def image_instance(name, img, x, y, w, h, handles, kind="Image"):
    return {"version": 2,
            "componentData": {"version": 1, "name": name, "type": "Image",
                              "data": {"version": 2, "imageType": "Regular", "colour": "0", "image": img}},
            "handle remapping": {"version": 1, "map": []},
            "bounds": {"version": 2, "acceptsHWFocus": "No", "showWhenDataModelInvalid": "Show", "whenVisible": "Always",
                       "boundsType": "Absolute", "bounds": bstr(x, y, w, h), "additionalInvalidatingHandles": handles}}


def when(skin, key, value):
    """IndexedEnabling handle: shown while option parameter `key` is at `value`"""
    return "IndexedEnabling/%d/%d/Parameter %d" % (value, len(skin.params[key]["options"]), skin.index[key])


# ------------------------------------------------------------------------------------------------ widget surgery
def write_knob_strips(skin):
    done = []
    for name in sorted(os.listdir(skin.dir)):
        m = re.match(r"sh_knob_r(\d+)\.png$", name)
        if not m:
            continue
        R = int(m.group(1))
        c = S.class_of_radius(R)
        if not c:
            raise SystemExit("knob radius %d belongs to no colour/size class" % R)
        S.knob_strip(c[0], R).save(os.path.join(skin.dir, name), optimize=True)
        done.append(R)
    return done


def item_index():
    """(key, kind) -> [items] from every page"""
    idx = {}
    pages = list(PG.PAGES["main"].values()) + PG.PAGES["type"]
    for items in pages:
        for it in items:
            if "key" in it:
                idx.setdefault(it["key"], []).append(it)
    return idx


def near(inst, cx, cy, tol=3):
    x, y, w, h = bounds(inst["bounds"]["bounds"])
    return abs(x + w / 2.0 - cx) <= tol and abs(y + h / 2.0 - cy) <= tol


def retype(skin, inst, template_key, newkey, w, h, mutate):
    if newkey not in skin.defs:
        d = copy.deepcopy(skin.defs[template_key])
        mutate(d)
        skin.add_def(newkey, d)
    inst["componentData"]["type"] = newkey
    x, y, _, _ = bounds(inst["bounds"]["bounds"])


def set_geometry(inst, cx, cy, w, h):
    inst["bounds"]["bounds"] = bstr(int(cx - w // 2), int(cy - h // 2), w, h)


def restyle_toggles(skin, items):
    comps = skin.page["componentsData"]
    n = 0
    for inst in comps:
        if not inst["componentData"]["type"].startswith("shToggle"):
            continue
        key = skin.param_of(inst)
        it = next((i for i in items.get(key, []) if i["kind"] == "key" and near(inst, i["cx"], i["cy"])), None)
        if it is None:
            raise SystemExit("toggle %s has no item at its place" % key)
        w, h = it["w"], it["h"]
        lab_off, lab_on = it["labels"]
        st_off = it["style"]
        st_on = it["on_style"]
        tag = "kcTog_%s_%dx%d" % (key, w, h)
        off = "kc_%s_%dx%d_off.png" % (key, w, h)
        on = "kc_%s_%dx%d_on.png" % (key, w, h)
        skin.save_img(off, A.keycap_image(w, h, lab_off, st_off))
        skin.save_img(on, A.keycap_image(w, h, lab_on, st_on))

        def mutate(d, w=w, h=h, off=off, on=on):
            d["componentsData"] = [s for s in d["componentsData"] if s["componentData"]["type"] != "Label"]
            for sub in d["componentsData"]:
                sub["bounds"]["bounds"] = bstr(0, 0, w, h)
                if sub["componentData"]["type"] == "Button":
                    sub["componentData"]["data"]["onImage"] = on
                    sub["componentData"]["data"]["offImage"] = off

        retype(skin, inst, inst["componentData"]["type"], tag, w, h, mutate)
        set_geometry(inst, it["cx"], it["cy"], w, h)
        n += 1
    return n


def restyle_triggers(skin, items):
    """every trigger: a transparent touch box with a press picture; styled taps are drawn key caps"""
    comps = skin.page["componentsData"]
    made = {}

    def blank_name(w, h):
        nm = "kc_blank.png"
        if nm not in made:
            skin.save_img(nm, A.blank())
            made[nm] = 1
        return nm

    def press_name(w, h):
        nm = "kc_press_%dx%d.png" % (w, h)
        if nm not in made:
            skin.save_img(nm, A.press_image(w, h))
            made[nm] = 1
        return nm

    hdr = {}
    for keys in (PG.MAIN_KEYS, PG.MOD_KEYS, PG.CONN_KEYS):
        for key, label, a, b in keys:
            hdr[(key, (a + b) // 2)] = (b - a, 52)
    count = 0
    for inst in comps:
        t = inst["componentData"]["type"]
        if not t.startswith("shTrig_"):
            continue
        key = skin.param_of(inst)
        x, y, w, h = bounds(inst["bounds"]["bounds"])
        cx, cy = x + w / 2.0, y + h / 2.0
        off = on = None
        it = next((i for i in items.get(key, []) if i["kind"] == "tap" and near(inst, i["cx"], i["cy"])), None)
        if it is not None and it["style"] and not it["bake"]:
            off = "kc_%s_%dx%d_off.png" % (key, it["w"], it["h"])
            on = "kc_%s_%dx%d_on.png" % (key, it["w"], it["h"])
            skin.save_img(off, A.keycap_image(it["w"], it["h"], it["label"], it["style"], 26))
            skin.save_img(on, A.keycap_image(it["w"], it["h"], it["label"], "orange", 26))
        elif key in ("pk_done", "pk_unplug", "pk_cancel"):
            if key == "pk_cancel" and near(inst, PG.PATCH_CANCEL[0], PG.PATCH_CANCEL[1]):
                bx, by, bw, bh = PG.PATCH_CANCEL[0], PG.PATCH_CANCEL[1], PG.PATCH_CANCEL[2], PG.PATCH_CANCEL[3]
            else:
                bx, by, bw, bh = PG.CONN_KEYS_ROW[key]
            lab = {"pk_done": "DONE", "pk_unplug": "UNPLUG", "pk_cancel": "CANCEL"}[key]
            sty = "red" if key == "pk_done" else "light"
            off = "kc_%s_%dx%d_off.png" % (key, bw, bh)
            on = "kc_%s_%dx%d_on.png" % (key, bw, bh)
            skin.save_img(off, A.keycap_image(bw, bh, lab, sty, 26))
            skin.save_img(on, A.keycap_image(bw, bh, lab, "orange", 26))
            w, h, cx, cy = bw, bh, bx, by
        else:
            mw, mh = (w, h)
            off = blank_name(mw, mh)
            on = press_name(mw, mh) if not key.startswith("xy_") and key != "r_mode_step" else blank_name(mw, mh)
            if key.startswith("sc_") or key == "r_mode_step":
                on = press_name(mw, mh)
        tag = "kcTrig_%s_%dx%d" % (key, w, h)

        def mutate(d, w=w, h=h, off=off, on=on):
            d["componentsData"] = [s for s in d["componentsData"] if s["componentData"]["type"] != "Label"]
            for sub in d["componentsData"]:
                sub["bounds"]["bounds"] = bstr(0, 0, w, h)
                if sub["componentData"]["type"] == "Button":
                    sub["componentData"]["data"]["offImage"] = off
                    sub["componentData"]["data"]["onImage"] = on

        retype(skin, inst, t, tag, w, h, mutate)
        set_geometry(inst, cx, cy, w, h)
        count += 1
    return count


def restyle_segments(skin):
    n = 0
    for key, d in list(skin.defs.items()):
        m = re.match(r"shSeg_(.+)_(\d+)$", key)
        if not m:
            continue
        pkey, seg = m.group(1), int(m.group(2))
        label = ui.short_opt(skin.params[pkey]["options"][seg]).upper() if False else skin.params[pkey]["options"][seg].upper()
        for sub in d["componentsData"]:
            if sub["componentData"]["type"] != "Button":
                continue
            _, _, w, h = bounds(sub["bounds"]["bounds"])
            data = sub["componentData"]["data"]
            skin.save_img(data["offImage"], A.keycap_image(w, h, label, "light", 24))
            skin.save_img(data["onImage"], A.keycap_image(w, h, label, "red", 24))
            n += 1
    return n


# ------------------------------------------------------------------------------------------------ overlays
def build_overlays(skin):
    """-> [image instances] (switched by parameters), written right after the page pictures"""
    ov = []
    save = skin.save_img

    # PLAY: the puck in the tapped cell (35 positions); xy_pos reads 0 off the page, so also require the page
    ball = A.ball(70)
    save("kc_ball.png", ball)
    cw, ch = PG.XY_W / float(ui.XY_COLS), PG.XY_H / float(ui.XY_ROWS)
    for r in range(ui.XY_ROWS):
        for c in range(ui.XY_COLS):
            pos = r * ui.XY_COLS + c
            cx, cy = PG.XY_X0 + cw * (c + 0.5), PG.XY_Y0 + ch * (r + 0.5)
            ov.append(image_instance("Puck", "kc_ball.png", int(cx - 35), int(cy - 35), 70, 70,
                                     [when(skin, "view", ui.V_PLAY), when(skin, "xy_pos", pos)]))

    # OUTPUT: the two meters (23 pictures each)
    for key, colour, y in (("m_gr", (255, 138, 31), 250), ("m_pk", (90, 200, 110), 398)):
        for n in range(23):
            nm = "kc_%s_%d.png" % (key, n)
            im = Image.new("RGBA", (400, 44), (0, 0, 0, 0))
            S.black_box(im, (0, 0, 399, 43))
            im.alpha_composite(S.led_strip(400, 44, n, colour, 22))
            save(nm, im)
            ov.append(image_instance("Meter", nm, 840, y - 0, 400, 44, [when(skin, "view", ui.V_OUTPUT), when(skin, key, n)]))

    # RANDOM: the cable mode key (3 labels) and the active scope key
    mode = [r for r in PG.PAGES["main"][ui.V_RANDOM] if r["kind"] == "tap" and r["key"] == "r_mode_step"][0]
    for n, lab in enumerate(("CABLES: OFF", "CABLES: ADD", "CABLES: REWIRE")):
        nm = "kc_rmode_%d.png" % n
        save(nm, A.keycap_image(mode["w"], mode["h"], lab, "light" if n == 0 else "red", 26))
        ov.append(image_instance("Mode", nm, mode["cx"] - mode["w"] // 2, mode["cy"] - mode["h"] // 2, mode["w"], mode["h"],
                                 [when(skin, "view", ui.V_RANDOM), when(skin, "r_mode", n)]))
    for k, lab in enumerate(("ALL", "MODULE", "MACROS", "CABLES")):
        it = [r for r in PG.PAGES["main"][ui.V_RANDOM] if r["kind"] == "tap" and r["key"] == "sc_%d" % k][0]
        nm = "kc_scope_%d.png" % k
        save(nm, A.keycap_image(it["w"], it["h"], lab, "red", 24))
        ov.append(image_instance("Scope", nm, it["cx"] - it["w"] // 2, it["cy"] - it["h"] // 2, it["w"], it["h"],
                                 [when(skin, "view", ui.V_RANDOM), when(skin, "r_scope", k)]))

    # PATCH: every jack's key and its place on the module panel show their state (1 cable, 2 held, 3 fits, 4 dimmed)
    for st in (1, 2, 3, 4):
        save("kc_jk_%d.png" % st, A.state_key(st, PG.KEY_W, PG.KEY_H))
        if st < 4:
            save("kc_jr_%d.png" % st, S.jack_state_image(st, 36))
    for t in range(len(T)):
        rows, _ = PG.jack_rows(t)
        for kind, n, label, cx, cy in rows:
            pk = "st_" + PG.jack_key(t, kind, n)
            jx, jy = A.jack_pos_on_panel(t, kind, n, PG.PANEL_H, PG.PANEL_X, PG.PANEL_Y)
            for st in (1, 2, 3, 4):
                ov.append(image_instance("JackKey", "kc_jk_%d.png" % st, cx - PG.KEY_W // 2, cy - PG.KEY_H // 2, PG.KEY_W, PG.KEY_H,
                                         [when(skin, pk, st)]))
                if st < 4:
                    ov.append(image_instance("JackRing", "kc_jr_%d.png" % st, int(jx - 18), int(jy - 18), 36, 36, [when(skin, pk, st)]))

    # CONNECTED: the two panels (by type) and the cable between them
    for t in range(len(T)):
        for left in (True, False):
            im, (x, y) = A.conn_panel(t, left)
            nm = "kc_conn_%s_%d.png" % ("o" if left else "i", t)
            save(nm, im)
            ov.append(image_instance("ConnPanel", nm, x, y, im.size[0], im.size[1],
                                     [when(skin, "ct_o" if left else "ct_i", t + 1)]))
    save("kc_cable.png", A.cable_arc((560, 120)))
    ov.append(image_instance("Cable", "kc_cable.png", 200, 300, 560, 120, [when(skin, "view", ui.V_CONN)]))
    return ov


def page_images(skin):
    """-> [(name, image instance)]: the page pictures with their switches"""
    out = []

    def add(name, im, handle):
        skin.save_img(name, im.convert("RGB"))
        out.append(image_instance("Page", name, 0, 0, W, H, [handle]))

    add("kc_page_ov.png", A.page_overview(), when(skin, "view", ui.V_OVERVIEW))
    for v in (ui.V_PERF, ui.V_PLAY, ui.V_OUTPUT, ui.V_RANDOM):
        add("kc_page_%d.png" % v, A.page_main(v), when(skin, "view", v))
    for t in range(len(T)):
        add("kc_ctrl_%d.png" % t, A.page_ctrl(t), when(skin, "vt", t + 1))
        add("kc_patch_%d.png" % t, A.page_patch(t), when(skin, "pt", t + 1))
    add("kc_page_conn.png", A.page_conn(), when(skin, "view", ui.V_CONN))
    return out


# ------------------------------------------------------------------------------------------------ preview
class Composer:
    """Draws a page as MPC would for a given state (param key -> value), from the skin itself."""

    def __init__(self, skin):
        self.skin = skin
        self.cache = {}

    def img(self, name):
        if name not in self.cache:
            self.cache[name] = Image.open(os.path.join(self.skin.dir, name)).convert("RGBA")
        return self.cache[name]

    def val(self, key, state):
        if key in state:
            return state[key]
        p = self.skin.params.get(key)
        return p.get("default", 0) if p else 0

    def shown(self, inst, state):
        for h in inst["bounds"]["additionalInvalidatingHandles"]:
            m = re.match(r"IndexedEnabling/(\d+)/(\d+)/Parameter (\d+)", h)
            if m and int(round(self.val(self.skin.keys[int(m.group(3))], state))) != int(m.group(1)):
                return False
        return True

    def norm(self, key, state):
        p = self.skin.params.get(key)
        if p is None:
            return 0.5
        v = self.val(key, state)
        if "options" in p:
            n = len(p["options"])
            return v / float(n - 1) if n > 1 else 0.0
        lo, hi = p.get("min", 0), p.get("max", 1)
        return (v - lo) / (hi - lo) if hi > lo else 0.0

    def compose(self, state, text=True):
        from PIL import ImageFont
        page = Image.new("RGBA", (W, H), (180, 172, 159, 255))
        d = ImageDraw.Draw(page)
        for inst in self.skin.page["componentsData"]:
            if not self.shown(inst, state):
                continue
            x, y, w, h = bounds(inst["bounds"]["bounds"])
            t = inst["componentData"]["type"]
            if t == "Image":
                name = inst["componentData"]["data"]["image"]
                if name:
                    im = self.img(name)
                    page.alpha_composite(im.resize((w, h)) if im.size != (w, h) else im, (x, y))
                continue
            dd = self.skin.defs.get(t)
            if not dd:
                continue
            key = self.skin.param_of(inst)
            for sub in dd["componentsData"]:
                st = sub["componentData"]["type"]
                sx, sy, sw, sh = bounds(sub["bounds"]["bounds"])
                data = sub["componentData"].get("data", {})
                if st == "Knob" and data.get("filmStrip"):
                    strip = self.img(data["filmStrip"])
                    F = strip.size[0]
                    fr = int(round(self.norm(key, state) * 127))
                    page.alpha_composite(strip.crop((0, fr * F, F, fr * F + F)).resize((sw, sh)), (x + sx, y + sy))
                elif st == "Button":
                    if sub["bounds"].get("whenVisible") == "WhenFocussed":
                        continue
                    n = data.get("numButtonsInGroup", 1)
                    v = self.val(key, state)
                    on = (int(round(v)) == data.get("buttonId", 0)) if n > 1 else False
                    if n == 1 and not (key or "").startswith(("nav_", "go_", "xy_", "pk_", "sc_", "r_", "m_clear")) and \
                            "options" in self.skin.params.get(key, {}):
                        on = bool(round(v))
                    name = data.get("onImage") if on else data.get("offImage")
                    if name:
                        im = self.img(name)
                        page.alpha_composite(im.resize((sw, sh)) if im.size != (sw, sh) else im, (x + sx, y + sy))
                elif st == "Label" and text:
                    td = data.get("textStyle", {})
                    size = td.get("font", {}).get("height", 24)
                    colour = "#" + td.get("colour", "ff000000")[2:]
                    kind = data.get("type", "")
                    p = self.skin.params.get(key, {})
                    if kind == "Name":
                        s = (p.get("name") or key or "").upper()
                    else:
                        s = self.sample(key, state)
                    f = ImageFont.truetype(os.path.join(S.ART, "fonts", "TitilliumWeb-SemiBold.ttf"), int(size))
                    ImageDraw.Draw(page).text((x + sx + sw / 2, y + sy + sh / 2), s, font=f, fill=colour, anchor="mm")
        return page

    def sample(self, key, state):
        p = self.skin.params.get(key, {})
        if key in ("ttl",):
            return state.get("_ttl", "MIXER")
        if p.get("display") == "string":
            return state.get("_" + key, key.upper())
        if "options" in p:
            return p["options"][int(self.val(key, state)) % len(p["options"])].upper()
        v = self.val(key, state)
        return ("%.2f" % v)[:6]


def compose_view(composer, v, extra=None):
    st = {"view": v, "hm": 2 if v == ui.V_CONN else (1 if v >= ui.V_CTRL0 else 0), "in_sec": 1 if v else 0}
    if ui.V_CTRL0 <= v < ui.V_PATCH0:
        st["vt"] = spec.SLOT_TYPE[v - ui.V_CTRL0] + 1
        st["_ttl"] = spec.slot_title(v - ui.V_CTRL0)
    if ui.V_PATCH0 <= v < ui.V_CONN:
        st["pt"] = spec.SLOT_TYPE[v - ui.V_PATCH0] + 1
        st["_ttl"] = spec.slot_title(v - ui.V_PATCH0)
    if v == ui.V_PLAY:
        st["xy_pos"] = 17
    if v == ui.V_OUTPUT:
        st["m_gr"], st["m_pk"] = 5, 14
    st.update(extra or {})
    return composer.compose(st)


def main():
    folder = sys.argv[1]
    preview = sys.argv[sys.argv.index("--preview") + 1] if "--preview" in sys.argv else None
    skin = Skin(folder)
    comps = skin.page["componentsData"]
    # 1) the framework's baked backgrounds go; the stone panel is the base
    comps[:] = [c for c in comps if not (c["componentData"]["type"] == "Image" and
                                         c["componentData"]["data"].get("image", "").startswith("sh_mode_"))]
    for name in os.listdir(folder):
        if name.startswith("sh_mode_"):
            os.remove(os.path.join(folder, name))
    S.base_page().convert("RGB").save(os.path.join(folder, "sh_bg_0.png"))
    # 2) widgets
    items = item_index()
    radii = write_knob_strips(skin)
    nt = restyle_toggles(skin, items)
    ntr = restyle_triggers(skin, items)
    nseg = restyle_segments(skin)
    # 3) pictures and overlays, right after the background so every control stays on top
    pics = page_images(skin)
    ovs = build_overlays(skin)
    comps[1:1] = [p for p in pics] + ovs
    skin.save()
    print("post_skin: knob radii %s, %d toggles, %d triggers, %d segments, %d pictures, %d overlays, %d components" % (
        radii, nt, ntr, nseg, len(pics), len(ovs), len(comps)))
    if preview:
        os.makedirs(preview, exist_ok=True)
        comp = Composer(skin)
        for v in range(ui.NVIEW):
            compose_view(comp, v).convert("RGB").save(os.path.join(preview, "view_%02d.png" % v))
        # patching states: an output held on the first Drone's patch page
        t = spec.SLOT_TYPE[ui.V_PATCH0 - ui.V_PATCH0]
        st = {"st_dr_i0": 3, "st_dr_i1": 3, "st_dr_o0": 2, "st_dr_o1": 4, "st_dr_i2": 1, "pk_c": 1}
        compose_view(comp, ui.V_PATCH0, st).convert("RGB").save(os.path.join(preview, "patch_held.png"))
        st = {"ct_o": 1, "ct_i": 2, "_conn_a": "SEQ 1  CV", "_conn_b": "DRONE 1  CV IN"}
        compose_view(comp, ui.V_CONN, st).convert("RGB").save(os.path.join(preview, "conn.png"))
        st = {"r_mode": 1, "r_scope": 2}
        compose_view(comp, ui.V_RANDOM, st).convert("RGB").save(os.path.join(preview, "random_state.png"))


if __name__ == "__main__":
    main()
