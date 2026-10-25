#!/usr/bin/env python3
"""VCV patches (patches/vcv/*.json, slimmed by hand from Neil Baumberger's AmbientModules patches/ and the user's Pulsar_FORCE_1)
-> the rack's four factory presets. Only the Lunar modules and the cables between them are kept; every module goes to the
slot of its own type (the n-th Drone of the patch, ordered by position, to Drone n), and a type the patch lacks stays at its
defaults. Cables to anything else (MIDI, audio interfaces, other plugins) are dropped."""
import json, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec

ROOT = spec.ROOT
NAMES = {"Pulsar_FORCE_1": "Pulsar", "Solar42-patch": "Solar 42", "Solar42f-Cinematic-Performance": "Cinematic Performance",
         "Meditations-on-Death": "Meditations on Death"}
ORDER = ["Pulsar_FORCE_1", "Solar42-patch", "Solar42f-Cinematic-Performance", "Meditations-on-Death"]


def convert(path):
    d = json.load(open(path))
    types = spec.types()
    byid = {}
    slots = [None] * len(spec.SLOTS)
    for ti, (model, _, _) in enumerate(spec.TYPES):
        ms = [m for m in d["modules"] if m["plugin"] == "AmbientModules" and m["model"] == model]
        ms.sort(key=lambda m: (m["pos"][1], m["pos"][0]))
        mine = [s for s in range(len(spec.SLOTS)) if spec.SLOT_TYPE[s] == ti]
        for s, m in zip(mine, ms):
            slots[s] = m
            byid[m["id"]] = s
    out_slots = []
    for s in range(len(spec.SLOTS)):
        t = types[spec.SLOT_TYPE[s]]
        vals = [p["default"] for p in t["params"]]
        data = [0, 0]
        m = slots[s]
        if m:
            for p in m.get("params", []):
                if 0 <= p["id"] < len(vals):
                    vals[p["id"]] = float(p["value"])
            keys = spec.TYPE_DATA.get(t["model"], [])
            for i, k in enumerate(keys):
                if k in (m.get("data") or {}):
                    data[i] = int(m["data"][k])
        out_slots.append(dict(vals=vals, data=data, used=m is not None))
    cables = []
    seen = set()
    for c in d["cables"]:
        a, b = byid.get(c["outputModuleId"]), byid.get(c["inputModuleId"])
        if a is None or b is None:
            continue
        k = (a, c["outputId"], b, c["inputId"])
        if k in seen:
            continue
        if c["outputId"] >= len(types[spec.SLOT_TYPE[a]]["outs"]) or c["inputId"] >= len(types[spec.SLOT_TYPE[b]]["ins"]):
            continue
        seen.add(k)
        cables.append(k)
    return dict(slots=out_slots, cables=cables)


def all_presets():
    res = []
    for stem in ORDER:
        p = convert(os.path.join(ROOT, "patches/vcv", stem + ".json"))
        p["name"] = NAMES[stem]
        res.append(p)
    return res


if __name__ == "__main__":
    for p in all_presets():
        print(p["name"], "slots used", sum(s["used"] for s in p["slots"]), "cables", len(p["cables"]))
