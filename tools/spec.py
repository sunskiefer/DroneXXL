"""The one source of truth for the rack: slots, module types, every control and jack, their labels and panel positions.
Everything else (params.json, gen.h, layout.conf, the skin art) is generated from this and build/modules.json (the modules'
own configuration, tools/introspect.cc) and build/layout_mm.json (their real panels, tools/extract_layout.py)."""
import json, os, re
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MODS = json.load(open(os.path.join(ROOT, "build/modules.json")))
MM = json.load(open(os.path.join(ROOT, "build/layout_mm.json")))

# rack slots, in the order of the overview (two rows of the pulsar patch)
SLOTS = ["Lunar50Drone", "Lunar50Drone", "LunarMixer", "LunarPads", "Lunar50Drone", "Lunar50Drone", "LunarFilter",
         "LunarPapaSrapa", "LunarVCO", "LunarLFO", "LunarJoystick", "LunarSequencer", "LunarDetector", "LunarVCO", "LunarPapaSrapa"]
# module types: (model, key, title, panel image, ctrl page columns)
TYPES = [("Lunar50Drone", "dr", "DRONE"), ("LunarMixer", "mx", "MIXER"), ("LunarFilter", "fl", "FILTER"),
         ("LunarPads", "pd", "PADS"), ("LunarPapaSrapa", "pp", "PAPASRAPA"), ("LunarVCO", "vc", "VCO"),
         ("LunarLFO", "lf", "LFOS"), ("LunarJoystick", "js", "JOYSTICK"), ("LunarSequencer", "sq", "SEQ"),
         ("LunarDetector", "dt", "DETECT")]
TYPE_OF = {m: i for i, (m, _, _) in enumerate(TYPES)}
SLOT_TYPE = [TYPE_OF[m] for m in SLOTS]
SLOT_INST = [sum(1 for k in range(i) if SLOT_TYPE[k] == SLOT_TYPE[i]) for i in range(len(SLOTS))]   # 0-based among its type
TYPE_COUNT = [sum(1 for t in SLOT_TYPE if t == i) for i in range(len(TYPES))]
def slot_title(s):
    t = TYPES[SLOT_TYPE[s]][2]
    return t + (" %d" % (SLOT_INST[s] + 1) if TYPE_COUNT[SLOT_TYPE[s]] > 1 else "")

# data saved with a module (menu items in Rack): key per type, up to two integers
TYPE_DATA = {"Lunar50Drone": ["fmTopology", "mixMode"], "LunarMixer": ["preferMixerOutput"], "LunarFilter": ["ioMode"],
             "LunarPads": ["latchMode"], "LunarLFO": ["cvRangeIndex"], "LunarSequencer": ["cvRangeIndex"]}

PN = {  # param label by enum symbol; +i is appended as number i+1
 "FREQ_PARAM": "TUNE", "ACTIVE_PARAM": "MUTE", "MOD_PARAM": "MOD", "ATTEN_PARAM": "CV ATT", "HOLD_PARAM": "HOLD",
 "ATTACK_PARAM": "ATTACK", "RELEASE_PARAM": "RELEASE", "VOLT_PARAM": "VOLT", "GAIN_PARAM": "GAIN", "DECAY_PARAM": "DECAY",
 "SUSTAIN_PARAM": "SUSTAIN",
 "FREQ_L_PARAM": "FREQ L", "RES_L_PARAM": "RES L", "TYPE_L_PARAM": "TYPE L", "FREQ_R_PARAM": "FREQ R", "RES_R_PARAM": "RES R",
 "TYPE_R_PARAM": "TYPE R", "MOD_L_PARAM": "MOD L", "MOD_R_PARAM": "MOD R", "DIST_PARAM": "BLEND", "DIST_MOD_PARAM": "DIST MOD",
 "LINK_PARAM": "LINK", "BLEND_PARAM": "D / W", "MASTER_PARAM": "MASTER", "BLEND_ATTEN_PARAM": "FX MOD",
 "X_PARAM": "X", "Y_PARAM": "Y", "X_OFFSET_PARAM": "X OFFSET", "Y_OFFSET_PARAM": "Y OFFSET", "RANGE_X_PARAM": "X RANGE",
 "RANGE_Y_PARAM": "Y RANGE",
 "WAVE_A_PARAM": "A WAVE", "RATE_A_PARAM": "A RATE", "WAVE_B_PARAM": "B WAVE", "RATE_B_PARAM": "B RATE",
 "PAN_PARAM": "PAN", "VOL_PARAM": "LEVEL", "MASTER_VOL_PARAM": "MASTER", "VU_PEAK_PARAM": "METER",
 "PAD_PARAM": "PAD", "RATE_PARAM": "RATE", "PITCH_PARAM": "PITCH", "FM_PARAM": "FM", "AM_PARAM": "AM",
 "DIVIDER_PARAM": "DIVIDER", "NOISE_PARAM": "NOISE", "NOISE_ONLY_PARAM": "NOISE ONLY",
 "STEP_CV_PARAM": "STEP", "STEP_GATE_PARAM": "GATE", "STAGES_PARAM": "STAGES",
 "WAVEFORM_PARAM": "WAVE", "TUNE_PARAM": "TUNE", "OCTAVE_PARAM": "OCTAVE", "SUB_PARAM": "SUB", "LINEXP_PARAM": "FM MODE",
 "SHAPE_PARAM": "SHAPE", "SHAPE_CV_ATTEN_PARAM": "SHAPE CV", "FM_CV_ATTEN_PARAM": "FM AMT", "SELFGEN_PARAM": "SELF GEN"}
PN_BY_MODEL = {("LunarPapaSrapa", "RATE_PARAM"): "LFO RATE", ("LunarPapaSrapa", "MOD_PARAM"): "MOD DEPTH",
               ("LunarSequencer", "RATE_PARAM"): "RATE", ("LunarFilter", "GAIN_PARAM"): "GAIN",
               ("LunarDetector", "ATTACK_PARAM"): "ATTACK"}
JN = {  # jack label by enum symbol
 "CV_INPUT": "CV IN", "TRIG_INPUT": "TRIG", "GATE_INPUT": "GATE", "VOLT_CV_INPUT": "VOLT CV", "ENV_INPUT": "ENV IN",
 "SAW_OUTPUT": "OUT", "ENV_OUTPUT": "ENV", "IN_INPUT": "SOURCE", "GATE_OUTPUT": "GATE",
 "IN_L_INPUT": "IN L", "IN_R_INPUT": "IN R", "CV_L_INPUT": "CV L", "CV_R_INPUT": "CV R", "DIST_CV_INPUT": "DIST CV",
 "RETURN_L_INPUT": "RETURN L", "RETURN_R_INPUT": "RETURN R", "BLEND_CV_INPUT": "FX CV",
 "OUT_L_OUTPUT": "OUT L", "OUT_R_OUTPUT": "OUT R", "SEND_L_OUTPUT": "SEND L", "SEND_R_OUTPUT": "SEND R",
 "X_INPUT": "X IN", "Y_INPUT": "Y IN", "X_OUTPUT": "X OUT", "Y_OUTPUT": "Y OUT", "LFO_A_OUTPUT": "LFO A", "LFO_B_OUTPUT": "LFO B",
 "CHANNEL_INPUT": "IN", "OUTPUT_L": "OUT L", "OUTPUT_R": "OUT R",
 "PITCH_CV_INPUT": "PITCH CV", "SH_CLOCK_INPUT": "S&H CLK", "SH_INPUT": "S&H IN", "MOD_CV_INPUT": "MOD CV",
 "DIVIDER_CV_INPUT": "DIV CV", "LFO_OUTPUT": "LFO", "VCO_OUT": "VCO", "SH_OUTPUT": "S&H",
 "CLOCK_INPUT": "CLOCK IN", "CV_OUTPUT": "CV", "CLOCK_OUTPUT": "CLOCK OUT",
 "VOCT_INPUT": "V/OCT", "FM_INPUT": "FM", "SHAPE_CV_INPUT": "SHAPE CV", "SYNC_INPUT": "SYNC", "VCO_OUTPUT": "AUDIO",
 "OSC_OUTPUT": "PHASE"}
JN_BY_MODEL = {("LunarPads", "GATE_INPUT"): "IN", ("LunarPads", "GATE_OUTPUT"): "GATE"}


def label(table, by_model, model, sym):
    base, _, off = sym.partition("+")
    t = by_model.get((model, base)) or table[base]
    return t + (" %d" % (int(off) + 1) if off else "")


def short(s, n):
    return s if len(s) <= n else s[:n]


class Param:
    pass


def build():
    """-> types: list of dict(model, key, title, params[], ins[], outs[], mm{...})"""
    out = []
    for mi, (model, key, title) in enumerate(TYPES):
        M, L = MODS[model], MM[model]
        t = dict(model=model, key=key, title=title, index=mi, count=TYPE_COUNT[mi])
        ps = []
        for p in M["params"]:
            sym = L["sym"]["params"][str(p["id"])]
            nm = label(PN, PN_BY_MODEL, model, sym)
            if p["snap"] and len(p["labels"]) == 2: kind = "toggle"
            elif p["snap"]: kind = "enum"
            else: kind = "knob"
            if model == "LunarPads": kind = "button"
            pos = L["params"].get(str(p["id"]))
            ps.append(dict(id=p["id"], sym=sym, name=nm, kind=kind, min=p["min"], max=p["max"], default=p["def"], unit=p["unit"],
                           labels=p["labels"], snap=p["snap"], x=pos["x"] if pos else None, y=pos["y"] if pos else None,
                           widget=pos["w"] if pos else "", cfg=p))
        ins = []
        for i, nm in enumerate(M["inputs"]):
            sym = L["sym"]["inputs"][str(i)]; pos = L["inputs"][str(i)]
            ins.append(dict(id=i, sym=sym, name=label(JN, JN_BY_MODEL, model, sym), x=pos["x"], y=pos["y"], full=nm))
        outs = []
        for i, nm in enumerate(M["outputs"]):
            sym = L["sym"]["outputs"][str(i)]; pos = L["outputs"][str(i)]
            outs.append(dict(id=i, sym=sym, name=label(JN, JN_BY_MODEL, model, sym), x=pos["x"], y=pos["y"], full=nm))
        t.update(params=ps, ins=ins, outs=outs)
        out.append(t)
    return out


TYPE_SPEC = None
def types():
    global TYPE_SPEC
    if TYPE_SPEC is None:
        TYPE_SPEC = build()
    return TYPE_SPEC


if __name__ == "__main__":
    for t in types():
        print(t["title"], len(t["params"]), "params", len(t["ins"]), "in", len(t["outs"]), "out")
        print("  ", [p["name"] for p in t["params"]])
        print("  in ", [j["name"] for j in t["ins"]], "out", [j["name"] for j in t["outs"]])
