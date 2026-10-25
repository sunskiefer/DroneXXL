#!/usr/bin/env python3
"""Everything that follows from tools/spec.py, tools/ui.py and the converted presets:

    python3 tools/gen_params.py

  params.json        the VST parameter list for mpc-vst-plugins' gen_vst.py (index = order, append-only once shipped)
  build/gen/gen.h    P_* indices, per-type tables, jack tables, preset data for src/engine.cc
  presets.json       the PRESET menu: each entry sets `prs`, the engine loads that patch (params, data, cables)
"""
import json, os, re, sys
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec, ui, convert_presets

T = spec.types()


def trig(key, name, refresh=False):
    d = {"key": key, "name": name, "min": 0.0, "max": 1.0, "default": 0.0, "momentary": True, "type": "trigger"}
    if refresh:
        d["refresh_display"] = True
    return d


def knob01(key, name, default, **kw):
    d = {"key": key, "name": name, "min": 0.0, "max": 1.0, "default": default, "dynamic_display": True}
    d.update(kw)
    return d


def jack_key(t, kind, n):      # kind 'i' | 'o'
    return "%s_%s%d" % (T[t]["key"], kind, n)


def build():
    P = []
    P.append({"key": "level", "name": "Level", "min": 0.0, "max": 1.0, "default": 0.5, "dynamic_display": True})
    # 1. the module controls, per TYPE (the page of a slot edits that slot)
    for t in T:
        for i, p in enumerate(t["params"]):
            k = "%s_%d" % (t["key"], i)
            if p["kind"] == "button":   # a pad: the engine latches it (the module's own latch mode is a widget setting)
                P.append({"key": k, "name": p["name"], "options": ["Off", "On"], "default": 0})
            elif p["kind"] in ("toggle", "enum"):
                P.append({"key": k, "name": p["name"], "options": [ui.short_opt(l) for l in p["labels"]], "default": int(p["default"])})
            else:
                P.append({"key": k, "name": p["name"], "min": float(p["min"]), "max": float(p["max"]),
                          "default": float(p["default"]), "dynamic_display": True})
    # 2. performance
    for m in range(ui.NMACRO):
        P.append({"key": "m%d" % (m + 1), "name": "Macro %d" % (m + 1), "min": 0.0, "max": 1.0, "default": 0.0,
                  "dynamic_name": True, "dynamic_display": True})
    P.append({"key": "learn", "name": "Learn", "options": ["Off", "On"], "default": 0, "refresh_display": True})
    P.append(trig("m_clear", "Clear Macro", True))
    P.append({"key": "perf_info", "name": "Macro Info", "min": 0.0, "max": 0.0, "default": 0.0, "display": "string"})
    # 3. play
    P.append(knob01("px", "X", 0.5))
    P.append(knob01("py", "Y", 0.5))
    for r in range(ui.XY_ROWS):
        for c in range(ui.XY_COLS):
            P.append(trig("xy_%d_%d" % (c, r), "XY %d,%d" % (c + 1, r + 1), True))
    P.append({"key": "xy_pos", "name": "XY Cell", "options": [str(i) for i in range(ui.XY_COLS * ui.XY_ROWS)], "default": 17, "poll": False})
    P.append({"key": "xy_text", "name": "XY Text", "min": 0.0, "max": 0.0, "default": 0.0, "display": "string"})
    # 4. output
    P.append({"key": "ceil", "name": "Ceiling", "min": -24.0, "max": -1.0, "default": -3.0, "unit": "dB", "dynamic_display": True})
    P.append({"key": "rel", "name": "Release", "min": 10.0, "max": 1000.0, "default": 120.0, "unit": "ms", "display": "int", "dynamic_display": True})
    P.append({"key": "m_gr", "name": "GR Meter", "options": [str(i) for i in range(23)], "default": 0, "poll": False})
    P.append({"key": "m_pk", "name": "Peak Meter", "options": [str(i) for i in range(23)], "default": 0, "poll": False})
    P.append({"key": "out_src", "name": "Source", "options": ["Auto", "Filter", "Mixer"], "default": 0})
    P.append({"key": "out_info", "name": "Output Info", "min": 0.0, "max": 0.0, "default": 0.0, "display": "string"})
    # 5. random
    P.append({"key": "r_amount", "name": "Amount", "min": 0.0, "max": 100.0, "default": 50.0, "unit": "%", "display": "int"})
    P.append({"key": "r_min", "name": "Min Step", "min": 0.0, "max": 50.0, "default": 5.0, "unit": "%", "display": "int"})
    P.append({"key": "r_cables", "name": "Cables", "min": 0.0, "max": 8.0, "default": 2.0, "display": "int"})
    P.append({"key": "r_mode", "name": "Cable Mode", "options": ["Off", "Add", "Rewire"], "default": 1})
    P.append({"key": "r_scope", "name": "Scope", "options": ["All", "Module", "Macros", "Cables"], "default": 0})
    P.append(trig("r_go", "Randomize", True))
    P.append(trig("r_mode_step", "Cable Mode Step", True))
    for k, n in enumerate(("All", "Module", "Macros", "Cables")):
        P.append(trig("sc_%d" % k, "Scope " + n, True))
    P.append(trig("r_undo", "Undo", True))
    P.append({"key": "r_info", "name": "Random Info", "min": 0.0, "max": 0.0, "default": 0.0, "display": "string"})
    # 6. navigation
    P.append({"key": "view", "name": "View", "options": ui.view_names(), "default": 0, "refresh_display": True})
    for k, n in (("nav_ov", "Overview"), ("nav_prev", "Prev"), ("nav_next", "Next"), ("nav_perf", "Performance"),
                 ("nav_play", "Play"), ("nav_out", "Output"), ("nav_rand", "Random"), ("nav_ctrl", "Controls"),
                 ("nav_patch", "Patch")):
        P.append(trig(k, n, True))
    for s in range(ui.NSLOT):
        P.append(trig("go_%d" % s, "Go " + spec.slot_title(s).title(), True))
    P.append({"key": "hm", "name": "Header Mode", "options": ["Main", "Module", "Cable"], "default": 0, "poll": False})
    P.append({"key": "ttl", "name": "Page Title", "min": 0.0, "max": 0.0, "default": 0.0, "display": "string"})
    P.append({"key": "in_sec", "name": "In Section", "options": ["Overview", "Section"], "default": 0})
    P.append({"key": "vt", "name": "Type Page", "options": ["-"] + [t["title"].title() for t in T], "default": 0})
    P.append({"key": "pt", "name": "Patch Tiles", "options": ["-"] + [t["title"].title() for t in T], "default": 0})
    # 7. patching: a tile per jack of each type, the picture of its state, and the connected page
    for ti, t in enumerate(T):
        for j in t["ins"]:
            P.append(trig(jack_key(ti, "i", j["id"]), "Tap %s %s" % (t["title"].title(), j["name"]), True))
        for j in t["outs"]:
            P.append(trig(jack_key(ti, "o", j["id"]), "Tap %s %s" % (t["title"].title(), j["name"]), True))
    for ti, t in enumerate(T):
        for kind, js in (("i", t["ins"]), ("o", t["outs"])):
            for j in js:
                P.append({"key": "st_" + jack_key(ti, kind, j["id"]), "name": "State %s" % jack_key(ti, kind, j["id"]),
                          "options": ["-", "Cable", "Held", "Fit", "Dim"], "default": 0, "poll": False})
    for k, n in (("pk_cancel", "Cancel"), ("pk_done", "Done"), ("pk_unplug", "Unplug")):
        P.append(trig(k, n, True))
    P.append({"key": "pk_c", "name": "Cancel Shown", "options": ["Off", "On"], "default": 0})
    P.append({"key": "conn_a", "name": "Cable From", "min": 0.0, "max": 0.0, "default": 0.0, "display": "string"})
    P.append({"key": "conn_b", "name": "Cable To", "min": 0.0, "max": 0.0, "default": 0.0, "display": "string"})
    P.append({"key": "ct_o", "name": "Cable From Type", "options": ["-"] + [t["title"].title() for t in T], "default": 0, "poll": False})
    P.append({"key": "ct_i", "name": "Cable To Type", "options": ["-"] + [t["title"].title() for t in T], "default": 0, "poll": False})
    P.append({"key": "patch_info", "name": "Patch Info", "min": 0.0, "max": 0.0, "default": 0.0, "display": "string"})
    P.append({"key": "prs", "name": "Patch", "options": [p["name"] for p in PRESETS], "default": 0, "refresh_display": True})
    P += [{"key": "ql%d" % (i + 1), "name": "Q-Link %d" % (i + 1), "min": 0.0, "max": 1.0, "default": 0.0,
           "dynamic_name": True, "dynamic_display": True} for i in range(16)]
    keys = [p["key"] for p in P]
    assert len(keys) == len(set(keys)), "duplicate keys"
    return P


PRESETS = convert_presets.all_presets()


def fl(x):
    t = "%.7g" % float(x)
    return t + (".0f" if "." not in t and "e" not in t and "n" not in t else "f")


def write_header(P):
    idx = {p["key"]: i for i, p in enumerate(P)}
    L = ["// Generated by tools/gen_params.py -- do not edit.", "#pragma once", ""]
    for i, p in enumerate(P):
        L.append("#define P_%s %d" % (p["key"].upper(), i))
    L.append("#define P_COUNT %d" % len(P))
    L.append("#define NMACRO %d\n#define NPAD %d\n#define XY_COLS %d\n#define XY_ROWS %d\n#define MAX_CABLES %d\n#define HIST %d\n#define BINS %d" % (
        ui.NMACRO, ui.NPAD, ui.XY_COLS, ui.XY_ROWS, ui.MAX_CABLES, ui.HIST, ui.BINS))
    q = lambda s: '"%s"' % s
    L.append("static const char *const P_KEY[P_COUNT] = {%s};" % ", ".join(q(p["key"]) for p in P))
    L.append("static const char *const P_NAME[P_COUNT] = {%s};" % ", ".join(q(p["name"]) for p in P))
    L.append("static const float P_MIN[P_COUNT] = {%s};" % ", ".join(fl(p.get("min", 0)) for p in P))
    L.append("static const float P_MAX[P_COUNT] = {%s};" % ", ".join(
        (str(len(p["options"]) - 1) + ".0f") if "options" in p else fl(p.get("max", 1)) for p in P))
    L.append("static const float P_DEF[P_COUNT] = {%s};" % ", ".join(fl(p.get("default", 0)) for p in P))
    L.append("static const unsigned char P_NOPTS[P_COUNT] = {%s};" % ", ".join(str(len(p.get("options", []))) for p in P))
    for i, p in enumerate(P):
        if "options" in p:
            L.append("static const char *const OPTS_%d[] = {%s};" % (i, ", ".join(q(o) for o in p["options"])))
    L.append("static const char *const *const P_OPT[P_COUNT] = {%s};" % ", ".join(
        ("OPTS_%d" % i) if "options" in p else "0" for i, p in enumerate(P)))
    L.append("static const unsigned char P_INT[P_COUNT] = {%s};" % ", ".join("1" if p.get("display") == "int" else "0" for p in P))
    L.append("")
    L.append("// rack: slots and module types")
    L.append("#define NSLOT %d" % ui.NSLOT)
    L.append("#define NTYPE %d" % len(T))
    L.append("static const unsigned char SLOT_TYPE[NSLOT] = {%s};" % ", ".join(map(str, spec.SLOT_TYPE)))
    L.append("static const unsigned char SLOT_INST[NSLOT] = {%s};" % ", ".join(map(str, spec.SLOT_INST)))
    L.append("static const char *const SLOT_TITLE[NSLOT] = {%s};" % ", ".join(q(spec.slot_title(s)) for s in range(ui.NSLOT)))
    L.append("static const char *const T_MODEL[NTYPE] = {%s};" % ", ".join(q(t["model"]) for t in T))
    L.append("static const char *const T_TITLE[NTYPE] = {%s};" % ", ".join(q(t["title"]) for t in T))
    L.append("static const unsigned char T_NP[NTYPE] = {%s};" % ", ".join(str(len(t["params"])) for t in T))
    L.append("static const unsigned char T_NI[NTYPE] = {%s};" % ", ".join(str(len(t["ins"])) for t in T))
    L.append("static const unsigned char T_NO[NTYPE] = {%s};" % ", ".join(str(len(t["outs"])) for t in T))
    L.append("static const unsigned char T_NDATA[NTYPE] = {%s};" % ", ".join(
        str(len(spec.TYPE_DATA.get(t["model"], []))) for t in T))
    L.append("static const char *const T_DATA[NTYPE][2] = {%s};" % ", ".join(
        "{%s}" % ", ".join((q(k) for k in (spec.TYPE_DATA.get(t["model"], []) + ["", ""])[:2])) for t in T))
    # host index of each type's first control (controls are contiguous, in the module's own param order)
    L.append("static const short T_CBASE[NTYPE] = {%s};" % ", ".join("P_" + T[i]["key"].upper() + "_0" for i in range(len(T))))
    L.append("static const short T_TAPBASE[NTYPE] = {%s};" % ", ".join(
        "P_" + T[i]["key"].upper() + "_I0" if T[i]["ins"] else "P_" + T[i]["key"].upper() + "_O0" for i in range(len(T))))
    L.append("static const short T_JSBASE[NTYPE] = {%s};" % ", ".join(
        "P_ST_" + T[i]["key"].upper() + "_I0" if T[i]["ins"] else "P_ST_" + T[i]["key"].upper() + "_O0" for i in range(len(T))))
    # per-type param tables, flattened with an offset
    off, mn, mx, df, kd, nm = [], [], [], [], [], []
    o = 0
    for t in T:
        off.append(o)
        for p in t["params"]:
            mn.append(fl(p["min"])); mx.append(fl(p["max"])); df.append(fl(p["default"]))
            kd.append({"knob": 0, "toggle": 1, "enum": 2, "button": 3}[p["kind"]])
            nm.append(q(p["name"]))
        o += len(t["params"])
    L.append("#define NPTOT %d" % o)
    L.append("static const short T_POFF[NTYPE] = {%s};" % ", ".join(map(str, off)))
    L.append("static const float TP_MIN[NPTOT] = {%s};" % ", ".join(mn))
    L.append("static const float TP_MAX[NPTOT] = {%s};" % ", ".join(mx))
    L.append("static const float TP_DEF[NPTOT] = {%s};" % ", ".join(df))
    L.append("static const unsigned char TP_KIND[NPTOT] = {%s};" % ", ".join(map(str, kd)))
    L.append("static const char *const TP_NAME[NPTOT] = {%s};" % ", ".join(nm))
    rnd = []
    for t in T:
        for p in t["params"]:
            rnd.append("0" if (p["kind"] == "button" or p["sym"] in ("VU_PEAK_PARAM", "RANGE_X_PARAM", "RANGE_Y_PARAM")) else "1")
    L.append("static const unsigned char TP_RND[NPTOT] = {%s};" % ", ".join(rnd))
    # default macros: (label, [(slot, param index)])
    def find(model, name, inst=0):
        ti = spec.TYPE_OF[model]
        slot = [s for s in range(ui.NSLOT) if spec.SLOT_TYPE[s] == ti][inst]
        return slot, [p["name"] for p in T[ti]["params"]].index(name)
    DEF = [("CUTOFF", [find("LunarFilter", "FREQ L"), find("LunarFilter", "FREQ R")]),
           ("RESO", [find("LunarFilter", "RES L"), find("LunarFilter", "RES R")]),
           ("DRIVE", [find("LunarFilter", "BLEND")]),
           ("FX MIX", [find("LunarFilter", "D / W")]),
           ("VOLUME", [find("LunarMixer", "MASTER")]),
           ("LFO RATE", [find("LunarLFO", "A RATE"), find("LunarLFO", "B RATE")]),
           ("PITCH", [find("LunarPapaSrapa", "PITCH")]),
           ("MOD", [find("LunarFilter", "MOD L"), find("LunarFilter", "MOD R")])]
    assert len(DEF) == ui.NMACRO
    L.append("static const char *const DEFM_NAME[NMACRO] = {%s};" % ", ".join(q(d[0]) for d in DEF))
    L.append("static const unsigned char DEFM_N[NMACRO] = {%s};" % ", ".join(str(len(d[1])) for d in DEF))
    L.append("static const unsigned char DEFM_T[NMACRO][2][2] = {%s};" % ", ".join(
        "{%s}" % ", ".join("{%d,%d}" % tuple(d[1][k]) if k < len(d[1]) else "{0,0}" for k in range(2)) for d in DEF))
    # jacks
    ioff, ooff, iname, oname = [], [], [], []
    a = b = 0
    for t in T:
        ioff.append(a); ooff.append(b)
        iname += [q(j["name"]) for j in t["ins"]]; oname += [q(j["name"]) for j in t["outs"]]
        a += len(t["ins"]); b += len(t["outs"])
    L.append("#define NITOT %d" % a)
    L.append("#define NOTOT %d" % b)
    L.append("static const short T_IOFF[NTYPE] = {%s};" % ", ".join(map(str, ioff)))
    L.append("static const short T_OOFF[NTYPE] = {%s};" % ", ".join(map(str, ooff)))
    L.append("static const char *const TI_NAME[NITOT] = {%s};" % ", ".join(iname))
    L.append("static const char *const TO_NAME[NOTOT] = {%s};" % ", ".join(oname))
    # controls in reading order per type (Q-Links)
    L.append("static const unsigned char T_ORDER[NPTOT] = {%s};" % ", ".join(
        str(i) for t in T for i in ui.ctrl_order(t)))
    # pages
    L.append("#define V_OVERVIEW %d\n#define V_PERF %d\n#define V_PLAY %d\n#define V_OUTPUT %d\n#define V_RANDOM %d" % (
        ui.V_OVERVIEW, ui.V_PERF, ui.V_PLAY, ui.V_OUTPUT, ui.V_RANDOM))
    L.append("#define V_CTRL0 %d\n#define V_PATCH0 %d\n#define V_CONN %d\n#define NVIEW %d" % (ui.V_CTRL0, ui.V_PATCH0, ui.V_CONN, ui.NVIEW))
    # presets
    L.append("#define NPRESET %d" % len(PRESETS))
    L.append("struct PresetCable { unsigned char os, op, is, ip; };")
    L.append("struct PresetSlot { const float *v; signed char d0, d1; };")
    for pi, p in enumerate(PRESETS):
        for s, sl in enumerate(p["slots"]):
            L.append("static const float PV_%d_%d[] = {%s};" % (pi, s, ", ".join(fl(x) for x in sl["vals"])))
        L.append("static const PresetSlot PS_%d[NSLOT] = {%s};" % (pi, ", ".join(
            "{PV_%d_%d, %d, %d}" % (pi, s, sl["data"][0], sl["data"][1]) for s, sl in enumerate(p["slots"]))))
        L.append("static const PresetCable PC_%d[] = {%s{0,0,0,0}};" % (pi, "".join("{%d,%d,%d,%d}, " % c for c in p["cables"])))
    L.append("static const PresetSlot *const PRESET_SLOTS[NPRESET] = {%s};" % ", ".join("PS_%d" % i for i in range(len(PRESETS))))
    L.append("static const PresetCable *const PRESET_CABLES[NPRESET] = {%s};" % ", ".join("PC_%d" % i for i in range(len(PRESETS))))
    L.append("static const unsigned char PRESET_NCABLES[NPRESET] = {%s};" % ", ".join(str(len(p["cables"])) for p in PRESETS))
    L.append("static const char *const PRESET_NAME[NPRESET] = {%s};" % ", ".join(q(p["name"]) for p in PRESETS))
    L.append("")
    open(os.path.join(ROOT, "build/gen/gen.h"), "w").write("\n".join(L))


def main():
    P = build()
    json.dump({"name": "DroneXXL", "params": P}, open(os.path.join(ROOT, "params.json"), "w"), indent=1)
    write_header(P)
    json.dump({"presets": [{"name": p["name"], "values": {"prs": p["name"]}} for p in PRESETS]},
              open(os.path.join(ROOT, "presets.json"), "w"), indent=1)
    print("gen_params: %d host parameters" % len(P))


if __name__ == "__main__":
    main()
