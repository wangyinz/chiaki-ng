// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
#include "allyrumble.h"
#include <cassert>
#include <iostream>
#include <random>
using namespace ChiakiAllyRumble;
static TriggerEffect effect(unsigned strength, uint16_t zones = 1023, uint8_t frequency = 35)
{
    TriggerEffect e; e.type = 0x26; e.data[0] = zones; e.data[1] = zones >> 8;
    uint32_t packed = 0;
    for(unsigned z = 0; z < 10; ++z) packed |= (strength - 1u) << (3*z);
    for(unsigned b = 0; b < 4; ++b) e.data[2+b] = packed >> (8*b);
    e.data[8] = frequency;
    return e;
}
static bool same(Motors a, Motors b) { return a.low == b.low && a.high == b.high; }
int main()
{
    const auto e = effect(8);
    Mixer m; m.setTriggers(e, e);
    assert(same(m.sample(255,0,1,true,true).output, {32768,32768}));
    assert(same(m.sample(0,255,1,true,true).output, {32768,32768}));
    assert(same(m.sample(255,255,1,true,true).output, {32768,32768}));
    assert(same(m.sample(0,0,1,true,true).output, {}));
    assert(same(m.sample(255,255,1,true,false).output, {}));
    for(auto type : {0x05,0x21,0x25,0x22,0x00})
    { auto nonVibration = e; nonVibration.type = type; assert(triggerLevel(nonVibration,255,1) == 0); }
    assert(triggerLevel(effect(8,1023,0),255,1) == 0);
    assert(triggerLevel(effect(8,0),255,1) == 0);
    assert(triggerLevel(effect(8,1u<<9),230,1) == 0);
    assert(triggerLevel(effect(8,1u<<9),231,1) == 32768);
    assert(triggerLevel(effect(8,1u<<9),255,1) == 32768);
    assert(triggerLevel(e,0,1) == 0);
    m.setTriggerGain(0.5); assert(m.sample(255,0,1,true,true).l2 == 16384);
    m.setTriggerGain(0); assert(same(m.sample(255,255,1,true,true).output, {}));
    m.setTriggerGain(1);

    // Captured Astro trigger-demo regression: both sides receive the same 0x26
    // trigger envelope, while the raw body-haptics stream can be much stronger
    // during L2 than R2. They are separate DualSense actuator paths, but on an
    // Ally both fall back to the same rumble motors. Body may therefore not
    // raise an active trigger fallback a second time.
    {
        Mixer isolated;
        const auto sustain = effect(2); // 2 * 4096 = 8192
        isolated.setTriggers(sustain, sustain);

        isolated.setBody({16000, 15500}, 100);
        const auto left = isolated.sample(255, 0, 100, true, true);
        assert(same(left.body, {16000,16000}));
        assert(same(left.bodyUsed, {8192,8192}));
        assert(same(left.trigger, {8192,8192}));
        assert(same(left.output, {8192,8192}));

        isolated.setBody({1600, 0}, 101);
        const auto right = isolated.sample(0, 255, 101, true, true);
        assert(same(right.body, {1600,1600}));
        assert(same(right.bodyUsed, {1600,1600}));
        assert(same(right.trigger, {8192,8192}));
        assert(same(right.output, {8192,8192}));

        // No active vibration trigger: body haptics retain the old behavior.
        const auto body_only = isolated.sample(0, 0, 101, true, true);
        assert(same(body_only.bodyUsed, {1600,1600}));
        assert(same(body_only.output, {1600,1600}));

        // Resistance/feedback modes are not converted to trigger rumble and
        // therefore must not gate body haptics.
        auto resistance = sustain;
        resistance.type = 0x25;
        isolated.setTriggers(resistance, resistance);
        isolated.setBody({16000, 15500}, 102);
        const auto resistance_body = isolated.sample(255, 0, 102, true, true);
        assert(same(resistance_body.trigger, {}));
        assert(same(resistance_body.bodyUsed, {16000,16000}));
        assert(same(resistance_body.output, {16000,16000}));

        // Classic rumble is independent and may still dominate the shared
        // motors even while trigger/body isolation is active.
        isolated.setTriggers(sustain, sustain);
        isolated.setClassic(200, 200, 103);
        const auto classic = isolated.sample(255, 0, 103, true, true);
        assert(same(classic.classic, {51200,51200}));
        assert(same(classic.output, {51200,51200}));
    }

    m.setBody({6000,1000},10);
    assert(same(m.sample(0,0,10,true,true).output, {6000,6000}));
    m.setBody({1000,6000},10);
    assert(same(m.sample(0,0,10,true,true).output, {6000,6000}));
    m.setClassic(20,100,10);
    assert(same(m.sample(0,0,10,true,true).output, {6000,25600}));
    // Body silence/disabled never erases classic rumble or a pressed trigger.
    m.setBody({},11);
    assert(same(m.sample(0,0,11,true,true).output, {5120,25600}));
    assert(same(m.sample(0,255,11,false,true).output, {32768,32768}));
    // Classic stop doesn't erase body haptics or trigger vibration either.
    m.setClassic(0,0,12); m.setBody({4000,0},12);
    assert(same(m.sample(0,0,12,true,true).output, {4000,4000}));
    assert(same(m.sample(255,0,12,true,true).output, {32768,32768}));
    assert(same(m.sample(0,0,112,true,true).output, {}));
    m.setBodyGain(0);
    assert(same(m.sample(255,0,12,true,true).output, {32768,32768}));
    m.setTriggerGain(0); assert(same(m.sample(255,255,12,true,true).output, {}));
    m.reset(); assert(same(m.sample(255,255,12,true,true).output, {}));
    m.setClassic(255,1,0); assert(same(m.sample(0,0,5000,true,true).output, {}));
    assert(scale(65536,1) == 65535);
    assert(scale(32768,4) == 65535);
    // Regression negative control: old L2->low, R2->high was not mirror invariant.
    assert(!same({32768,0}, {0,32768}));
    std::mt19937 random(20261002);
    for(unsigned i=0; i<10000; ++i)
    {
        Mixer a,b;
        auto l=effect(1+random()%8,random()%1024,uint8_t(random()%256));
        auto r=effect(1+random()%8,random()%1024,uint8_t(random()%256));
        uint8_t lp=random()%256, rp=random()%256;
        uint16_t bl=random()%65536,br=random()%65536;
        a.setTriggers(l,r);b.setTriggers(r,l);
        a.setBody({bl,br},100);b.setBody({br,bl},100);
        a.setClassic(10,80,100);b.setClassic(10,80,100);
        assert(same(a.sample(lp,rp,100,true,true).output,b.sample(rp,lp,100,true,true).output));
    }
    std::cout << "Ally rumble regressions passed: source separation, L2/R2 mirror symmetry, 10,000 cases.\n";
}
