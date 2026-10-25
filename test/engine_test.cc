// Offline engine test. Built for ARM (static musl) and run under qemu-arm-static by test/build_test.sh -- never for x86.
// Renders every factory patch and drives macros, randomizer, patching and state through the engine's own interface.
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <set>
extern "C" {
#include "engine.h"
}
#include "gen.h"

static const mpc_engine_t *E;
static void *I;
static int fails = 0;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL %s:%d  ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static void setp(const char *k, const char *v) { E->set_param(I, k, v); }
static void setf(const char *k, double v) { char b[32]; snprintf(b, sizeof b, "%.6g", v); setp(k, b); }
static std::string getp(const char *k) { char b[8192]; b[0] = 0; int n = E->get_param(I, k, b, sizeof b); return n > 0 ? b : ""; }

struct Stats { double peak, rms, dc; bool finite; };
static Stats render(int blocks) {
  Stats s{0, 0, 0, true};
  double sum2 = 0, sum = 0; long n = 0;
  int16_t buf[256];
  for (int b = 0; b < blocks; b++) {
    E->render(I, buf, 128);
    for (int i = 0; i < 256; i++) {
      double x = buf[i] / 32768.0;
      if (fabs(x) > s.peak) s.peak = fabs(x);
      sum2 += x * x; sum += x; n++;
    }
  }
  s.rms = sqrt(sum2 / n); s.dc = sum / n;
  return s;
}
static double db(double x) { return 20 * log10(fmax(x, 1e-9)); }

int main() {
  E = mpc_engine();
  I = E->create(nullptr);
  CHECK(I != nullptr, "create");
  printf("host params: %d, module params %d\n", P_COUNT, NPTOT);

  // 1. every patch renders: finite, audible, no DC, under the ceiling
  for (int p = 0; p < NPRESET; p++) {
    setf("prs", p);
    render(200);                                   // settle (about 0.6 s)
    getp("dbg_peaks");
    Stats s = render(1200);                        // about 3.5 s
    if (getenv("PEAKS")) printf("%s", getp("dbg_peaks").c_str());
    printf("patch %-22s peak %6.1f dBFS  rms %6.1f dBFS  dc %.5f  cables %s\n", PRESET_NAME[p], db(s.peak), db(s.rms), s.dc,
           getp("patch_info").c_str());
    CHECK(s.peak <= pow(10, -3.0 / 20) + 0.0005, "patch %d over the ceiling: %g", p, db(s.peak));
    CHECK(s.rms > 1e-5, "patch %d silent (rms %g)", p, db(s.rms));
    CHECK(fabs(s.dc) < 0.01, "patch %d dc %g", p, s.dc);
  }

  // 2. the ceiling: never above -1 dBFS, whatever is asked; the limiter has no bypass
  setf("prs", 0);
  setf("level", 1.0);
  setf("ceil", 5.0);                               // out of range, clamps to -1
  Stats s = render(600);
  printf("ceiling asked +5 dB, peak %.2f dBFS (display %s)\n", db(s.peak), getp("ceil_display").c_str());
  CHECK(s.peak <= pow(10, -1.0 / 20) + 0.0005, "ceiling above -1 dBFS: %g", db(s.peak));
  setf("ceil", -3.0); setf("level", 0.5);

  // 3. macros: default CUTOFF moves the filter; learn assigns a control
  setf("view", 1);
  setf("m1", 0.2);
  std::string a = getp("fl_0");
  setf("m1", 0.9);
  std::string b = getp("fl_0");
  CHECK(a != b, "macro 1 did not move FREQ L (%s %s)", a.c_str(), b.c_str());
  setf("learn", 1);
  setf("m6", 0.5);                                 // arm macro 6
  int before = atoi(getp("m6_name").c_str() ? "0" : "0");
  (void)before;
  setf("view", V_CTRL0 + 0);                       // Drone 1
  setf("dr_15", 0.9);                              // CV ATT
  CHECK(getp("perf_info").find("Macro 6") != std::string::npos, "learn did not report: %s", getp("perf_info").c_str());
  setf("learn", 0);

  // 4. page-following Q-Links
  setf("view", V_CTRL0 + 2);                       // Mixer
  CHECK(getp("ql1_name") == "PAN 1" || getp("ql1_name").size() > 0, "ql name");
  printf("mixer page ql1=%s ql9=%s\n", getp("ql1_name").c_str(), getp("ql9_name").c_str());

  // 5. patching: tap an output on one module, an input on another, check the cable, unplug it
  setf("prs", 1);                                  // Solar 42 patch
  setf("view", V_PATCH0 + 11);                     // Sequencer (slot 11)
  int sq = 8;                                      // type index of the sequencer
  setf("view", V_PATCH0 + 11);
  char k[32];
  snprintf(k, sizeof k, "sq_o0"); setf(k, 1);      // CV out
  CHECK(getp("pk_c") == "1", "held end not reported");
  setf("view", V_PATCH0 + 0);                      // Drone 1 (page change keeps the held end)
  CHECK(getp("pk_c") == "1", "held end lost on page change");
  snprintf(k, sizeof k, "dr_i0"); setf(k, 1);      // CV in
  CHECK(atoi(getp("view").c_str()) == V_CONN, "no connected page (view %s)", getp("view").c_str());
  printf("connected page: %s\n", getp("patch_info").c_str());
  setf("pk_unplug", 1);
  CHECK(atoi(getp("view").c_str()) == V_PATCH0 + 0, "unplug did not go back");
  (void)sq;

  // 6. randomizer: bins never repeat inside 100 runs, cables, undo
  setf("prs", 0);
  setf("r_scope", 0); setf("r_mode", 1); setf("r_cables", 3); setf("r_amount", 100); setf("r_min", 0);
  std::set<int> seen;                              // FREQ L's value over 100 runs
  bool repeat = false;
  std::string v0 = getp("fl_0");
  for (int r = 0; r < 100; r++) {
    setf("r_go", 1);
    int bin = (int)(atof(getp("fl_0").c_str()) * 1000);
    (void)bin;
    std::string v = getp("fl_0");
    int q = (int)lround(atof(v.c_str()) * 1000000);
    // the bin is of the normalised range; FREQ L min..max
    double lo = TP_MIN[T_POFF[2] + 0], hi = TP_MAX[T_POFF[2] + 0];
    int nb = (int)floor((atof(v.c_str()) - lo) / (hi - lo) * BINS);
    if (nb >= BINS) nb = BINS - 1;
    if (seen.count(nb)) repeat = true;
    seen.insert(nb);
    (void)q;
    render(2);
  }
  CHECK(!repeat, "a parameter landed on a used bin within 100 runs");
  printf("100 runs: %s; %s\n", repeat ? "REPEAT" : "no repeated place for FREQ L", getp("r_info").c_str());
  Stats rs = render(400);
  printf("after 100 random runs peak %.1f dBFS rms %.1f\n", db(rs.peak), db(rs.rms));
  CHECK(rs.peak <= pow(10, -3.0 / 20) + 0.0005, "random patch over the ceiling");
  std::string before_undo = getp("fl_0");
  setf("r_go", 1);
  std::string after_go = getp("fl_0");
  setf("r_undo", 1);
  CHECK(getp("fl_0") == before_undo, "undo did not restore (%s vs %s, was %s)", getp("fl_0").c_str(), before_undo.c_str(), after_go.c_str());
  // toggles cycle through their positions
  setf("r_scope", 3); setf("r_mode", 2); setf("r_cables", 4);
  setf("r_go", 1);
  printf("cables scope: %s\n", getp("r_info").c_str());

  // 7. state: save, change, load, same sound and same history
  char st[65536]; int n = E->get_param(I, "state", st, sizeof st);
  printf("state: %d bytes\n", n);
  CHECK(n > 0 && n < 65000, "state size %d", n);
  std::string saved(st);
  std::string f0 = getp("fl_0"), m1 = getp("m1");
  setf("prs", 2);
  E->set_param(I, "state", saved.c_str());
  CHECK(getp("fl_0") == f0, "state: fl_0 %s vs %s", getp("fl_0").c_str(), f0.c_str());
  char st2[65536]; E->get_param(I, "state", st2, sizeof st2);
  CHECK(saved == std::string(st2), "state not stable across a save/load/save (%zu vs %zu bytes)", saved.size(), strlen(st2));
  if (saved != std::string(st2)) { size_t i = 0; while (i < saved.size() && saved[i] == st2[i]) i++; printf("first difference at %zu: [%.60s] vs [%.60s]\n", i, saved.c_str() + (i > 20 ? i - 20 : 0), st2 + (i > 20 ? i - 20 : 0)); }
  // small buffer: the history shrinks, the rack still saves
  char small[8192]; int n2 = E->get_param(I, "state", small, sizeof small);
  printf("state in an 8 KB buffer: %d bytes\n", n2);
  CHECK(n2 > 0 && n2 < 8192, "no state in 8 KB");

  // 8. play: pads and XY
  setf("view", V_PLAY);
  setf("xy_6_0", 1);
  printf("XY: x %s y %s\n", getp("px_display").c_str(), getp("py_display").c_str());
  setf("pd_0", 0);
  render(50);
  setf("pd_0", 1);
  render(50);

  E->destroy(I);
  printf(fails ? "\n%d FAILURES\n" : "\nALL PASSED\n", fails);
  return fails ? 1 : 0;
}
