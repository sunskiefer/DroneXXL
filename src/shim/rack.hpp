// Host-free stand-in for the part of the VCV Rack SDK that the Lunar modules' DSP uses.
// Panels, widgets and menus are not here: tools/prep_modules.py cuts them from the vendored sources.
// Numeric helpers (math, simd, dsp) are the MetaModule plugin SDK's rack-interface headers, which are Rack's own (GPL-3).
#pragma once
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <string>
#include <vector>
#include <map>
#include <memory>
#include <algorithm>
#include <functional>
#include <initializer_list>
#include <math.hpp>
#include <simd/Vector.hpp>
#include <simd/functions.hpp>
#include <dsp/common.hpp>
#include <dsp/approx.hpp>
#include <dsp/digital.hpp>
#include <dsp/filter.hpp>

#ifndef ENUMS
#define ENUMS(name, count) name, name##_LAST = name + (count) - 1
#endif

namespace rack {
namespace string {
inline std::string f(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
inline std::string f(const char *fmt, ...) {
    char b[160]; va_list a; va_start(a, fmt); vsnprintf(b, sizeof b, fmt, a); va_end(a); return b;
}
}

static const int PORT_MAX_CHANNELS = 16;
static const int RACK_GRID_WIDTH = 15;

// A tiny json: the modules save one or two integers
struct json_t { std::map<std::string, long long> kv; };
typedef long long json_int_t;
inline json_t *json_object() { return new json_t; }
inline json_t *json_integer(long long v) { json_t *j = new json_t; j->kv["v"] = v; return j; }
inline void json_object_set_new(json_t *o, const char *k, json_t *v) { o->kv[k] = v->kv["v"]; delete v; }
inline json_t *json_object_get(json_t *o, const char *k) {
    auto it = o->kv.find(k); if (it == o->kv.end()) return nullptr;
    static thread_local json_t tmp; tmp.kv["v"] = it->second; return &tmp;
}
inline long long json_integer_value(json_t *j) { return j ? j->kv["v"] : 0; }
inline void json_decref(json_t *j) { if (j && j->kv.count("v") == 0) delete j; }

struct SampleRateChangeEvent { float sampleRate; float sampleTime; };
struct ResetEvent {};

struct Model;
namespace engine {
struct Module;
struct ProcessArgs { float sampleRate; float sampleTime; int64_t frame = 0; };

struct Param {
    float value = 0.f;
    float getValue() const { return value; }
    void setValue(float v) { value = v; }
};
struct Light {
    float value = 0.f;
    void setBrightness(float b) { value = b; }
    float getBrightness() const { return value; }
};
struct Port {
    float voltages[PORT_MAX_CHANNELS] = {};
    uint8_t channels = 0;       // 0 = nothing patched (inputs) or never written (outputs)
    bool connected = false;     // inputs: a cable ends here; outputs: a cable starts here
    bool isConnected() const { return connected; }
    bool isMonophonic() const { return channels <= 1; }
    bool isPolyphonic() const { return channels > 1; }
    int getChannels() const { return channels; }
    void setChannels(int c) { channels = (uint8_t)c; for (int i = c; i < PORT_MAX_CHANNELS; i++) voltages[i] = 0.f; }
    void setVoltage(float v, int c = 0) { voltages[c] = v; if (channels < 1) channels = 1; }
    float getVoltage(int c = 0) const { return voltages[c]; }
    float getPolyVoltage(int c) const { return isMonophonic() ? voltages[0] : voltages[c]; }
    float getNormalVoltage(float n, int c = 0) const { return connected ? getVoltage(c) : n; }
    float getNormalPolyVoltage(float n, int c) const { return connected ? getPolyVoltage(c) : n; }
    float getVoltageSum() const { float s = 0.f; int n = channels < 1 ? 1 : channels; for (int i = 0; i < n; i++) s += voltages[i]; return s; }
    template <typename T = float> T getVoltageSimd(int c) const { return T::load(&voltages[c]); }
    template <typename T = float> T getPolyVoltageSimd(int c) const { return isMonophonic() ? T(voltages[0]) : T::load(&voltages[c]); }
    template <typename T = float> void setVoltageSimd(T v, int c) { v.store(&voltages[c]); }
};

struct ParamQuantity {
    Module *module = nullptr; int paramId = 0;
    float minValue = 0.f, maxValue = 1.f, defaultValue = 0.f;
    std::string name, unit; float displayBase = 0.f, displayMultiplier = 1.f, displayOffset = 0.f;
    std::vector<std::string> labels; bool snapEnabled = false;
    virtual ~ParamQuantity() {}
    float getValue();
    void setValue(float v);
    float getMinValue() { return minValue; }
    float getMaxValue() { return maxValue; }
    float getDefaultValue() { return defaultValue; }
    float getRange() { return maxValue - minValue; }
    virtual float getDisplayValue() {
        float v = getValue();
        if (displayBase == 0.f) v *= displayMultiplier;
        else if (displayBase < 0.f) v = std::log(v) / std::log(-displayBase) * displayMultiplier;
        else v = std::pow(displayBase, v) * displayMultiplier;
        return v + displayOffset;
    }
    virtual void setDisplayValue(float d) {
        float v = d - displayOffset;
        if (displayBase == 0.f) { if (displayMultiplier != 0.f) v /= displayMultiplier; }
        else if (displayBase < 0.f) v = std::pow(-displayBase, v / displayMultiplier);
        else v = std::log(v / displayMultiplier) / std::log(displayBase);
        setValue(v);
    }
    virtual std::string getDisplayValueString() { char b[32]; snprintf(b, sizeof b, "%g", getDisplayValue()); return b; }
    ParamQuantity *getParamQuantity() { return this; }
};
struct SwitchQuantity : ParamQuantity {};

struct Expander {
    Module *module = nullptr;
    void *producerMessage = nullptr;
    void *consumerMessage = nullptr;
    bool messageFlipRequested = false;
    void requestMessageFlip() { messageFlipRequested = true; }
};

struct Module {
    typedef engine::ProcessArgs ProcessArgs;
    std::vector<Param> params; std::vector<Port> inputs, outputs; std::vector<Light> lights;
    std::vector<std::unique_ptr<ParamQuantity>> paramQuantities;
    std::vector<float> paramDefaults;
    Expander leftExpander, rightExpander;
    Model *model = nullptr;
    virtual ~Module() {}
    void config(int np, int ni, int no, int nl = 0) {
        params.assign(np, Param()); inputs.assign(ni, Port()); outputs.assign(no, Port()); lights.assign(nl, Light());
        paramQuantities.clear(); paramQuantities.resize(np); paramDefaults.assign(np, 0.f);
    }
    template <class Q = ParamQuantity>
    Q *configParam(int id, float mn, float mx, float def, std::string name = "", std::string unit = "",
                   float base = 0.f, float mult = 1.f, float off = 0.f) {
        Q *q = new Q; q->module = this; q->paramId = id; q->minValue = mn; q->maxValue = mx; q->defaultValue = def;
        q->name = name; q->unit = unit; q->displayBase = base; q->displayMultiplier = mult; q->displayOffset = off;
        paramQuantities[id].reset(q); params[id].value = def; paramDefaults[id] = def; return q;
    }
    template <class Q = SwitchQuantity>
    Q *configSwitch(int id, float mn, float mx, float def, std::string name = "", std::vector<std::string> labels = {}) {
        Q *q = configParam<Q>(id, mn, mx, def, name); q->labels = labels; q->snapEnabled = true; return q;
    }
    template <class Q = ParamQuantity>
    Q *configButton(int id, std::string name = "") { return configParam<Q>(id, 0.f, 1.f, 0.f, name); }
    std::map<int, std::string> inNames, outNames;
    void configInput(int i, std::string n = "") { inNames[i] = n; }
    void configOutput(int i, std::string n = "") { outNames[i] = n; }
    struct LightInfo { std::string description; };
    LightInfo *configLight(int, std::string = "") { static thread_local LightInfo li; return &li; }
    void configBypass(int, int) {}
    ParamQuantity *getParamQuantity(int id) { return paramQuantities[id].get(); }
    virtual void process(const ProcessArgs &) {}
    virtual json_t *dataToJson() { return nullptr; }
    virtual void dataFromJson(json_t *) {}
    virtual void onSampleRateChange(const SampleRateChangeEvent &) {}
    virtual void onReset(const ResetEvent &) {}
};
inline float ParamQuantity::getValue() { return module->params[paramId].value; }
inline void ParamQuantity::setValue(float v) { module->params[paramId].value = math::clamp(v, minValue, maxValue); }
} // namespace engine

using Input = engine::Port; using Output = engine::Port;
using engine::Module; using engine::Param; using engine::Port; using engine::Light;
using engine::ParamQuantity; using engine::SwitchQuantity; using engine::ProcessArgs; using engine::Expander;
struct Plugin { };
struct Model {
    const char *slug; std::function<Module *()> make;
    Module *createModule() { return make(); }
};
template <class TModule> Model *createModel(const char *slug) {
    Model *m = new Model; m->slug = slug; m->make = [m] { Module *x = (Module *)new TModule; x->model = m; return x; }; return m;
}
using namespace math;
} // namespace rack
using namespace rack;
