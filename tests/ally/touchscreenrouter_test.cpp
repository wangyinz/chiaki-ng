// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
#include "touchscreenrouter.h"
#include <cassert>
#include <iostream>
#include <limits>
#include <random>
using namespace ChiakiTouch;
using P = PointState;
static auto send(Router &r, Phase phase, std::initializer_list<Point> points, uint64_t t)
{ return r.update(phase, points, 1000, 1000, t); }
static bool idle(const Router &r)
{ return r.current().touches[0].id < 0 && r.current().touches[1].id < 0 && r.current().buttons == 0; }
static int count(const Router &r)
{ return int(r.current().touches[0].id >= 0) + int(r.current().touches[1].id >= 0); }
int main()
{
    // Full-screen coordinates, including every edge and corner: no dead zones.
    for(auto x : {0.,1.,49.,50.,500.,950.,999.,1000.,1100.})
    for(auto y : {-50.,0.,49.,500.,951.,1000.})
    {
        Router r;
        send(r,Phase::Begin,{{1,x,y,P::Pressed}},0);
        assert(count(r)==1);
        const auto &s=r.current().touches[0];
        assert(s.x==std::clamp(x/1000,0.0,1.0));
        assert(s.y==std::clamp(y/1000,0.0,1.0));
        bool edge=s.x<=.05||s.x>=.95||s.y<=.05||s.y>=.95;
        assert(bool(r.current().buttons&TouchpadButton)==edge);
        send(r,Phase::End,{{1,x,y,P::Released}},20);
        assert(idle(r));
    }
    // Each independently configured corner captures its finger from DOWN to UP.
    for(int corner=0;corner<4;++corner)
    {
        Config cfg; cfg.corners[corner]=16;
        Router r(cfg);
        double x=corner%2?990:10,y=corner/2?990:10;
        send(r,Phase::Begin,{{3,x,y,P::Pressed}},1000);
        assert(count(r)==0 && r.current().buttons==PsButton);
        send(r,Phase::Update,{{3,500,500,P::Moved}},1050);
        assert(count(r)==0 && r.current().buttons==PsButton);
        send(r,Phase::End,{{3,500,500,P::Released}},1101);
        assert(idle(r));
    }
    // Passing through a configured corner during a normal swipe never presses PS.
    {
        Config cfg;cfg.corners[1]=16; Router r(cfg);
        send(r,Phase::Begin,{{1,500,500,P::Pressed}},0);
        send(r,Phase::Update,{{1,995,2,P::Moved}},20);
        assert(count(r)==1 && !(r.current().buttons&PsButton));
        assert(r.current().buttons&TouchpadButton);
    }
    // Shared button owners: lifting one mapped finger must not release the other.
    {
        Config cfg;cfg.corners={{16,16,0,0}};Router r(cfg);
        send(r,Phase::Begin,{{1,10,10,P::Pressed}},0);
        send(r,Phase::Update,{{1,10,10,P::Stationary},{2,990,10,P::Pressed}},10);
        send(r,Phase::Update,{{1,10,10,P::Released},{2,990,10,P::Stationary}},150);
        assert(r.current().buttons==PsButton);
        send(r,Phase::End,{{2,990,10,P::Released}},160); assert(idle(r));
    }
    // Double-tap: short pulses survive UP; a held second touch stays held.
    {
        Router r;
        send(r,Phase::Begin,{{1,400,400,P::Pressed}},100);
        send(r,Phase::End,{{1,400,400,P::Released}},200);assert(idle(r));
        send(r,Phase::Begin,{{2,500,400,P::Pressed}},800);
        assert(r.current().buttons&TouchpadButton);
        r.tick(1200); assert(r.current().buttons&TouchpadButton);
        send(r,Phase::End,{{2,500,400,P::Released}},1300); assert(idle(r));
        send(r,Phase::Begin,{{3,400,400,P::Pressed}},2000);
        send(r,Phase::End,{{3,400,400,P::Released}},2040);
        send(r,Phase::Begin,{{4,401,402,P::Pressed}},2120);
        send(r,Phase::End,{{4,401,402,P::Released}},2130);
        assert(r.current().buttons&TouchpadButton);
        r.tick(2220); assert(idle(r));
    }
    // Out-and-back drag is not a tap; nor is the last release of a multi-touch.
    {
        Router r;
        send(r,Phase::Begin,{{1,400,400,P::Pressed}},0);
        send(r,Phase::Update,{{1,600,400,P::Moved}},50);
        send(r,Phase::End,{{1,400,400,P::Released}},100);
        send(r,Phase::Begin,{{2,400,400,P::Pressed}},150);
        assert(!(r.current().buttons&TouchpadButton));
        send(r,Phase::Update,{{2,400,400,P::Stationary},{3,500,500,P::Pressed}},170);
        send(r,Phase::Update,{{2,400,400,P::Released},{3,500,500,P::Stationary}},190);
        send(r,Phase::End,{{3,500,500,P::Released}},210);
        send(r,Phase::Begin,{{4,500,500,P::Pressed}},300);
        assert(!(r.current().buttons&TouchpadButton));
    }
    // Three-finger PS: every release permutation; 3 -> 2 -> 1 stays suppressed.
    for(auto order: {std::array<int,3>{{1,2,3}},{{1,3,2}},{{2,1,3}},{{2,3,1}},{{3,1,2}},{{3,2,1}}})
    {
        Router r;
        send(r,Phase::Begin,{{1,400,400,P::Pressed}},0);
        send(r,Phase::Update,{{1,400,400,P::Stationary},{2,500,500,P::Pressed}},10);
        auto frames=send(r,Phase::Update,{{1,400,400,P::Stationary},{2,500,500,P::Stationary},{3,600,600,P::Pressed}},20);
        assert(count(r)==0 && r.current().buttons==0 && !frames.empty());
        std::map<int,Point> active{{1,{1,400,400,P::Stationary}},{2,{2,500,500,P::Stationary}},{3,{3,600,600,P::Stationary}}};
        for(int i=0;i<3;++i)
        {
            std::vector<Point> points;
            for(auto entry:active) { if(entry.first==order[i]) entry.second.state=P::Released; points.push_back(entry.second); }
            active.erase(order[i]);
            r.update(i==2?Phase::End:Phase::Update,points,1000,1000,30+i*10);
            assert(count(r)==0);
            assert(bool(r.current().buttons&PsButton)==(i==2));
        }
        r.tick(150); assert(idle(r));
        send(r,Phase::Begin,{{4,500,500,P::Pressed}},200);assert(count(r)==1);
        send(r,Phase::End,{{4,500,500,P::Released}},220);assert(idle(r));
    }
    // Cancel invalidates gestures and pulses (no delayed timer revival).
    {
        Router r;
        send(r,Phase::Begin,{{1,400,400,P::Pressed},{2,500,500,P::Pressed},{3,600,600,P::Pressed}},0);
        send(r,Phase::Cancel,{},50);r.tick(1000);assert(idle(r));
        Config cfg;cfg.corners[1]=16;r=Router(cfg);
        send(r,Phase::Begin,{{1,990,10,P::Pressed}},1100);
        r.reset(1101);r.tick(1300);assert(idle(r));
    }
    // Slot reuse in a single frame publishes an UP before the new DOWN.
    {
        Router r;send(r,Phase::Begin,{{1,400,400,P::Pressed}},0);
        int old=r.current().touches[0].id;
        auto frames=send(r,Phase::Update,{{1,400,400,P::Released},{2,600,600,P::Pressed}},20);
        assert(frames.size()>=2 && frames[0].touches[0].id==-1);
        assert(frames.back().touches[0].id>=0 && frames.back().touches[0].id!=old);
    }
    // ID wrap while a finger stays down; never duplicate a live protocol ID.
    {
        Config cfg;cfg.threeFingerPs=false;Router r(cfg);
        send(r,Phase::Begin,{{1,400,400,P::Pressed}},0);
        for(int i=2;i<600;++i)
        {
            send(r,Phase::Update,{{1,400,400,P::Stationary},{i,500,500,P::Pressed}},i*10);
            assert(count(r)==2 && r.current().touches[0].id!=r.current().touches[1].id);
            send(r,Phase::Update,{{1,400,400,P::Stationary},{i,500,500,P::Released}},i*10+1);
            assert(count(r)==1);
        }
        send(r,Phase::End,{{1,400,400,P::Released}},7000);assert(idle(r));
    }
    // Bad dimensions/NaN cannot reach clamp with invalid bounds or leave a hold.
    {
        Router r;send(r,Phase::Begin,{{1,0,0,P::Pressed}},0);
        r.update(Phase::Update,{},0,1000,10);assert(idle(r));
        r.update(Phase::Begin,{{2,std::numeric_limits<double>::quiet_NaN(),0,P::Pressed}},1000,1000,20);assert(idle(r));
    }
    // Lost END recovery, then 10,000 reproducible mixed sequences.
    {
        Router r;send(r,Phase::Begin,{{1,500,500,P::Pressed}},0);
        send(r,Phase::Begin,{{2,500,500,P::Pressed}},10);assert(count(r)==1);
        std::mt19937 gen(42);
        for(int n=0;n<10000;++n)
        {
            std::vector<Point> points;int fingers=1+gen()%4;
            for(int i=0;i<fingers;++i) points.push_back({i,double(gen()%1001),double(gen()%1001),P::Pressed});
            uint64_t t=10000+uint64_t(n)*500;
            r.update(Phase::Begin,points,1000,1000,t);
            for(auto &p:points)p.state=P::Released;
            r.update(Phase::End,points,1000,1000,t+30);
            r.tick(t+400);assert(idle(r));
        }
    }
    std::cout << "Touchscreen router regressions passed (10,000 randomized sequences).\n";
}
