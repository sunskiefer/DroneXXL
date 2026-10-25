// SPDX-License-Identifier: GPL-3.0-or-later
// DroneXXL -- Neil Baumberger's AmbientModules (Solar 42 style drone / experimental rack) as an MPC OS instrument.
// The fifteen modules' own DSP (third_party/AmbientModules, GPL-3.0-or-later) runs unchanged on a host-free Rack API
// shim (src/shim/rack.hpp); this file is the rack around them:
//
//   modules -> cable graph (Rack semantics: one sample of delay, several cables into an input add) -> main out
//   -> DC filter -> brickwall limiter (ceiling -3 dBFS by default, never above -1 dBFS, no bypass) -> int16
//
// and the UI side: pages (overview, performance macros with learn, play, output, random, the module pages and their
// patch pages), tap-to-patch cabling, the randomizer (1000 bins, 100-run exclusion, cables, undo), 16 Q-Links that follow
// the page, and a versioned state string that carries the whole rack and the randomizer's history.
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <time.h>
#include <new>
#include <vector>
#include <string>

#include <rack.hpp>
extern "C" {
#include "engine.h"
}
#include "gen.h"
#include "denormals.h"
#include "limiter.h"

extern Model *modelLunar50Drone, *modelLunarMixer, *modelLunarFilter, *modelLunarPads, *modelLunarPapaSrapa,
    *modelLunarVCO, *modelLunarLFO, *modelLunarJoystick, *modelLunarSequencer, *modelLunarDetector;

namespace {

const float SR = 44100.0f;
const int MAXT = 20;              // most controls of any type
const int MAXJ = 10;              // most jacks of one kind on any module
const int NMT = 8;                // targets per macro

inline float clampf(float x, float a, float b) { return x < a ? a : x > b ? b : x; }

struct Cab { uint8_t os, op, is, ip; };
struct Macro { float v; int nt; uint8_t slot[NMT], idx[NMT]; char name[24]; };
struct Hist { uint16_t b[HIST]; uint8_t n, head; };    // ring of the last runs' bins; newest at head - 1
struct Snap {
  bool valid;
  float v[NSLOT * MAXT];
  Cab cab[MAX_CABLES]; int ncab;
  float mv[NMACRO];
  Hist hist[NSLOT * MAXT + NMACRO];
  uint16_t ph[HIST][8]; uint8_t phn[HIST]; int ph_head, ph_count;
  int runs;
};

struct Rig {
  Module *mod[NSLOT];
  int pbase[NSLOT + 1];            // slot -> first global param id
  int nsp;                         // module params in the rack
  float pv[P_COUNT];               // host-side parameter values (non-module)
  int ctl_type[P_COUNT];           // host param -> type of the module control it is (or -1)
  int ctl_idx[P_COUNT];
  int ctl_first, ctl_last;

  Cab cab[MAX_CABLES]; int ncab;
  Macro mac[NMACRO];
  bool learn; int armed;

  // pages and patching
  int view, sel;
  int held_slot, held_out, held_port;
  int conn_k, conn_back;
  unsigned rev;
  char info[96], perf_info[96], rand_info[96], out_info[96], conn_a[48], conn_b[48];
  int ct_o, ct_i;
  int gr_pos, pk_pos, meter_tick; float pk_hold;

  // randomizer
  Hist hist[NSLOT * MAXT + NMACRO];
  uint16_t ph[HIST][8]; uint8_t phn[HIST]; int ph_head, ph_count;
  int runs;
  Snap snap;
  uint32_t rs;

  // audio
  plateau::Limiter lim;
  float dcx_l, dcx_r, dcy_l, dcy_r;
  int64_t frame;
  float dbg_peak[NSLOT][4];             // largest output voltage per module output since last read (a test aid)
  int zin_n; uint16_t zin[MAX_CABLES];   // inputs that a cable drives, cleared every sample

  // ---- construction ----------------------------------------------------------------------------------------------
  void init() {
    Model *models[NTYPE] = {modelLunar50Drone, modelLunarMixer, modelLunarFilter, modelLunarPads, modelLunarPapaSrapa,
                            modelLunarVCO, modelLunarLFO, modelLunarJoystick, modelLunarSequencer, modelLunarDetector};
    nsp = 0;
    for (int s = 0; s < NSLOT; s++) {
      pbase[s] = nsp;
      nsp += T_NP[SLOT_TYPE[s]];
      mod[s] = models[SLOT_TYPE[s]]->createModule();
      mod[s]->onSampleRateChange({SR, 1.0f / SR});
    }
    pbase[NSLOT] = nsp;
    for (int i = 0; i < P_COUNT; i++) { pv[i] = P_DEF[i]; ctl_type[i] = -1; ctl_idx[i] = 0; }
    ctl_first = T_CBASE[0];
    ctl_last = T_CBASE[NTYPE - 1] + T_NP[NTYPE - 1] - 1;
    for (int t = 0; t < NTYPE; t++)
      for (int i = 0; i < T_NP[t]; i++) { ctl_type[T_CBASE[t] + i] = t; ctl_idx[T_CBASE[t] + i] = i; }
    memset(hist, 0, sizeof hist);
    memset(ph, 0, sizeof ph); memset(phn, 0, sizeof phn);
    ph_head = ph_count = 0; runs = 0; snap.valid = false;
    ncab = 0; zin_n = 0;
    view = V_OVERVIEW; sel = 0; held_slot = -1; held_out = 0; held_port = 0; conn_k = -1; conn_back = V_OVERVIEW;
    rev = 1; learn = false; armed = -1;
    dcx_l = dcx_r = dcy_l = dcy_r = 0; frame = 0;
    lim.Init();
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    rs = (uint32_t)(ts.tv_nsec ^ (ts.tv_sec * 2654435761u)) | 1u;
    set_default_macros();
    load_preset(0);
    set_info_idle();
    snprintf(perf_info, sizeof perf_info, "Turn a macro. LEARN ON, then move any control to assign it.");
    snprintf(rand_info, sizeof rand_info, "Nothing randomized yet.");
    snprintf(out_info, sizeof out_info, "Limiter always on. Ceiling %.1f dB.", pv[P_CEIL]);
    ct_o = ct_i = 0; conn_a[0] = conn_b[0] = 0; gr_pos = pk_pos = 0; meter_tick = 0; pk_hold = 0;
  }

  void destroy() { for (int s = 0; s < NSLOT; s++) delete mod[s]; }

  void bump() { rev++; }

  // ---- random numbers --------------------------------------------------------------------------------------------
  uint32_t rnd32() { rs ^= rs << 13; rs ^= rs >> 17; rs ^= rs << 5; return rs; }
  float rnd() { return (rnd32() >> 8) * (1.0f / 16777216.0f); }

  // ---- module parameters -----------------------------------------------------------------------------------------
  int gp(int s, int i) const { return pbase[s] + i; }
  int tslot(int t) const {
    if (SLOT_TYPE[sel] == t) return sel;
    for (int s = 0; s < NSLOT; s++) if (SLOT_TYPE[s] == t) return s;
    return 0;
  }
  float sget(int s, int i) const { return mod[s]->params[i].getValue(); }
  float smin(int s, int i) const { return TP_MIN[T_POFF[SLOT_TYPE[s]] + i]; }
  float smax(int s, int i) const { return TP_MAX[T_POFF[SLOT_TYPE[s]] + i]; }
  int skind(int s, int i) const { return TP_KIND[T_POFF[SLOT_TYPE[s]] + i]; }
  bool ssnap(int s, int i) const { int k = skind(s, i); return k >= 1; }
  void sset(int s, int i, float v) {
    v = clampf(v, smin(s, i), smax(s, i));
    if (ssnap(s, i)) v = roundf(v);
    mod[s]->params[i].setValue(v);
  }
  float snorm(int s, int i) const {
    float lo = smin(s, i), hi = smax(s, i);
    return hi > lo ? (sget(s, i) - lo) / (hi - lo) : 0.0f;
  }
  void sset_norm(int s, int i, float x) { sset(s, i, smin(s, i) + clampf(x, 0, 1) * (smax(s, i) - smin(s, i))); }

  void set_data(int s, int d0, int d1) {
    int t = SLOT_TYPE[s];
    if (!T_NDATA[t]) return;
    json_t j;
    j.kv["v"] = 0;
    j.kv[T_DATA[t][0]] = d0;
    if (T_NDATA[t] > 1) j.kv[T_DATA[t][1]] = d1;
    mod[s]->dataFromJson(&j);
  }
  void get_data(int s, int *d) {
    d[0] = d[1] = 0;
    int t = SLOT_TYPE[s];
    if (!T_NDATA[t]) return;
    json_t *j = mod[s]->dataToJson();
    if (!j) return;
    for (int k = 0; k < T_NDATA[t]; k++) { auto it = j->kv.find(T_DATA[t][k]); if (it != j->kv.end()) d[k] = (int)it->second; }
    delete j;
  }

  // ---- cables ----------------------------------------------------------------------------------------------------
  int find_cable(int os, int op, int is, int ip) const {
    for (int k = 0; k < ncab; k++) if (cab[k].os == os && cab[k].op == op && cab[k].is == is && cab[k].ip == ip) return k;
    return -1;
  }
  int first_cable_at(int s, bool out, int port) const {
    for (int k = 0; k < ncab; k++)
      if (out ? (cab[k].os == s && cab[k].op == port) : (cab[k].is == s && cab[k].ip == port)) return k;
    return -1;
  }
  int cables_at(int s, bool out, int port) const {
    int n = 0;
    for (int k = 0; k < ncab; k++)
      if (out ? (cab[k].os == s && cab[k].op == port) : (cab[k].is == s && cab[k].ip == port)) n++;
    return n;
  }
  void rewire() {   // the connected flags and the list of inputs a cable drives
    for (int s = 0; s < NSLOT; s++) {
      for (auto &p : mod[s]->inputs) { p.connected = false; }
      for (auto &p : mod[s]->outputs) { p.connected = false; }
    }
    zin_n = 0;
    for (int k = 0; k < ncab; k++) {
      mod[cab[k].os]->outputs[cab[k].op].connected = true;
      Port &in = mod[cab[k].is]->inputs[cab[k].ip];
      if (!in.connected) { in.connected = true; zin[zin_n++] = (uint16_t)(cab[k].is * 16 + cab[k].ip); }
    }
    for (int s = 0; s < NSLOT; s++) if (SLOT_TYPE[s] == 1 || SLOT_TYPE[s] == 2) {   // the main out reads Mixer and Filter
      mod[s]->outputs[0].connected = true; mod[s]->outputs[1].connected = true;
    }
    for (int s = 0; s < NSLOT; s++)
      for (auto &p : mod[s]->inputs) if (!p.connected) { memset(p.voltages, 0, sizeof p.voltages); p.channels = 0; }
  }
  bool add_cable(int os, int op, int is, int ip) {
    if (os < 0 || os >= NSLOT || is < 0 || is >= NSLOT) return false;
    if (op >= T_NO[SLOT_TYPE[os]] || ip >= T_NI[SLOT_TYPE[is]]) return false;
    if (find_cable(os, op, is, ip) >= 0) return false;
    if (ncab >= MAX_CABLES) return false;
    cab[ncab].os = os; cab[ncab].op = op; cab[ncab].is = is; cab[ncab].ip = ip; ncab++;
    return true;
  }
  void remove_cable(int k) {
    if (k < 0 || k >= ncab) return;
    for (int j = k; j < ncab - 1; j++) cab[j] = cab[j + 1];
    ncab--;
    rewire();
  }
  const char *iname(int s, int p) const { return TI_NAME[T_IOFF[SLOT_TYPE[s]] + p]; }
  const char *oname(int s, int p) const { return TO_NAME[T_OOFF[SLOT_TYPE[s]] + p]; }

  // ---- presets ---------------------------------------------------------------------------------------------------
  void load_preset(int n) {
    if (n < 0 || n >= NPRESET) return;
    const PresetSlot *ps = PRESET_SLOTS[n];
    for (int s = 0; s < NSLOT; s++) {
      for (int i = 0; i < T_NP[SLOT_TYPE[s]]; i++) { sset(s, i, ps[s].v[i]); }
      set_data(s, ps[s].d0, ps[s].d1);
    }
    for (int s = 0; s < NSLOT; s++) if (SLOT_TYPE[s] == 3)       // the patches' drones sound while their pad gate is on
      for (int i = 0; i < T_NP[3]; i++) sset(s, i, 1.0f);
    ncab = 0;
    for (int k = 0; k < PRESET_NCABLES[n]; k++) {
      const PresetCable &c = PRESET_CABLES[n][k];
      add_cable(c.os, c.op, c.is, c.ip);
    }
    rewire();
    for (int s = 0; s < NSLOT; s++) mod[s]->onReset(ResetEvent());
    sync_macros();
    held_slot = -1;
    if (view == V_CONN) { view = conn_back; }
    pv[P_PRS] = (float)n;
    snap.valid = false;
    set_info_idle();
    bump();
  }

  // ---- macros ----------------------------------------------------------------------------------------------------
  void set_default_macros() {
    for (int m = 0; m < NMACRO; m++) {
      mac[m].v = 0; mac[m].nt = DEFM_N[m];
      snprintf(mac[m].name, sizeof mac[m].name, "%s", DEFM_NAME[m]);
      for (int k = 0; k < DEFM_N[m]; k++) { mac[m].slot[k] = DEFM_T[m][k][0]; mac[m].idx[k] = DEFM_T[m][k][1]; }
    }
  }
  void sync_macros() {
    for (int m = 0; m < NMACRO; m++) if (mac[m].nt > 0) mac[m].v = snorm(mac[m].slot[0], mac[m].idx[0]);
  }
  void apply_macro(int m) {
    for (int k = 0; k < mac[m].nt; k++) sset_norm(mac[m].slot[k], mac[m].idx[k], mac[m].v);
  }
  void macro_label(int m, char *b, int n) const {
    if (mac[m].nt == 0) { snprintf(b, n, "MACRO %d", m + 1); return; }
    snprintf(b, n, "%s", mac[m].name);
  }
  void describe_macro() {
    if (!learn) { snprintf(perf_info, sizeof perf_info, "Macros move the controls they hold. Turn LEARN ON to assign."); return; }
    if (armed < 0) { snprintf(perf_info, sizeof perf_info, "LEARN ON: turn a macro to choose it."); return; }
    snprintf(perf_info, sizeof perf_info, "LEARN: MACRO %d (%d held). Move any control.", armed + 1, mac[armed].nt);
  }
  void assign_macro(int s, int i) {
    if (!learn || armed < 0) return;
    Macro &M = mac[armed];
    for (int k = 0; k < M.nt; k++) if (M.slot[k] == s && M.idx[k] == i) return;
    if (M.nt >= NMT) { snprintf(perf_info, sizeof perf_info, "Macro %d is full (%d). CLEAR first.", armed + 1, NMT); return; }
    if (M.nt == 0) {
      M.v = snorm(s, i);
      const char *nm = TP_NAME[T_POFF[SLOT_TYPE[s]] + i];
      snprintf(M.name, sizeof M.name, "%s", nm);
    }
    M.slot[M.nt] = s; M.idx[M.nt] = i; M.nt++;
    snprintf(perf_info, sizeof perf_info, "Macro %d + %s %s (%d held)", armed + 1, SLOT_TITLE[s], TP_NAME[T_POFF[SLOT_TYPE[s]] + i], M.nt);
    bump();
  }
  void clear_macro() {
    int m = armed;
    if (m < 0) { snprintf(perf_info, sizeof perf_info, "Turn a macro first, then CLEAR."); bump(); return; }
    mac[m].nt = 0; snprintf(mac[m].name, sizeof mac[m].name, "MACRO %d", m + 1);
    snprintf(perf_info, sizeof perf_info, "Macro %d cleared.", m + 1);
    bump();
  }

  // ---- host control writes ---------------------------------------------------------------------------------------
  void set_control(int p, float v) {          // a module control, through the page's slot
    int t = ctl_type[p], i = ctl_idx[p];
    int s = tslot(t);
    float before = sget(s, i);
    sset(s, i, v);
    if (fabsf(sget(s, i) - before) > 1e-6f) assign_macro(s, i);
  }

  // ---- pages -----------------------------------------------------------------------------------------------------
  void set_info_idle() {
    if (held_slot >= 0)
      snprintf(info, sizeof info, "%s %s HELD: TAP %s", SLOT_TITLE[held_slot],
               held_out ? oname(held_slot, held_port) : iname(held_slot, held_port), held_out ? "AN INPUT" : "AN OUTPUT");
    else snprintf(info, sizeof info, "TAP A JACK, THEN THE OTHER END");
  }
  void set_view(int v) {
    if (v < 0 || v >= NVIEW) return;
    if (v >= V_CTRL0 && v < V_CONN) sel = (v - V_CTRL0) % NSLOT;
    if (v == V_CONN && (conn_k < 0 || conn_k >= ncab)) return;
    view = v;
    set_info_idle();
    describe_macro();
    bump();
  }
  bool on_patch() const { return view >= V_PATCH0 && view < V_CONN; }
  bool on_ctrl() const { return view >= V_CTRL0 && view < V_PATCH0; }
  void go_slot(int s) {
    sel = s;
    set_view(held_slot >= 0 ? V_PATCH0 + s : V_CTRL0 + s);
  }
  void nav_step(int d) {
    if (on_ctrl() || on_patch()) {
      int s = ((sel + d) % NSLOT + NSLOT) % NSLOT;
      set_view((on_patch() ? V_PATCH0 : V_CTRL0) + s);
    } else if (view >= V_PERF && view <= V_RANDOM) {
      int n = V_RANDOM - V_PERF + 1;
      set_view(V_PERF + ((view - V_PERF + d) % n + n) % n);
    }
  }

  void show_conn(int k) {
    conn_k = k; conn_back = on_patch() ? view : V_PATCH0 + sel;
    held_slot = -1;
    view = V_CONN;
    int n = 0;
    for (int j = 0; j < ncab; j++) if (cab[j].os == cab[k].os && cab[j].op == cab[k].op) n++;
    snprintf(info, sizeof info, "%s %s  ->  %s %s", SLOT_TITLE[cab[k].os], oname(cab[k].os, cab[k].op), SLOT_TITLE[cab[k].is],
             iname(cab[k].is, cab[k].ip));
    snprintf(conn_a, sizeof conn_a, "%s  %s", SLOT_TITLE[cab[k].os], oname(cab[k].os, cab[k].op));
    snprintf(conn_b, sizeof conn_b, "%s  %s", SLOT_TITLE[cab[k].is], iname(cab[k].is, cab[k].ip));
    ct_o = SLOT_TYPE[cab[k].os] + 1; ct_i = SLOT_TYPE[cab[k].is] + 1;
    (void)n;
    bump();
  }
  void tap_jack(int t, int n) {
    if (!on_patch() || SLOT_TYPE[sel] != t) return;
    bool out = n >= T_NI[t];
    int port = out ? n - T_NI[t] : n;
    int s = sel;
    if (held_slot < 0) {
      int k = first_cable_at(s, out, port);
      if (k >= 0) { show_conn(k); return; }
      held_slot = s; held_out = out; held_port = port;
    } else if (held_slot == s && held_out == (int)out && held_port == port) {
      held_slot = -1;
    } else if (held_out == (int)out) {
      held_slot = s; held_out = out; held_port = port;   // two outputs or two inputs: the new one is held
    } else {
      int os = out ? s : held_slot, op = out ? port : held_port, is = out ? held_slot : s, ip = out ? held_port : port;
      int k = find_cable(os, op, is, ip);
      if (k < 0 && add_cable(os, op, is, ip)) { rewire(); k = ncab - 1; }
      held_slot = -1;
      if (k >= 0) { show_conn(k); return; }
      snprintf(info, sizeof info, "RACK FULL (%d CABLES): UNPLUG ONE", MAX_CABLES);
      bump();
      return;
    }
    set_info_idle();
    bump();
  }
  void pk_unplug() {
    if (view == V_CONN && conn_k >= 0 && conn_k < ncab) {
      remove_cable(conn_k);
      conn_k = -1;
      view = conn_back; set_info_idle();
      snprintf(info, sizeof info, "UNPLUGGED");
      bump();
    }
  }
  void pk_done() {
    if (view == V_CONN) { view = conn_back; set_info_idle(); bump(); }
  }
  void pk_cancel() {
    held_slot = -1;
    if (view == V_CONN) view = conn_back;
    set_info_idle();
    bump();
  }

  // the stated picture of a jack tile on the current patch page: 0 plain, 1 patched, 2 held
  int jack_state(int t, int n) const {
    if (!on_patch() || SLOT_TYPE[sel] != t) return 0;
    bool out = n >= T_NI[t];
    int port = out ? n - T_NI[t] : n;
    if (held_slot >= 0) {
      if (held_slot == sel && held_out == (int)out && held_port == port) return 2;
      return held_out == (int)out ? 4 : 3;               // an output waits for an input, an input for an output
    }
    return cables_at(sel, out, port) > 0 ? 1 : 0;
  }

  // ---- Q-Links ---------------------------------------------------------------------------------------------------
  int ql_target(int i) const {
    if (on_ctrl()) {
      int t = SLOT_TYPE[sel];
      if (i < T_NP[t]) return T_CBASE[t] + T_ORDER[T_POFF[t] + i];
      return -1;
    }
    if (view == V_PERF) return i < NMACRO ? P_M1 + i : -1;
    if (view == V_PLAY) return i == 0 ? P_PX : i == 1 ? P_PY : -1;
    if (view == V_OUTPUT) return i == 0 ? P_LEVEL : i == 1 ? P_CEIL : -1;
    if (view == V_RANDOM) return i == 0 ? P_R_AMOUNT : i == 1 ? P_R_MIN : i == 2 ? P_R_CABLES : -1;
    return -1;
  }

  // ---- values as text and numbers --------------------------------------------------------------------------------
  float host_get(int p) const {
    if (p >= ctl_first && p <= ctl_last) return sget(tslot(ctl_type[p]), ctl_idx[p]);
    if (p >= P_M1 && p < P_M1 + NMACRO) return mac[p - P_M1].v;
    return pv[p];
  }
  float host_norm(int p) const {
    float lo = P_MIN[p], hi = P_MAX[p];
    return hi > lo ? clampf((host_get(p) - lo) / (hi - lo), 0, 1) : 0.0f;
  }
  void display(int p, char *buf, int n) const {
    if (p >= ctl_first && p <= ctl_last) {
      int t = ctl_type[p], i = ctl_idx[p], s = tslot(t);
      int k = TP_KIND[T_POFF[t] + i];
      if (k == 1 || k == 2) { snprintf(buf, n, "%s", P_OPT[p][(int)clampf(sget(s, i), 0, P_NOPTS[p] - 1)]); return; }
      ParamQuantity *q = mod[s]->getParamQuantity(i);
      std::string str = q ? q->getDisplayValueString() : std::string();
      std::string unit = q ? q->unit : std::string();
      if (!str.size()) snprintf(buf, n, "%.2f", sget(s, i));
      else if (unit.size() && str.find(unit) == std::string::npos) snprintf(buf, n, "%s %s", str.c_str(), unit.c_str());
      else snprintf(buf, n, "%s", str.c_str());
      return;
    }
    if (P_NOPTS[p]) { snprintf(buf, n, "%s", P_OPT[p][(int)clampf(host_get(p), 0, P_NOPTS[p] - 1)]); return; }
    float v = host_get(p);
    if (p == P_LEVEL) { float g = 4.0f * v * v; snprintf(buf, n, g > 0.0001f ? "%+.1f dB" : "-inf dB", 20.0f * log10f(fmaxf(g, 1e-6f))); return; }
    if (p == P_CEIL) { snprintf(buf, n, "%.1f dB", v); return; }
    if (p == P_REL) { snprintf(buf, n, "%d ms", (int)lroundf(v)); return; }
    if (p == P_PX || p == P_PY) { snprintf(buf, n, "%+.1f V", v * 10.0f - 5.0f); return; }
    if (p >= P_M1 && p < P_M1 + NMACRO) { snprintf(buf, n, "%d%%", (int)lroundf(v * 100.0f)); return; }
    if (p == P_R_AMOUNT || p == P_R_MIN) { snprintf(buf, n, "%d%%", (int)lroundf(v)); return; }
    if (p == P_R_CABLES) { snprintf(buf, n, "%d", (int)lroundf(v)); return; }
    snprintf(buf, n, "%g", v);
  }

  // ---- play ------------------------------------------------------------------------------------------------------
  void apply_play() {
    for (int s = 0; s < NSLOT; s++) if (SLOT_TYPE[s] == 7) {   // the joystick module: X and Y are -5..5 V
      sset(s, 0, pv[P_PX] * 10.0f - 5.0f);
      sset(s, 1, pv[P_PY] * 10.0f - 5.0f);
      break;
    }
  }
  void pad_set(int n, bool on) {
    for (int s = 0; s < NSLOT; s++) if (SLOT_TYPE[s] == 3) { sset(s, n, on ? 1.0f : 0.0f); break; }
    bump();
  }

  // ---- randomizer ------------------------------------------------------------------------------------------------
  Hist &H(int g) { return hist[g]; }
  void hist_push(Hist &h, int bin) {
    h.b[h.head] = (uint16_t)bin;
    h.head = (uint8_t)((h.head + 1) % HIST);
    if (h.n < HIST) h.n++;
  }
  int hist_at(const Hist &h, int k) const { return h.b[(h.head - 1 - k + 2 * HIST) % HIST]; }   // k = 0 newest

  // a new bin for a parameter: not one of the last runs' bins, at least minstep (0..1 of the range) from where it is
  int pick_bin(const Hist &h, float cur, int nopt, float amount, float minstep) {
    static bool forb[BINS];
    int bins = nopt > 0 ? nopt : BINS;
    memset(forb, 0, bins);
    int lim = nopt > 0 ? (nopt - 1 < HIST ? nopt - 1 : HIST) : HIST;
    int cnt = h.n < lim ? h.n : lim;
    for (int k = 0; k < cnt; k++) { int b = hist_at(h, k); if (b < bins) forb[b] = true; }
    auto val = [&](int b) { return nopt > 0 ? (nopt > 1 ? b / (float)(nopt - 1) : 0.0f) : (b + 0.5f) / BINS; };
    for (int t = 0; t < 48; t++) {
      float c = cur + (rnd() - cur) * amount;
      int b = nopt > 0 ? (int)lroundf(c * (nopt - 1)) : (int)(c * BINS);
      if (b < 0) b = 0; if (b >= bins) b = bins - 1;
      if (forb[b]) continue;
      if (fabsf(val(b) - cur) < minstep) continue;
      return b;
    }
    int cand[BINS], nc = 0, any[BINS], na = 0;
    for (int b = 0; b < bins; b++) {
      if (forb[b]) continue;
      any[na++] = b;
      if (fabsf(val(b) - cur) >= minstep) cand[nc++] = b;
    }
    if (nc) return cand[rnd32() % nc];
    if (na) return any[rnd32() % na];
    // every position was used lately (a switch with more history than positions): the longest ago
    int best = 0, bestage = -1;
    for (int b = 0; b < bins; b++) {
      int age = h.n;
      for (int k = 0; k < h.n; k++) if (hist_at(h, k) == b) { age = k; break; }
      if (age > bestage) { bestage = age; best = b; }
    }
    return best;
  }

  void snapshot() {
    snap.valid = true;
    for (int s = 0; s < NSLOT; s++) for (int i = 0; i < T_NP[SLOT_TYPE[s]]; i++) snap.v[gp(s, i)] = sget(s, i);
    memcpy(snap.cab, cab, sizeof cab); snap.ncab = ncab;
    for (int m = 0; m < NMACRO; m++) snap.mv[m] = mac[m].v;
    memcpy(snap.hist, hist, sizeof hist);
    memcpy(snap.ph, ph, sizeof ph); memcpy(snap.phn, phn, sizeof phn);
    snap.ph_head = ph_head; snap.ph_count = ph_count; snap.runs = runs;
  }
  void undo() {
    if (!snap.valid) { snprintf(rand_info, sizeof rand_info, "Nothing to undo."); bump(); return; }
    for (int s = 0; s < NSLOT; s++) for (int i = 0; i < T_NP[SLOT_TYPE[s]]; i++) sset(s, i, snap.v[gp(s, i)]);
    memcpy(cab, snap.cab, sizeof cab); ncab = snap.ncab;
    for (int m = 0; m < NMACRO; m++) mac[m].v = snap.mv[m];
    memcpy(hist, snap.hist, sizeof hist);
    memcpy(ph, snap.ph, sizeof ph); memcpy(phn, snap.phn, sizeof phn);
    ph_head = snap.ph_head; ph_count = snap.ph_count; runs = snap.runs;
    snap.valid = false;
    rewire();
    held_slot = -1;
    snprintf(rand_info, sizeof rand_info, "Undone. Run %d.", runs);
    bump();
  }

  bool pair_used(int code) const {
    for (int r = 0; r < ph_count; r++) {
      int row = (ph_head - 1 - r + 2 * HIST) % HIST;
      for (int k = 0; k < phn[row]; k++) if (ph[row][k] == code) return true;
    }
    return false;
  }

  int random_cables(int mode, int want, int *added_out) {
    int added = 0;
    if (mode == 2) { ncab = 0; }                       // rewire: all cables go, new ones come
    int tot_i = 0, tot_o = 0;
    for (int s = 0; s < NSLOT; s++) { tot_i += T_NI[SLOT_TYPE[s]]; tot_o += T_NO[SLOT_TYPE[s]]; }
    int row = ph_head;                                  // this run's row of pairs
    phn[row] = 0;
    for (int c = 0; c < want; c++) {
      bool ok = false;
      for (int t = 0; t < 300 && !ok; t++) {
        int oi = rnd32() % tot_o, ii = rnd32() % tot_i;
        int os = 0, op = 0, is = 0, ip = 0;
        for (int s = 0; s < NSLOT; s++) { int n = T_NO[SLOT_TYPE[s]]; if (oi < n) { os = s; op = oi; break; } oi -= n; }
        for (int s = 0; s < NSLOT; s++) { int n = T_NI[SLOT_TYPE[s]]; if (ii < n) { is = s; ip = ii; break; } ii -= n; }
        if (os == is) continue;                         // a module's own output into its own input: leave to the player
        int code = ((os * 16 + op) << 8) | (is * 16 + ip);
        if (find_cable(os, op, is, ip) >= 0 || pair_used(code) || phn[row] >= 8) continue;
        if (ncab >= MAX_CABLES) { for (int j = 0; j < ncab - 1; j++) cab[j] = cab[j + 1]; ncab--; }   // add: the oldest makes room
        if (!add_cable(os, op, is, ip)) continue;
        ph[row][phn[row]++] = (uint16_t)code;
        added++; ok = true;
      }
    }
    ph_head = (ph_head + 1) % HIST;
    if (ph_count < HIST) ph_count++;
    rewire();
    *added_out = added;
    return added;
  }

  void randomize() {
    int scope = (int)pv[P_R_SCOPE], mode = (int)pv[P_R_MODE];
    float amount = pv[P_R_AMOUNT] / 100.0f, minstep = pv[P_R_MIN] / 100.0f;
    int want = (int)lroundf(pv[P_R_CABLES]);
    if (scope == 3 && mode == 0) { snprintf(rand_info, sizeof rand_info, "CABLES scope, cable mode OFF: nothing to do."); bump(); return; }
    snapshot();
    int nparam = 0, nmac = 0, added = 0;
    bool do_params = scope == 0 || scope == 1;
    if (do_params) {
      for (int s = 0; s < NSLOT; s++) {
        if (scope == 1 && s != sel) continue;
        int t = SLOT_TYPE[s];
        for (int i = 0; i < T_NP[t]; i++) {
          if (!TP_RND[T_POFF[t] + i]) continue;
          int nopt = ssnap(s, i) ? (int)(smax(s, i) - smin(s, i)) + 1 : 0;
          if (nopt == 1) continue;
          int g = gp(s, i);
          int b = pick_bin(hist[g], snorm(s, i), nopt, amount, minstep);
          float x = nopt > 0 ? b / (float)(nopt - 1) : (b + 0.5f) / BINS;
          sset_norm(s, i, x);
          hist_push(hist[g], b);
          nparam++;
        }
      }
    }
    if (scope == 2) {
      for (int m = 0; m < NMACRO; m++) {
        int g = NSLOT * MAXT + m;
        int b = pick_bin(hist[g], mac[m].v, 0, amount, minstep);
        mac[m].v = (b + 0.5f) / BINS;
        hist_push(hist[g], b);
        apply_macro(m);
        nmac++;
      }
    }
    if ((scope == 0 || scope == 3) && mode != 0) {
      random_cables(mode, want, &added);
    } else {
      ph_head = ph_head;   // a run without cables leaves the pair history alone
    }
    runs++;
    sync_macros_after_random();
    held_slot = -1;
    char tmp[96];
    snprintf(tmp, sizeof tmp, "Run %d:", runs);
    int len = (int)strlen(tmp);
    if (nparam) len += snprintf(tmp + len, sizeof tmp - len, " %d params", nparam);
    if (nmac) len += snprintf(tmp + len, sizeof tmp - len, " %d macros", nmac);
    if (mode != 0 && (scope == 0 || scope == 3)) len += snprintf(tmp + len, sizeof tmp - len, " +%d cables (%d)", added, ncab);
    snprintf(rand_info, sizeof rand_info, "%s", tmp);
    bump();
  }
  void sync_macros_after_random() {
    for (int m = 0; m < NMACRO; m++) if (mac[m].nt > 0) mac[m].v = snorm(mac[m].slot[0], mac[m].idx[0]);
  }

  // ---- audio -----------------------------------------------------------------------------------------------------
  static inline float finite(float x) { return (x != x || x > 1e4f || x < -1e4f) ? 0.0f : x; }

  void render(int16_t *out, int frames) {
    ScopedDenormalDisable dg;
    float bl[128], br[128];
    int fs = -1, ms = -1;
    for (int s = 0; s < NSLOT; s++) { if (SLOT_TYPE[s] == 2 && fs < 0) fs = s; if (SLOT_TYPE[s] == 1 && ms < 0) ms = s; }
    int src = (int)pv[P_OUT_SRC];
    int use = src == 1 ? fs : src == 2 ? ms : (first_cable_at(fs, false, 0) >= 0 || first_cable_at(fs, false, 1) >= 0 ? fs : ms);
    float g = 4.0f * pv[P_LEVEL] * pv[P_LEVEL] * (1.0f / 5.0f);          // Rack's 5 V peak = full scale
    ProcessArgs args; args.sampleRate = SR; args.sampleTime = 1.0f / SR;
    for (int n = 0; n < frames; n++) {
      args.frame = frame++;
      for (int s = 0; s < NSLOT; s++) mod[s]->process(args);
      for (int s = 0; s < NSLOT; s++) {
        Module *m = mod[s];
        for (auto &o : m->outputs) {
          if (!o.connected) continue;
          int nc = o.channels < 1 ? 1 : o.channels;
          for (int c = 0; c < nc; c++) o.voltages[c] = finite(o.voltages[c]);
        }
        for (int q = 0; q < 4 && q < (int)m->outputs.size(); q++) { float a = fabsf(m->outputs[q].voltages[0]); if (a > dbg_peak[s][q]) dbg_peak[s][q] = a; }
      }
      bl[n] = mod[use]->outputs[0].voltages[0] * g;
      br[n] = mod[use]->outputs[1].voltages[0] * g;
      // cables: clear what they drive, then add every source (Rack: several cables into one input sum)
      for (int z = 0; z < zin_n; z++) {
        Port &in = mod[zin[z] >> 4]->inputs[zin[z] & 15];
        memset(in.voltages, 0, sizeof in.voltages); in.channels = 0;
      }
      for (int k = 0; k < ncab; k++) {
        const Port &o = mod[cab[k].os]->outputs[cab[k].op];
        Port &in = mod[cab[k].is]->inputs[cab[k].ip];
        int nc = o.channels < 1 ? 1 : o.channels;
        for (int c = 0; c < nc; c++) in.voltages[c] += o.voltages[c];
        if (nc > in.channels) in.channels = (uint8_t)nc;
      }
    }
    // DC blocker, then the brickwall
    for (int n = 0; n < frames; n++) {
      float yl = bl[n] - dcx_l + 0.9995f * dcy_l, yr = br[n] - dcx_r + 0.9995f * dcy_r;
      dcx_l = bl[n]; dcx_r = br[n]; dcy_l = yl; dcy_r = yr;
      bl[n] = yl; br[n] = yr;
    }
    float ceil_db = clampf(pv[P_CEIL], -24.0f, -1.0f);   // never above -1 dBFS
    lim.Process(bl, br, frames, 0.0f, ceil_db, clampf(pv[P_REL], 10.0f, 1000.0f), SR);
    float bp = 0;
    for (int n = 0; n < frames; n++) bp = fmaxf(bp, fmaxf(fabsf(bl[n]), fabsf(br[n])));
    pk_hold = fmaxf(bp, pk_hold * 0.96f);
    int gp2 = (int)ceilf(clampf(-lim.gr_db, 0.0f, 22.0f) - 0.01f);
    int pp2 = (int)clampf((20.0f * log10f(fmaxf(pk_hold, 1e-6f)) + 44.0f) / 2.0f, 0.0f, 22.0f);
    if (gp2 != gr_pos || pp2 != pk_pos) { gr_pos = gp2; pk_pos = pp2; if (view == V_OUTPUT && ++meter_tick >= 4) { meter_tick = 0; bump(); } }
    for (int n = 0; n < frames; n++) {
      float a = bl[n] * 32767.0f, b = br[n] * 32767.0f;
      out[n * 2] = (int16_t)(a > 32767.0f ? 32767 : a < -32768.0f ? -32768 : lrintf(a));
      out[n * 2 + 1] = (int16_t)(b > 32767.0f ? 32767 : b < -32768.0f ? -32768 : lrintf(b));
    }
  }

  void midi(const uint8_t *m, int len) {
    if (len < 3) return;
    int st = m[0] & 0xF0;                                   // notes 36..41 hold the six pads
    if (m[1] >= 36 && m[1] < 36 + NPAD) {
      if (st == 0x90 && m[2] > 0) pad_set(m[1] - 36, true);
      else if (st == 0x80 || st == 0x90) pad_set(m[1] - 36, false);
    }
  }

  // ---- state -----------------------------------------------------------------------------------------------------
  // bit packing for the history: base64 of a little bit stream
  struct Bits {
    std::string out; uint32_t acc; int nb;
    Bits() : acc(0), nb(0) {}
    void put(uint32_t v, int bits) {
      for (int i = 0; i < bits; i++) {
        acc |= ((v >> i) & 1u) << nb;
        if (++nb == 6) { out.push_back(b64(acc)); acc = 0; nb = 0; }
      }
    }
    void flush() { if (nb) { out.push_back(b64(acc)); acc = 0; nb = 0; } }
    static char b64(uint32_t v) { return "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-"[v & 63]; }
  };
  struct BitsIn {
    const char *p; uint32_t acc; int nb;
    BitsIn(const char *s) : p(s), acc(0), nb(0) {}
    static int dec(char c) {
      if (c >= 'A' && c <= 'Z') return c - 'A';
      if (c >= 'a' && c <= 'z') return 26 + c - 'a';
      if (c >= '0' && c <= '9') return 52 + c - '0';
      if (c == '+') return 62;
      if (c == '-') return 63;
      return -1;
    }
    uint32_t get(int bits) {
      uint32_t v = 0;
      for (int i = 0; i < bits; i++) {
        if (nb == 0) { int d = *p ? dec(*p) : 0; if (*p) p++; acc = d < 0 ? 0 : d; nb = 6; }
        v |= (acc & 1u) << i; acc >>= 1; nb--;
      }
      return v;
    }
  };

  std::string history_string(int keep) const {
    Bits b;
    int total = NSLOT * MAXT + NMACRO;
    for (int g = 0; g < total; g++) {
      const Hist &h = hist[g];
      int n = h.n < keep ? h.n : keep;
      b.put(n, 7);
      for (int k = n - 1; k >= 0; k--) b.put(hist_at(h, k), 10);      // oldest first
    }
    int rows = ph_count < keep ? ph_count : keep;
    b.put(rows, 7);
    for (int r = rows - 1; r >= 0; r--) {
      int row = (ph_head - 1 - r + 2 * HIST) % HIST;
      b.put(phn[row], 4);
      for (int k = 0; k < phn[row]; k++) b.put(ph[row][k], 16);
    }
    b.flush();
    return b.out;
  }
  void load_history(const char *s) {
    BitsIn b(s);
    int total = NSLOT * MAXT + NMACRO;
    memset(hist, 0, sizeof hist);
    for (int g = 0; g < total; g++) {
      int n = b.get(7);
      if (n > HIST) n = HIST;
      Hist &h = hist[g];
      for (int k = 0; k < n; k++) hist_push(h, (int)b.get(10) % BINS);
    }
    int rows = b.get(7);
    if (rows > HIST) rows = HIST;
    memset(ph, 0, sizeof ph); memset(phn, 0, sizeof phn);
    ph_head = ph_count = 0;
    for (int r = 0; r < rows; r++) {
      int n = b.get(4);
      if (n > 8) n = 8;
      for (int k = 0; k < n; k++) ph[ph_head][k] = (uint16_t)b.get(16);
      phn[ph_head] = (uint8_t)n;
      ph_head = (ph_head + 1) % HIST; ph_count++;
    }
  }

  int save(char *buf, int cap) const {
    std::string o;
    char t[128];
    o += "dxxl 1;";
    snprintf(t, sizeof t, "prs=%d;sel=%d;runs=%d;", (int)pv[P_PRS], sel, runs); o += t;
    static const int HP[] = {P_LEVEL, P_CEIL, P_REL, P_OUT_SRC, P_R_AMOUNT, P_R_MIN, P_R_CABLES, P_R_MODE, P_R_SCOPE};
    for (int p : HP) { snprintf(t, sizeof t, "%s=%g;", P_KEY[p], pv[p]); o += t; }
    for (int s = 0; s < NSLOT; s++) {
      int d[2]; const_cast<Rig *>(this)->get_data(s, d);
      snprintf(t, sizeof t, "s%d=%d,%d", s, d[0], d[1]); o += t;
      for (int i = 0; i < T_NP[SLOT_TYPE[s]]; i++) { snprintf(t, sizeof t, ",%g", sget(s, i)); o += t; }
      o += ";";
    }
    o += "cb=";
    for (int k = 0; k < ncab; k++) { snprintf(t, sizeof t, "%s%d.%d.%d.%d", k ? "," : "", cab[k].os, cab[k].op, cab[k].is, cab[k].ip); o += t; }
    o += ";";
    for (int m = 0; m < NMACRO; m++) {
      snprintf(t, sizeof t, "mc%d=%g,%s", m, mac[m].v, mac[m].name); o += t;
      for (int k = 0; k < mac[m].nt; k++) { snprintf(t, sizeof t, ",%d.%d", mac[m].slot[k], mac[m].idx[k]); o += t; }
      o += ";";
    }
    // the history goes last, as much of it as the buffer takes
    int keep = HIST;
    std::string h;
    for (;;) {
      h = history_string(keep);
      if ((int)(o.size() + h.size() + 8) < cap || keep == 0) break;
      keep = keep * 2 / 3;
    }
    o += "hist=" + h + ";";
    if ((int)o.size() >= cap) return -1;
    memcpy(buf, o.c_str(), o.size() + 1);
    return (int)o.size();
  }

  void load(const char *st) {
    if (strncmp(st, "dxxl", 4)) return;
    const char *q = strchr(st, ';');
    ncab = 0;
    bool sawcab = false;
    int prs = -1;
    std::string item;
    while (q && *++q) {
      const char *e = strchr(q, ';');
      if (!e) break;
      item.assign(q, e - q);
      q = e;
      size_t eq = item.find('=');
      if (eq == std::string::npos) continue;
      std::string k = item.substr(0, eq);
      const char *v = item.c_str() + eq + 1;
      if (k == "prs") prs = atoi(v);
      else if (k == "sel") sel = (int)clampf((float)atoi(v), 0, NSLOT - 1);
      else if (k == "runs") runs = atoi(v);
      else if (k == "hist") load_history(v);
      else if (k == "cb") {
        sawcab = true;
        const char *c = v;
        while (*c) {
          int a, b2, cc, d, n = 0;
          if (sscanf(c, "%d.%d.%d.%d%n", &a, &b2, &cc, &d, &n) >= 4) { add_cable(a, b2, cc, d); c += n; }
          else break;
          if (*c == ',') c++;
        }
      } else if (k[0] == 's' && k.size() > 1 && isdigit((unsigned char)k[1])) {
        int s = atoi(k.c_str() + 1);
        if (s < 0 || s >= NSLOT) continue;
        const char *c = v;
        int d0 = (int)strtol(c, (char **)&c, 10); if (*c == ',') c++;
        int d1 = (int)strtol(c, (char **)&c, 10);
        set_data(s, d0, d1);
        for (int i = 0; i < T_NP[SLOT_TYPE[s]] && *c == ','; i++) { c++; sset(s, i, strtof(c, (char **)&c)); }
      } else if (k[0] == 'm' && k[1] == 'c' && isdigit((unsigned char)k[2])) {
        int m = atoi(k.c_str() + 2);
        if (m < 0 || m >= NMACRO) continue;
        char *c = (char *)v;
        mac[m].v = strtof(c, &c);
        mac[m].nt = 0;
        if (*c == ',') {
          c++;
          char *comma = strchr(c, ',');
          size_t nl = comma ? (size_t)(comma - c) : strlen(c);
          if (nl > 23) nl = 23;
          memcpy(mac[m].name, c, nl); mac[m].name[nl] = 0;
          c = comma ? comma : c + strlen(c);
          while (*c == ',' && mac[m].nt < NMT) {
            int a, b2, n = 0;
            if (sscanf(c + 1, "%d.%d%n", &a, &b2, &n) >= 2 && a >= 0 && a < NSLOT && b2 >= 0 && b2 < T_NP[SLOT_TYPE[a]]) {
              mac[m].slot[mac[m].nt] = a; mac[m].idx[mac[m].nt] = b2; mac[m].nt++;
            }
            c += 1 + (n > 0 ? n : 0);
            if (n <= 0) break;
          }
        }
      } else {
        for (int p = 0; p < P_COUNT; p++) if (!strcmp(P_KEY[p], k.c_str())) { pv[p] = clampf((float)atof(v), P_MIN[p], P_MAX[p]); break; }
      }
    }
    (void)sawcab;
    if (prs >= 0 && prs < NPRESET) pv[P_PRS] = (float)prs;
    rewire();
    for (int s = 0; s < NSLOT; s++) mod[s]->onReset(ResetEvent());
    for (int s = 0; s < NSLOT; s++) if (SLOT_TYPE[s] == 7) { pv[P_PX] = (sget(s, 0) + 5.0f) / 10.0f; pv[P_PY] = (sget(s, 1) + 5.0f) / 10.0f; break; }
    held_slot = -1; view = V_OVERVIEW;
    snap.valid = false;
    set_info_idle();
    bump();
  }
};

// ---- parameter keys ----------------------------------------------------------------------------------------------
int find_key(const char *k) {
  static int table[2048];
  static bool built = false;
  auto h = [](const char *s) { uint32_t x = 2166136261u; while (*s) x = (x ^ (unsigned char)*s++) * 16777619u; return x; };
  if (!built) {
    for (int i = 0; i < 2048; i++) table[i] = -1;
    for (int i = 0; i < P_COUNT; i++) {
      uint32_t s = h(P_KEY[i]) & 2047;
      while (table[s] >= 0) s = (s + 1) & 2047;
      table[s] = i;
    }
    built = true;
  }
  uint32_t s = h(k) & 2047;
  while (table[s] >= 0) {
    if (!strcmp(P_KEY[table[s]], k)) return table[s];
    s = (s + 1) & 2047;
  }
  return -1;
}

void *create(const char *) {
  void *mem = calloc(1, sizeof(Rig));
  if (!mem) return nullptr;
  Rig *r = new (mem) Rig();
  r->init();
  return r;
}
void destroy(void *inst) {
  Rig *r = (Rig *)inst;
  r->destroy();
  r->~Rig();
  free(r);
}
void midi(void *inst, const uint8_t *m, int len) { ((Rig *)inst)->midi(m, len); }

void set_param(void *inst, const char *key, const char *val) {
  Rig *r = (Rig *)inst;
  float v = (float)atof(val);
  if (!strcmp(key, "state")) { r->load(val); return; }
  int p = find_key(key);
  if (p < 0) return;
  bool trigger = false;
  if (p >= r->ctl_first && p <= r->ctl_last) {
    r->set_control(p, v);
    r->bump();
    return;
  }
  if (p >= P_M1 && p < P_M1 + NMACRO) {
    int m = p - P_M1;
    if (r->learn) { r->armed = m; r->describe_macro(); }
    r->mac[m].v = clampf(v, 0, 1);
    r->apply_macro(m);
    r->bump();
    return;
  }
  if (p >= P_QL1 && p <= P_QL1 + 15) {
    int t = r->ql_target(p - P_QL1);
    if (t < 0) return;
    float x = clampf(v, 0, 1);
    float val2 = P_MIN[t] + x * (P_MAX[t] - P_MIN[t]);
    if (P_NOPTS[t]) val2 = roundf(x * (P_NOPTS[t] - 1));
    char b[32]; snprintf(b, sizeof b, "%g", val2);
    set_param(inst, P_KEY[t], b);
    return;
  }
  switch (p) {
    case P_LEVEL: case P_CEIL: case P_REL: case P_OUT_SRC: case P_R_AMOUNT: case P_R_MIN: case P_R_CABLES: case P_R_MODE: case P_R_SCOPE:
      r->pv[p] = clampf(P_NOPTS[p] ? roundf(v) : v, P_MIN[p], P_MAX[p]);
      if (p == P_CEIL || p == P_LEVEL || p == P_REL) snprintf(r->out_info, sizeof r->out_info, "Limiter always on. Ceiling %.1f dB.", r->pv[P_CEIL]);
      r->bump();
      return;
    case P_PX: case P_PY:
      r->pv[p] = clampf(v, 0, 1); r->apply_play(); r->bump(); return;
    case P_LEARN:
      r->learn = v > 0.5f; if (!r->learn) r->armed = -1;
      r->pv[p] = r->learn ? 1.0f : 0.0f; r->describe_macro(); r->bump(); return;
    case P_VIEW: r->set_view((int)lroundf(v)); return;
    case P_PRS: r->load_preset((int)lroundf(v)); return;
    case P_IN_SEC: case P_HM: case P_TTL: case P_XY_POS: case P_VT: case P_PT: case P_PK_C: return;     // follow the page
    default: break;
  }
  trigger = true;
  if (trigger && v < 0.5f) return;                                 // triggers fire on 1 only
  if (p >= P_XY_0_0 && p < P_XY_0_0 + XY_COLS * XY_ROWS) {
    int n = p - P_XY_0_0, row = n / XY_COLS, col = n % XY_COLS;
    r->pv[P_PX] = (col + 0.5f) / XY_COLS;
    r->pv[P_PY] = 1.0f - (row + 0.5f) / XY_ROWS;
    r->apply_play(); r->bump();
    return;
  }
  for (int t = 0; t < NTYPE; t++)
    if (p >= T_TAPBASE[t] && p < T_TAPBASE[t] + T_NI[t] + T_NO[t]) { r->tap_jack(t, p - T_TAPBASE[t]); return; }
  for (int s = 0; s < NSLOT; s++) if (p == P_GO_0 + s) { r->go_slot(s); return; }
  switch (p) {
    case P_NAV_OV: r->set_view(V_OVERVIEW); break;
    case P_NAV_PREV: r->nav_step(-1); break;
    case P_NAV_NEXT: r->nav_step(1); break;
    case P_NAV_PERF: r->set_view(V_PERF); break;
    case P_NAV_PLAY: r->set_view(V_PLAY); break;
    case P_NAV_OUT: r->set_view(V_OUTPUT); break;
    case P_NAV_RAND: r->set_view(V_RANDOM); break;
    case P_NAV_CTRL: if (r->on_patch()) r->set_view(V_CTRL0 + r->sel); break;
    case P_NAV_PATCH: if (r->on_ctrl()) r->set_view(V_PATCH0 + r->sel); break;
    case P_M_CLEAR: r->clear_macro(); break;
    case P_R_GO: r->randomize(); break;
    case P_R_MODE_STEP: r->pv[P_R_MODE] = (float)(((int)r->pv[P_R_MODE] + 1) % 3); r->bump(); break;
    case P_SC_0: case P_SC_1: case P_SC_2: case P_SC_3: r->pv[P_R_SCOPE] = (float)(p - P_SC_0); r->bump(); break;
    case P_R_UNDO: r->undo(); break;
    case P_PK_CANCEL: r->pk_cancel(); break;
    case P_PK_UNPLUG: r->pk_unplug(); break;
    case P_PK_DONE: r->pk_done(); break;
    default: break;
  }
}

int get_param(void *inst, const char *key, char *buf, int n) {
  Rig *r = (Rig *)inst;
  if (!strcmp(key, "display_rev")) return snprintf(buf, n, "%u", r->rev);
  if (!strcmp(key, "state")) return r->save(buf, n);
  if (!strcmp(key, "dbg_peaks")) {
    int len = 0; buf[0] = 0;
    for (int s = 0; s < NSLOT && len < n - 40; s++) {
      len += snprintf(buf + len, n - len, "%s:", SLOT_TITLE[s]);
      for (int q = 0; q < 4 && q < T_NO[SLOT_TYPE[s]]; q++) { len += snprintf(buf + len, n - len, " %.2f", r->dbg_peak[s][q]); r->dbg_peak[s][q] = 0; }
      len += snprintf(buf + len, n - len, "\n");
    }
    return len;
  }
  size_t kl = strlen(key);
  char base[64];
  int suffix = 0;   // 1 = _display, 2 = _name
  if (kl > 8 && !strcmp(key + kl - 8, "_display")) { suffix = 1; kl -= 8; }
  else if (kl > 5 && !strcmp(key + kl - 5, "_name")) { suffix = 2; kl -= 5; }
  if (kl >= sizeof base) return 0;
  memcpy(base, key, kl);
  base[kl] = 0;
  int p = find_key(base);
  if (p < 0) return 0;
  if (p >= P_QL1 && p <= P_QL1 + 15) {
    int t = r->ql_target(p - P_QL1);
    if (suffix == 2) {
      if (t < 0) return snprintf(buf, n, "-");
      if (t >= P_M1 && t < P_M1 + NMACRO) { r->macro_label(t - P_M1, buf, n); return (int)strlen(buf); }
      return snprintf(buf, n, "%s", P_NAME[t]);
    }
    if (suffix == 1) { if (t < 0) return snprintf(buf, n, " "); r->display(t, buf, n); return (int)strlen(buf); }
    if (t < 0) return snprintf(buf, n, "0");
    if (P_NOPTS[t]) return snprintf(buf, n, "%g", P_NOPTS[t] > 1 ? r->host_get(t) / (P_NOPTS[t] - 1) : 0.0f);
    return snprintf(buf, n, "%g", r->host_norm(t));
  }
  if (suffix == 2) {
    if (p >= P_M1 && p < P_M1 + NMACRO) { r->macro_label(p - P_M1, buf, n); return (int)strlen(buf); }
    return 0;
  }
  if (suffix == 1) { r->display(p, buf, n); return (int)strlen(buf); }
  if (p >= r->ctl_first && p <= r->ctl_last) {
    if (P_NOPTS[p]) return snprintf(buf, n, "%d", (int)r->host_get(p));
    return snprintf(buf, n, "%g", r->host_get(p));
  }
  if (p == P_VIEW) return snprintf(buf, n, "%d", r->view);
  if (p == P_IN_SEC) return snprintf(buf, n, "%d", r->view > 0 ? 1 : 0);
  if (p == P_HM) return snprintf(buf, n, "%d", r->view == V_CONN ? 2 : (r->on_ctrl() || r->on_patch()) ? 1 : 0);
  if (p == P_XY_POS) {
    int c = (int)clampf(r->pv[P_PX] * XY_COLS, 0, XY_COLS - 1), rw = (int)clampf((1.0f - r->pv[P_PY]) * XY_ROWS, 0, XY_ROWS - 1);
    return snprintf(buf, n, "%d", r->view == V_PLAY ? rw * XY_COLS + c : 0);
  }
  if (p == P_XY_TEXT) return snprintf(buf, n, "X %+.1f V   Y %+.1f V", r->pv[P_PX] * 10.0f - 5.0f, r->pv[P_PY] * 10.0f - 5.0f);
  if (p == P_TTL) return snprintf(buf, n, "%s", (r->on_ctrl() || r->on_patch()) ? SLOT_TITLE[r->sel] : " ");
  if (p == P_VT) return snprintf(buf, n, "%d", r->on_ctrl() ? SLOT_TYPE[r->sel] + 1 : 0);
  if (p == P_PT) return snprintf(buf, n, "%d", r->on_patch() ? SLOT_TYPE[r->sel] + 1 : 0);
  if (p == P_PK_C) return snprintf(buf, n, "%d", (r->on_patch() || r->view == V_CONN) && r->held_slot >= 0 ? 1 : 0);
  if (p == P_PATCH_INFO) return snprintf(buf, n, "%s", r->info);
  if (p == P_PERF_INFO) return snprintf(buf, n, "%s", r->perf_info);
  if (p == P_R_INFO) return snprintf(buf, n, "%s", r->rand_info);
  if (p == P_OUT_INFO) return snprintf(buf, n, "%s", r->out_info);
  if (p == P_CONN_A) return snprintf(buf, n, "%s", r->conn_a);
  if (p == P_CONN_B) return snprintf(buf, n, "%s", r->conn_b);
  if (p == P_CT_O) return snprintf(buf, n, "%d", r->view == V_CONN ? r->ct_o : 0);
  if (p == P_CT_I) return snprintf(buf, n, "%d", r->view == V_CONN ? r->ct_i : 0);
  if (p == P_M_GR) return snprintf(buf, n, "%d", r->view == V_OUTPUT ? r->gr_pos : 0);
  if (p == P_M_PK) return snprintf(buf, n, "%d", r->view == V_OUTPUT ? r->pk_pos : 0);
  if (p == P_LEARN) return snprintf(buf, n, "%d", r->learn ? 1 : 0);
  if (p == P_PRS) return snprintf(buf, n, "%d", (int)r->pv[P_PRS]);
  for (int t = 0; t < NTYPE; t++) {
    int nj = T_NI[t] + T_NO[t];
    if (p >= T_JSBASE[t] && p < T_JSBASE[t] + nj) return snprintf(buf, n, "%d", r->jack_state(t, p - T_JSBASE[t]));
  }
  if (P_NOPTS[p]) return snprintf(buf, n, "%d", (int)r->pv[p]);
  if (p >= P_M1 && p < P_M1 + NMACRO) return snprintf(buf, n, "%g", r->mac[p - P_M1].v);
  return snprintf(buf, n, "%g", r->pv[p]);   // triggers read back as 0
}

void render(void *inst, int16_t *out, int frames) { ((Rig *)inst)->render(out, frames); }

const mpc_engine_t API = {create, destroy, midi, set_param, get_param, render, nullptr, nullptr};

}  // namespace

extern "C" const mpc_engine_t *mpc_engine(void) { return &API; }
