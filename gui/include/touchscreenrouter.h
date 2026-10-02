// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
#ifndef CHIAKI_TOUCHSCREENROUTER_H
#define CHIAKI_TOUCHSCREENROUTER_H

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <vector>

// Deterministic touchscreen routing, independent of Qt, timers and networking.
// Coordinates and dimensions use the same window-local logical-pixel units.
namespace ChiakiTouch
{
constexpr uint32_t TouchpadButton = 1u << 14;
constexpr uint32_t PsButton = 1u << 15;
enum class Phase { Begin, Update, End, Cancel };
enum class PointState { Pressed, Moved, Stationary, Released };
struct Point { int id; double x, y; PointState state; };
struct Slot { int id = -1; double x = 0, y = 0; };
struct Snapshot
{
    std::array<Slot, 2> touches{};
    uint32_t buttons = 0;
};
struct Config
{
    // 0 = original touchpad behavior, 1..16 = Chiaki digital button bit + 1.
    // Order: top-left, top-right, bottom-left, bottom-right.
    std::array<int, 4> corners{{0, 0, 0, 0}};
    int cornerPercent = 8;
    bool edgeClick = true;
    bool threeFingerPs = true;
    int doubleTapMs = 650; // First release to second press, not release-to-release.
};

class Router
{
    struct Contact
    {
        double x = 0, y = 0, startX = 0, startY = 0;
        uint64_t started = 0;
        double maxTravel = 0;
        int action = 0; // Captured at DOWN; dragging never changes input ownership.
        int slot = -1;
        bool beganAtEdge = false;
    };
    Config config;
    std::map<int, Contact> contacts;
    Snapshot state, sent;
    std::array<uint64_t, 16> pulseUntil{};
    int nextId = 0;
    int doubleHeldId = -1;
    bool multiSequence = false, suppressed = false;
    bool lastTapValid = false;
    uint64_t lastTapTime = 0;
    double lastTapX = 0, lastTapY = 0;
    double aspectX = 1, aspectY = 1;

    static bool edge(double x, double y)
    { return x <= .05 || x >= .95 || y <= .05 || y >= .95; }
    double distance(double ax, double ay, double bx, double by) const
    { return std::hypot((ax-bx)*aspectX, (ay-by)*aspectY); }
    int actionAt(double x, double y) const
    {
        const double size = std::clamp(config.cornerPercent, 3, 20) / 100.0;
        const bool left = x <= size, right = x >= 1-size;
        const bool top = y <= size, bottom = y >= 1-size;
        if(!(left || right) || !(top || bottom)) return 0;
        const int action = config.corners[(bottom ? 2 : 0) + (right ? 1 : 0)];
        return action >= 1 && action <= 16 ? action : 0;
    }
    void pulse(uint32_t button, uint64_t now)
    {
        for(unsigned i = 0; i < 16; ++i)
            if(button & (1u << i)) pulseUntil[i] = std::max(pulseUntil[i], now + 100);
    }
    void compose(uint64_t now)
    {
        state.buttons = 0;
        for(unsigned i = 0; i < 16; ++i)
            if(pulseUntil[i] > now) state.buttons |= 1u << i;
        if(suppressed) return;
        for(const auto &entry : contacts)
        {
            const Contact &c = entry.second;
            if(c.action) state.buttons |= 1u << (c.action-1);
            else if(c.slot >= 0 && config.edgeClick && edge(c.x, c.y))
                state.buttons |= TouchpadButton;
            if(entry.first == doubleHeldId) state.buttons |= TouchpadButton;
        }
    }
    static bool equal(const Snapshot &a, const Snapshot &b)
    {
        if(a.buttons != b.buttons) return false;
        for(unsigned i = 0; i < 2; ++i)
            if(a.touches[i].id != b.touches[i].id ||
               (a.touches[i].id >= 0 && (a.touches[i].x != b.touches[i].x ||
                                        a.touches[i].y != b.touches[i].y))) return false;
        return true;
    }
    void publish(std::vector<Snapshot> &out, uint64_t now)
    {
        compose(now);
        if(!equal(state, sent)) { out.push_back(state); sent = state; }
    }
    void clearContacts()
    {
        contacts.clear();
        for(Slot &s : state.touches) s = Slot{};
        doubleHeldId = -1;
    }
    void allocate(Contact &c)
    {
        for(unsigned i = 0; i < 2; ++i)
        {
            if(state.touches[i].id >= 0) continue;
            // Avoid an ID collision when one finger stays down across a wrap.
            while(nextId == state.touches[0].id || nextId == state.touches[1].id)
                nextId = (nextId + 1) & 0x7f;
            state.touches[i] = Slot{nextId, c.x, c.y};
            nextId = (nextId + 1) & 0x7f;
            c.slot = static_cast<int>(i);
            return;
        }
    }
public:
    explicit Router(Config value = Config{}) : config(value) {}
    const Snapshot &current() const { return state; }
    bool hasPulse(uint64_t now) const
    {
        for(auto deadline : pulseUntil) if(deadline > now) return true;
        return false;
    }
    std::vector<Snapshot> reset(uint64_t now)
    {
        std::vector<Snapshot> out;
        clearContacts();
        pulseUntil.fill(0);
        suppressed = multiSequence = lastTapValid = false;
        publish(out, now);
        return out;
    }
    std::vector<Snapshot> tick(uint64_t now)
    { std::vector<Snapshot> out; publish(out, now); return out; }

    std::vector<Snapshot> update(Phase phase, const std::vector<Point> &points,
                                 double width, double height, uint64_t now)
    {
        if(phase == Phase::Cancel || !std::isfinite(width) || !std::isfinite(height) ||
           width <= 0 || height <= 0) return reset(now);
        for(const Point &p : points)
            if(!std::isfinite(p.x) || !std::isfinite(p.y)) return reset(now);
        const double shortSide = std::min(width, height);
        aspectX = width / shortSide;
        aspectY = height / shortSide;
        std::vector<Snapshot> out;
        std::map<int, Point> active;
        if(phase != Phase::End)
            for(const Point &p : points)
                if(p.state != PointState::Released) active.emplace(p.id, p);

        // A new sequence is also a recovery boundary for a lost END/CANCEL.
        if(phase == Phase::Begin)
        {
            if(!contacts.empty() || suppressed)
            {
                clearContacts(); suppressed = false; lastTapValid = false;
                publish(out, now);
            }
            multiSequence = false;
        }
        if(suppressed)
        {
            if(active.empty())
            {
                suppressed = false;
                clearContacts();
                publish(out, now); // All touch-UP transitions precede the PS press.
                pulse(PsButton, now);
                publish(out, now);
            }
            return out;
        }

        // Update travel (including the release position) before classifying taps.
        for(const Point &p : points)
        {
            auto it = contacts.find(p.id);
            if(it == contacts.end()) continue;
            Contact &c = it->second;
            c.x = std::clamp(p.x / width, 0.0, 1.0);
            c.y = std::clamp(p.y / height, 0.0, 1.0);
            c.maxTravel = std::max(c.maxTravel, distance(c.x,c.y,c.startX,c.startY));
            if(c.slot >= 0) { state.touches[c.slot].x = c.x; state.touches[c.slot].y = c.y; }
        }
        if(active.size() > 1 || contacts.size() > 1)
        { multiSequence = true; lastTapValid = false; }

        // Remove UP contacts first and publish before any slot can be reused.
        for(auto it = contacts.begin(); it != contacts.end();)
        {
            if(active.count(it->first)) { ++it; continue; }
            const Contact c = it->second;
            bool explicitUp = phase == Phase::End;
            for(const Point &p : points)
                if(p.id == it->first && p.state == PointState::Released) explicitUp = true;
            const bool wasDouble = it->first == doubleHeldId;
            if(explicitUp && !multiSequence && !c.action && !wasDouble &&
               !c.beganAtEdge && now >= c.started && now-c.started <= 400 && c.maxTravel <= .07)
            {
                lastTapValid = true; lastTapTime = now; lastTapX = c.x; lastTapY = c.y;
            }
            else lastTapValid = false;
            if(wasDouble) doubleHeldId = -1;
            if(c.slot >= 0) state.touches[c.slot] = Slot{};
            it = contacts.erase(it);
        }
        publish(out, now);

        for(const auto &entry : active)
        {
            if(contacts.count(entry.first)) continue;
            const Point &p = entry.second;
            Contact c;
            c.x = c.startX = std::clamp(p.x / width, 0.0, 1.0);
            c.y = c.startY = std::clamp(p.y / height, 0.0, 1.0);
            c.started = now;
            c.action = actionAt(c.x,c.y);
            c.beganAtEdge = config.edgeClick && edge(c.x,c.y);
            if(p.state != PointState::Pressed) multiSequence = true;
            if(p.state == PointState::Pressed && active.size() == 1 && !multiSequence &&
               !c.action && !c.beganAtEdge && lastTapValid && now >= lastTapTime &&
               now-lastTapTime <= static_cast<uint64_t>(std::clamp(config.doubleTapMs,200,1000)) &&
               distance(c.x,c.y,lastTapX,lastTapY) <= .18)
            {
                doubleHeldId = p.id;
                pulse(TouchpadButton, now);
                lastTapValid = false;
            }
            else if(p.state == PointState::Pressed) lastTapValid = false;
            if(c.action) pulse(1u << (c.action-1), now);
            contacts.emplace(entry.first,c);
        }

        bool capturedCorner = false;
        for(const auto &entry : contacts) capturedCorner |= entry.second.action != 0;
        if(config.threeFingerPs && active.size() >= 3 && !capturedCorner)
        {
            clearContacts(); pulseUntil.fill(0);
            suppressed = true; lastTapValid = false;
            publish(out, now);
            return out;
        }
        for(auto &entry : contacts)
        {
            Contact &c = entry.second;
            if(!c.action && c.slot < 0) allocate(c);
        }
        publish(out, now);
        return out;
    }
};
} // namespace ChiakiTouch
#endif
