// Prints every module type's parameters and jacks as JSON (build-time helper for tools/spec_modules.py).
// Built for ARM (static musl) and run with qemu-arm: the build never compiles anything for x86.
#include "rack.hpp"
#include <cstdio>
extern Model *modelLunar50Drone, *modelLunarDetector, *modelLunarFilter, *modelLunarJoystick, *modelLunarLFO, *modelLunarMixer,
    *modelLunarPads, *modelLunarPapaSrapa, *modelLunarSequencer, *modelLunarVCO;
static void esc(const std::string &s) { for (char c : s) { if (c == '"' || c == '\\') putchar('\\'); putchar(c); } }
int main() {
    Model *ms[] = {modelLunar50Drone, modelLunarDetector, modelLunarFilter, modelLunarJoystick, modelLunarLFO, modelLunarMixer,
                   modelLunarPads, modelLunarPapaSrapa, modelLunarSequencer, modelLunarVCO};
    printf("{\n");
    for (int k = 0; k < 10; k++) {
        Module *m = ms[k]->createModule();
        printf("\"%s\": {\"params\": [", ms[k]->slug);
        for (size_t i = 0; i < m->params.size(); i++) {
            ParamQuantity *q = m->paramQuantities[i].get();
            printf("%s{\"id\":%zu,\"name\":\"", i ? "," : "", i);
            if (q) esc(q->name);
            printf("\",\"min\":%g,\"max\":%g,\"def\":%g,\"unit\":\"", q ? q->minValue : 0, q ? q->maxValue : 1, q ? q->defaultValue : 0);
            if (q) esc(q->unit);
            printf("\",\"base\":%g,\"mult\":%g,\"off\":%g,\"snap\":%d,\"labels\":[", q ? q->displayBase : 0, q ? q->displayMultiplier : 1, q ? q->displayOffset : 0, q ? q->snapEnabled : 0);
            if (q) for (size_t l = 0; l < q->labels.size(); l++) { printf("%s\"", l ? "," : ""); esc(q->labels[l]); printf("\""); }
            printf("]}");
        }
        printf("], \"inputs\": [");
        for (size_t i = 0; i < m->inputs.size(); i++) { printf("%s\"", i ? "," : ""); esc(m->inNames.count(i) ? m->inNames[i] : ""); printf("\""); }
        printf("], \"outputs\": [");
        for (size_t i = 0; i < m->outputs.size(); i++) { printf("%s\"", i ? "," : ""); esc(m->outNames.count(i) ? m->outNames[i] : ""); printf("\""); }
        printf("], \"lights\": %zu}%s\n", m->lights.size(), k < 9 ? "," : "");
        delete m;
    }
    printf("}\n");
}
