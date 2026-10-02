#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
"""Exercise production history-transition logic with isolated transport stubs.
This tests history generation, NOT packet delivery or a physical PlayStation.
"""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root/'lib/src/feedbacksender.c').read_text()
start = source.index('static void feedback_sender_record_history(', source.index('static void feedback_sender_record_history(')+1)
end = source.index('\nstatic bool state_cond_check', start)
function = source[start:end]
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define CHIAKI_CONTROLLER_TOUCHES_MAX 2
#define CHIAKI_CONTROLLER_BUTTONS_COUNT 16
#define CHIAKI_CONTROLLER_ANALOG_BUTTON_L2 (1u<<16)
#define CHIAKI_CONTROLLER_ANALOG_BUTTON_R2 (1u<<17)
#define CHIAKI_ERR_SUCCESS 0
#define CHIAKI_LOGV(...) ((void)0)
#define CHIAKI_LOGE(...) ((void)0)
typedef int ChiakiErrorCode;
typedef struct { int id; uint16_t x,y; } Contact;
typedef struct { Contact touches[2]; uint32_t buttons; uint8_t l2_state,r2_state; } ChiakiControllerState;
typedef struct { bool touch,down; uint32_t id; uint16_t x,y; } ChiakiFeedbackHistoryEvent;
typedef struct { ChiakiFeedbackHistoryEvent events[32]; size_t len; } Buffer;
typedef struct { void *log; Buffer history_buf; bool history_dirty; } ChiakiFeedbackSender;
static void chiaki_feedback_history_event_set_touchpad(ChiakiFeedbackHistoryEvent *e,bool down,uint8_t id,uint16_t x,uint16_t y)
{ *e=(ChiakiFeedbackHistoryEvent){true,down,id,x,y}; }
static ChiakiErrorCode chiaki_feedback_history_event_set_button(ChiakiFeedbackHistoryEvent *e,uint64_t id,uint8_t state)
{ *e=(ChiakiFeedbackHistoryEvent){false,state!=0,(uint32_t)id,0,0};return 0; }
static void chiaki_feedback_history_buffer_push(Buffer *b,const ChiakiFeedbackHistoryEvent *e)
{ assert(b->len<32);b->events[b->len++]=*e; }
'''
suffix = r'''
int main(void)
{
    ChiakiControllerState a={{{7,100,200},{-1,0,0}},0,0,0};
    ChiakiControllerState b=a;
    ChiakiFeedbackSender sender={0};
    b.touches[0]=(Contact){8,300,400};
    feedback_sender_record_history(&sender,&a,&b);
    assert(sender.history_buf.len==2);
    assert(!sender.history_buf.events[0].down && sender.history_buf.events[0].id==7);
    assert(sender.history_buf.events[1].down && sender.history_buf.events[1].id==8);
    sender=(ChiakiFeedbackSender){0};
    a.touches[1]=(Contact){9,400,500};b=a;
    b.touches[0].id=-1;b.touches[1].id=-1;b.buttons=1u<<15;
    feedback_sender_record_history(&sender,&a,&b);
    assert(sender.history_buf.len==3);
    assert(sender.history_buf.events[0].touch && !sender.history_buf.events[0].down);
    assert(sender.history_buf.events[1].touch && !sender.history_buf.events[1].down);
    assert(!sender.history_buf.events[2].touch && sender.history_buf.events[2].id==(1u<<15));
    sender=(ChiakiFeedbackSender){0};a=b;b.buttons=0;
    feedback_sender_record_history(&sender,&a,&b);
    assert(sender.history_buf.len==1 && !sender.history_buf.events[0].down);
    sender=(ChiakiFeedbackSender){0};a=b;
    feedback_sender_record_history(&sender,&a,&b);
    assert(sender.history_buf.len==0);
    puts("Production feedback-history regression cases passed.");
    return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
    path=Path(d)/'history_test.c';exe=Path(d)/('history_test.exe' if os.name=='nt' else 'history_test')
    path.write_text(prefix+function+suffix)
    subprocess.run([os.environ.get('CC','gcc'),'-std=c11','-Wall','-Wextra','-Werror',str(path),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
