#!/usr/bin/env python3
"""Where every jack and control sits on each module's real panel (mm), read from the module widgets' constructors.
    python3 tools/extract_layout.py  ->  build/layout_mm.json
The widget code is plain arithmetic over `const float` values, loops and enum ids, so a small evaluator is enough; the
counts are checked against the module's own config (build/modules.json, from tools/introspect.cc)."""
import json, os, re, sys
R = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SRC = os.path.join(R, "third_party/AmbientModules/src")
MODS = json.load(open(os.path.join(R, "build/modules.json")))
CONST = {"NUM_METER_LEDS": 16, "NUM_OSC": 5, "NUM_STEPS": 5, "NUM_CHANNELS": 9, "NUM_PADS": 6}


def body_between(text, start_pat):
    m = re.search(start_pat, text)
    i = text.index("{", m.end()) if "{" not in m.group(0) else m.end() - 1
    depth, j = 0, i
    while True:
        if text[j] == "{": depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0: return text[i + 1:j]
        j += 1


def split_stmts(body):
    """-> list of ('stmt', text) / ('for', var, lo, hi, [stmts]) from a block"""
    out, i, n = [], 0, len(body)
    while i < n:
        while i < n and body[i] in " \t\r\n": i += 1
        if i >= n: break
        if body.startswith("//", i):
            i = body.index("\n", i) if "\n" in body[i:] else n; continue
        m = re.match(r"for \(int (\w+) = (\w+); \1 < ([\w:]+); \1\+\+\) \{", body[i:])
        if m:
            j = i + m.end() - 1; depth = 0; k = j
            while True:
                if body[k] == "{": depth += 1
                elif body[k] == "}":
                    depth -= 1
                    if depth == 0: break
                k += 1
            out.append(("for", m.group(1), m.group(2), m.group(3), split_stmts(body[j + 1:k])))
            i = k + 1; continue
        m = re.match(r"(if|while|for)\b", body[i:])
        if m:   # an unrelated block: skip it
            j = body.index("{", i); depth = 0; k = j
            while True:
                if body[k] == "{": depth += 1
                elif body[k] == "}":
                    depth -= 1
                    if depth == 0: break
                k += 1
            i = k + 1; continue
        # a statement ends at ';' outside parens/braces
        depth, k = 0, i
        while k < n:
            c = body[k]
            if c in "({[": depth += 1
            elif c in ")}]": depth -= 1
            elif c == ";" and depth == 0: break
            k += 1
        out.append(("stmt", body[i:k]))
        i = k + 1
    return out


def num(e, env):
    e = re.sub(r"(?<=[\d.])f\b", "", e)
    e = re.sub(r"\b(\w+)::(\w+)\b", lambda m: str(CONST.get(m.group(2), m.group(0))), e)
    return eval(e, {"__builtins__": {}}, env)


def run(stmts, env, rec, cls):
    for s in stmts:
        if s[0] == "for":
            _, v, lo, hi, inner = s
            for k in range(int(num(lo, env)), int(num(hi, env))):
                env2 = dict(env); env2[v] = k
                run(inner, env2, rec, cls)
            continue
        t = s[1].strip()
        m = re.match(r"(?:const )?(?:float|int)\s+(.*)$", t, re.S)
        if m:
            decl = m.group(1)
            ma = re.match(r"(\w+)\[[^\]]*\]\s*=\s*\{(.*)\}$", decl, re.S)
            if ma:
                env[ma.group(1)] = [num(x, env) for x in ma.group(2).split(",")]
                continue
            parts, depth, cur = [], 0, ""
            for c in decl:
                if c in "([": depth += 1
                if c in ")]": depth -= 1
                if c == "," and depth == 0: parts.append(cur); cur = ""
                else: cur += c
            parts.append(cur)
            for p in parts:
                if "=" in p:
                    k, e = p.split("=", 1)
                    try: env[k.strip()] = num(e, env)
                    except Exception: pass
            continue
        if t.startswith("add") and "mm2px" in t and not re.match(r"add(Input|Output|Param)", t): pass
        t = re.sub(r"^\w+\[\w+\]\s*=\s*create(\w+)<", r"addParam(create\1<", t) + (")" if re.match(r"^\w+\[\w+\]\s*=\s*create", t) else "")
        m = re.match(r"add(Input|Output|Param)\(create\w+<(.*?)>\(mm2px\(Vec\(", t, re.S)
        if m:
            kind, widget = m.group(1), m.group(2)
            i = m.end(); depth = 1; k = i
            while depth:
                if t[k] == "(": depth += 1
                elif t[k] == ")": depth -= 1
                k += 1
            xy = t[i:k - 1]
            depth, idx = 0, None
            for q, c in enumerate(xy):
                if c == "(": depth += 1
                elif c == ")": depth -= 1
                elif c == "," and depth == 0: idx = q; break
            x, y = num(xy[:idx], env), num(xy[idx + 1:], env)
            rest = t[k:]
            mr = re.match(r"\),\s*module,\s*" + cls + r"::(\w+)(?:\s*\+\s*(\w+))?", rest)
            if not mr:
                print("UNMATCHED:", " ".join(t.split())[:160], file=sys.stderr); continue
            sym, off = mr.groups()
            rec.append((kind.lower(), widget.strip(), sym, int(num(off, env)) if off else 0, round(x, 3), round(y, 3)))


def enum_ids(text, which):
    """enum ParamIds/InputIds/OutputIds -> {symbol: first id}"""
    m = re.search(r"enum %s \{(.*?)\n    \};" % which, text, re.S)
    ids, n = {}, 0
    block = re.sub(r"//[^\n]*", "", m.group(1))
    for item in re.split(r",\s*\n", block):
        item = re.sub(r"//.*", "", item).strip().rstrip(",")
        if not item: continue
        me = re.match(r"ENUMS\((\w+),\s*([\w:]+)\)", item)
        if me:
            ids[me.group(1)] = n
            c = CONST.get(me.group(2).split("::")[-1])
            if c is None: raise SystemExit("count of %s unknown" % me.group(2))
            n += c
        else:
            sym = item.split("=")[0].strip()
            if sym.startswith("NUM_"): continue
            ids[sym] = n; n += 1
    return ids, n


def main():
    out = {}
    for name in MODS:
        text = open("%s/%s.cpp" % (SRC, name)).read()
        cls = name
        pids, np_ = enum_ids(text, "ParamIds"); iids, ni = enum_ids(text, "InputIds"); oids, no = enum_ids(text, "OutputIds")
        body = body_between(text, r"struct %sWidget : ModuleWidget \{" % name)
        ctor = body_between(body, r"%sWidget\(%s\* module\) \{" % (name, name))
        rec = []
        run(split_stmts(ctor), {}, rec, cls)
        d = {"params": {}, "inputs": {}, "outputs": {}, "sym": {"params": {}, "inputs": {}, "outputs": {}}}
        for key, ids, n in (("params", pids, np_), ("inputs", iids, ni), ("outputs", oids, no)):
            order = sorted(ids.items(), key=lambda kv: kv[1])
            for q, (sy, first) in enumerate(order):
                last = order[q + 1][1] if q + 1 < len(order) else n
                for i in range(first, last):
                    d["sym"][key][str(i)] = sy + ("" if last - first == 1 else "+%d" % (i - first))
        for kind, widget, sym, off, x, y in rec:
            ids = {"param": pids, "input": iids, "output": oids}[kind]
            if sym not in ids: continue
            i = ids[sym] + off
            d[kind + "s"][str(i)] = {"x": x, "y": y, "w": widget}
        assert len(MODS[name]["params"]) == np_ and len(MODS[name]["inputs"]) == ni and len(MODS[name]["outputs"]) == no, name
        out[name] = d
        print("%-16s params %2d/%2d placed   inputs %2d/%2d   outputs %2d/%2d" % (
            name, len(d["params"]), np_, len(d["inputs"]), ni, len(d["outputs"]), no))
    json.dump(out, open(os.path.join(R, "build/layout_mm.json"), "w"), indent=1)


main()
