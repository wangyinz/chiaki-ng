// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
#ifndef CHIAKI_ALLYRUMBLE_H
#define CHIAKI_ALLYRUMBLE_H
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>

// These are SDL/XInput LOW/HIGH-frequency outputs, not Sony L2/R2 actuators.
// No claim of spatial or waveform fidelity is made by this two-motor fallback.
namespace ChiakiAllyRumble
{
struct Motors { uint16_t low = 0, high = 0; };
struct Stereo { uint16_t left = 0, right = 0; };
struct TriggerEffect { uint8_t type = 0x05; std::array<uint8_t, 10> data{}; };
struct Sources
{
    // body is the raw body-haptics fallback after stereo->motor downmix.
    // bodyUsed is the contribution that is allowed into the final motor mix.
    Motors classic, body, bodyUsed, trigger, output;
    uint16_t l2 = 0, r2 = 0;
};
inline uint16_t scale(uint32_t value, double gain)
{
    if(!std::isfinite(gain) || gain <= 0) return 0;
    return static_cast<uint16_t>(std::min(65535.0, value * gain));
}
inline Motors downmix(Stereo source, double gain)
{
    // Peak-envelope approximation. Stereo PCM channels are not frequency bands;
    // retain the strongest channel without giving L/R different motor timbres.
    const uint16_t level = scale(std::max(source.left, source.right), gain);
    return {level, level};
}
inline uint16_t triggerLevel(const TriggerEffect &effect, uint8_t position, double gain)
{
    // Public community format: type + ten data bytes. Frequency is byte 9 of
    // the full effect, i.e. data[8]. Resistance/weapon modes are NOT vibration.
    if(effect.type != 0x26 || position == 0 || effect.data[8] == 0) return 0;
    // Approximate the physical trigger's ten zones by uniform input intervals.
    const unsigned zone = std::min(9u, static_cast<unsigned>(position) * 10u / 256u);
    const uint16_t zones = effect.data[0] | (uint16_t(effect.data[1]) << 8);
    if(!(zones & (1u << zone))) return 0;
    const uint32_t packed = uint32_t(effect.data[2]) | (uint32_t(effect.data[3]) << 8) |
                            (uint32_t(effect.data[4]) << 16) | (uint32_t(effect.data[5]) << 24);
    const unsigned strength = ((packed >> (3 * zone)) & 7u) + 1u;
    // Preserve the previous approximation's 50% output cap. Frequency is used
    // to detect disabled effects; XInput cannot reproduce the requested waveform.
    return scale(strength * 4096u, std::clamp(gain, 0.0, 1.0));
}
inline Motors capBodyDuringTrigger(Motors body, Motors trigger)
{
    if(trigger.low == 0 && trigger.high == 0)
        return body;

    // PS5 exposes body haptic audio and adaptive-trigger effects as separate
    // output paths. On a DualSense they drive different actuator systems. The
    // Ally fallback maps both onto the same LOW/HIGH rumble pair, so allowing
    // body audio to exceed an already-active trigger fallback double-counts
    // part of a trigger event. Preserve the body signal for diagnostics but
    // cap the contribution used by the shared motors to the trigger envelope.
    return {std::min(body.low, trigger.low),
            std::min(body.high, trigger.high)};
}

inline Motors combine(Motors classic, Motors body, Motors trigger)
{
    // Do not add duplicate descriptions of the same impact, nor let a zero
    // from one source cancel another source. One writer publishes this result.
    return {std::max({classic.low, body.low, trigger.low}),
            std::max({classic.high, body.high, trigger.high})};
}
class Mixer
{
    uint8_t classicLow = 0, classicHigh = 0;
    uint64_t classicUntil = 0;
    Stereo bodyEnvelope;
    uint64_t bodyUntil = 0;
    TriggerEffect leftEffect, rightEffect;
    double bodyGain = 1.0, triggerGain = 1.0;
public:
    void reset() { *this = Mixer{}; }
    void setClassic(uint8_t low, uint8_t high, uint64_t now)
    { classicLow = low; classicHigh = high; classicUntil = now + 5000; }
    void setBody(Stereo value, uint64_t now)
    { bodyEnvelope = value; bodyUntil = now + 100; }
    void setTriggers(TriggerEffect left, TriggerEffect right)
    { leftEffect = left; rightEffect = right; }
    void setBodyGain(double gain) { bodyGain = gain; }
    void setTriggerGain(double gain) { triggerGain = gain; }
    Sources sample(uint8_t l2, uint8_t r2, uint64_t now, bool bodyEnabled, bool triggerEnabled) const
    {
        Sources s;
        if(now < classicUntil)
            s.classic = {scale(uint32_t(classicLow) << 8, bodyGain),
                         scale(uint32_t(classicHigh) << 8, bodyGain)};
        if(bodyEnabled && now < bodyUntil) s.body = downmix(bodyEnvelope, bodyGain);
        if(triggerEnabled)
        {
            s.l2 = triggerLevel(leftEffect, l2, triggerGain);
            s.r2 = triggerLevel(rightEffect, r2, triggerGain);
            // L2 and R2 have the SAME fallback transfer function. They do not
            // select the low-frequency and high-frequency motors respectively.
            const uint16_t level = std::max(s.l2, s.r2);
            s.trigger = {level, level};
        }

        // Only the Ally fallback needs this isolation. A real DualSense keeps
        // body haptics and adaptive triggers on separate actuator paths.
        s.bodyUsed = capBodyDuringTrigger(s.body, s.trigger);
        s.output = combine(s.classic, s.bodyUsed, s.trigger);
        return s;
    }
};
}
#endif
