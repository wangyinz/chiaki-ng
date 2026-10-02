#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
"""Compile production orientation code with data-type stubs and synthetic IMU input.
These tests do not emulate an Ally sensor or a PlayStation receiver.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
STUB = r'''
#ifndef TEST_ORIENTATION_H
#define TEST_ORIENTATION_H
#include <stdint.h>
#include <stdbool.h>
#define CHIAKI_EXPORT
typedef struct { float x,y,z,w; } ChiakiOrientation;
typedef struct { float accel_x,accel_y,accel_z; } ChiakiAccelNewZero;
typedef struct { float gyro_x,gyro_y,gyro_z,accel_x,accel_y,accel_z;
 ChiakiOrientation orient; uint32_t timestamp; uint64_t sample_index; } ChiakiOrientationTracker;
typedef struct { float gyro_x,gyro_y,gyro_z,accel_x,accel_y,accel_z,
 orient_x,orient_y,orient_z,orient_w; } ChiakiControllerState;
void chiaki_orientation_init(ChiakiOrientation*);
void chiaki_orientation_update(ChiakiOrientation*,float,float,float,float,float,float,float,float);
void chiaki_orientation_tracker_init(ChiakiOrientationTracker*);
void chiaki_orientation_tracker_update(ChiakiOrientationTracker*,float,float,float,float,float,float,ChiakiAccelNewZero*,bool,uint32_t);
void chiaki_orientation_tracker_apply_to_controller_state(ChiakiOrientationTracker*,ChiakiControllerState*);
void chiaki_accel_new_zero_set_inactive(ChiakiAccelNewZero*,bool);
void chiaki_accel_new_zero_set_active(ChiakiAccelNewZero*,float,float,float,bool);
bool chiaki_orientation_tracker_recenter(ChiakiOrientationTracker*,float,float,float,float,float,float,ChiakiAccelNewZero*,uint32_t);
#endif
'''
TEST = r'''
#include <chiaki/orientation.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
static float angle(ChiakiOrientationTracker *t) {
 ChiakiControllerState s; chiaki_orientation_tracker_apply_to_controller_state(t,&s);
 double n=sqrt(s.orient_w*s.orient_w+s.orient_x*s.orient_x+s.orient_y*s.orient_y+s.orient_z*s.orient_z);
 assert(isfinite(n) && fabs(n-1.)<.01);
 return (float)(2*acos(fmin(1.,fabs(s.orient_w)/n))*180/3.141592653589793);
}
static float stationary(unsigned interval, bool recenter) {
 ChiakiOrientationTracker t; ChiakiAccelNewZero zero;
 chiaki_orientation_tracker_init(&t);
 assert(t.sample_index==0);
 if(recenter) {
  assert(chiaki_orientation_tracker_recenter(&t,0,0,0,.25f,.8f,-.6f,&zero,1000000));
 } else {
  /* Exact sequence used by the previous Controller::resetMotionControls(). */
  chiaki_accel_new_zero_set_active(&zero,.25f,.8f,-.6f,false);
  chiaki_orientation_tracker_update(&t,0,0,0,.25f,.8f,-.6f,&zero,false,1000000);
  assert(t.sample_index==1);
 }
 float peak=0;
 for(unsigned i=1;i<=100;i++) {
  float x=.005f*sinf(i*1.7f),y=.005f*cosf(i*1.1f),z=.005f*sinf(i*.9f);
  chiaki_orientation_tracker_update(&t,0,0,0,.25f+x,.8f+y,-.6f+z,&zero,false,1000000+i*interval);
  float a=angle(&t); if(a>peak)peak=a;
 }
 return peak;
}
int main(void) {
 for(unsigned step=5000;step<=35000;step+=5000) {
  float old=stationary(step,false),fixed=stationary(step,true);
  printf("stationary synthetic noise dt=%uus: cold reset %.3f deg; recenter %.3f deg\n",step,old,fixed);
  assert(old>5.f); assert(fixed<1.f);
 }
 ChiakiOrientationTracker t; ChiakiAccelNewZero zero;
 chiaki_orientation_tracker_init(&t);
 for(unsigned i=0;i<500;i++) {
  uint32_t time=UINT32_MAX-16u+i*20000u;
  assert(chiaki_orientation_tracker_recenter(&t,.01f,-.02f,.03f,.25f,.8f,-.6f,&zero,time));
  assert(t.timestamp==time && fabsf(t.gyro_y+.02f)<.0001f);
  assert(angle(&t)<.01f);
  chiaki_orientation_tracker_update(&t,0,0,0,.25f,.8f,-.6f,&zero,false,time+20000u);
  assert(angle(&t)<.1f);
 }
 ChiakiOrientationTracker saved=t; ChiakiAccelNewZero saved_zero=zero;
 assert(!chiaki_orientation_tracker_recenter(&t,NAN,0,0,0,1,0,&zero,0));
 assert(!chiaki_orientation_tracker_recenter(&t,0,0,0,0,0,0,&zero,0));
 assert(!chiaki_orientation_tracker_recenter(&t,0,0,0,INFINITY,1,0,&zero,0));
 assert(memcmp(&t,&saved,sizeof(t))==0);
 assert(memcmp(&zero,&saved_zero,sizeof(zero))==0);
 /* Real angular input still changes orientation after a reset. */
 assert(chiaki_orientation_tracker_recenter(&t,0,0,0,0,1,0,&zero,0));
 for(unsigned i=1;i<=100;i++)
  chiaki_orientation_tracker_update(&t,0,1.5707963f,0,0,1,0,&zero,false,i*10000u);
 assert(angle(&t)>80.f && angle(&t)<100.f);
 puts("Production motion-recenter tests passed.");
}
'''
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root/'chiaki').mkdir()
    (root/'chiaki/orientation.h').write_text(STUB)
    (root/'test.c').write_text(TEST)
    executable = root/('test.exe' if os.name == 'nt' else 'test')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    if os.environ.get('CHIAKI_TEST_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, '-I'+str(root),
                    str(ROOT/'lib/src/orientation.c'), str(root/'test.c'), '-lm', '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
