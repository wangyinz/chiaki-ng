#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
"""Test production history generation, serialization, queueing and send boundary.

The only substituted layers are platform types, logging and transport. This is
NOT a PS5 emulator or proof of network delivery. --sender-source can point at an
older feedbacksender.c to demonstrate that the former batching fails the test.
"""
from pathlib import Path
import argparse
import os
import re
import shlex
import subprocess
import tempfile


def function(source: str, name: str) -> str:
    pattern = r"(?m)^(?:static |CHIAKI_EXPORT )[^\n]*\b" + re.escape(name) + r"\([^;]*?\)\n\{"
    match = re.search(pattern, source)
    if match is None:
        raise RuntimeError(f"Production function not found: {name}")
    opening = source.index("{", match.start())
    depth = 1
    end = opening + 1
    while depth:
        if end >= len(source):
            raise RuntimeError(f"Unclosed function: {name}")
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end] + "\n"


root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sender-source", type=Path, default=root / "lib/src/feedbacksender.c")
args = parser.parse_args()
sender = args.sender_source.read_text(encoding="utf-8")
wire = (root / "lib/src/feedback.c").read_text(encoding="utf-8")
header = (root / "lib/include/chiaki/feedbacksender.h").read_text(encoding="utf-8")
constants = "\n".join(re.findall(r"(?m)^#define (?:CHIAKI_FEEDBACK_HISTORY_PACKET_\w+|FEEDBACK_HISTORY_\w+)\s+[^\n]+", sender + "\n" + header))
serializers = "\n".join(function(wire, name) for name in [
    "chiaki_feedback_history_event_set_touchpad", "chiaki_feedback_history_event_set_button",
    "chiaki_feedback_history_buffer_init", "chiaki_feedback_history_buffer_fini",
    "chiaki_feedback_history_buffer_push", "chiaki_feedback_history_buffer_format"])
queue_helper = "feedback_sender_queue_history_event_locked"
production = function(sender, "feedback_sender_send_history_packet")
production += function(sender, "feedback_sender_flush_history_locked")
if queue_helper in sender:
    production += function(sender, queue_helper)
production += function(sender, "feedback_sender_record_history")
# Only the drain shim varies for old sources; assertions are unchanged.
sequenced = "ChiakiSeqNum16 sequence" in function(sender, "feedback_sender_send_history_packet")
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHIAKI_EXPORT
#define CHIAKI_CONTROLLER_TOUCHES_MAX 2
#define CHIAKI_CONTROLLER_BUTTONS_COUNT 16
#define CHIAKI_ERR_SUCCESS 0
#define CHIAKI_ERR_MEMORY 1
#define CHIAKI_ERR_BUF_TOO_SMALL 2
#define CHIAKI_ERR_INVALID_DATA 3
#define CHIAKI_LOGV(...) ((void)0)
#define CHIAKI_LOGW(...) ((void)0)
#define CHIAKI_LOGE(...) ((void)0)
#define CHECK(c) do { if(!(c)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c); exit(1); } } while(0)
'''
buttons = ["CROSS", "MOON", "BOX", "PYRAMID", "DPAD_LEFT", "DPAD_RIGHT", "DPAD_UP", "DPAD_DOWN", "L1", "R1", "L3", "R3", "OPTIONS", "SHARE", "TOUCHPAD", "PS"]
prefix += "\n".join(f"#define CHIAKI_CONTROLLER_BUTTON_{b} (1u<<{i})" for i, b in enumerate(buttons)) + "\n"
prefix += constants + r'''
#define CHIAKI_CONTROLLER_ANALOG_BUTTON_L2 (1u<<16)
#define CHIAKI_CONTROLLER_ANALOG_BUTTON_R2 (1u<<17)
typedef int ChiakiErrorCode;
typedef uint16_t ChiakiSeqNum16;
typedef struct { int id; uint16_t x,y; } Contact;
typedef struct { Contact touches[2]; uint32_t buttons; uint8_t l2_state,r2_state; } ChiakiControllerState;
typedef struct { uint8_t buf[5]; size_t len; } ChiakiFeedbackHistoryEvent;
typedef struct { ChiakiFeedbackHistoryEvent *events; size_t size,begin,len; } ChiakiFeedbackHistoryBuffer;
typedef struct {
    void *log,*takion;
    ChiakiSeqNum16 history_seq_num;
    ChiakiFeedbackHistoryBuffer history_buf;
    uint8_t history_packets[CHIAKI_FEEDBACK_HISTORY_PACKET_QUEUE_SIZE][CHIAKI_FEEDBACK_HISTORY_PACKET_BUF_SIZE];
    size_t history_packet_sizes[CHIAKI_FEEDBACK_HISTORY_PACKET_QUEUE_SIZE];
    ChiakiSeqNum16 history_packet_sequences[CHIAKI_FEEDBACK_HISTORY_PACKET_QUEUE_SIZE];
    size_t history_packet_begin,history_packet_len;
    bool history_dirty;
} ChiakiFeedbackSender;
typedef struct { uint16_t sequence; uint8_t bytes[CHIAKI_FEEDBACK_HISTORY_PACKET_BUF_SIZE]; size_t size; } Packet;
static Packet captured[CHIAKI_FEEDBACK_HISTORY_PACKET_QUEUE_SIZE];
static size_t captured_count;
static int transport_result;
static ChiakiErrorCode chiaki_takion_send_feedback_history(void *transport,uint16_t sequence,uint8_t *bytes,size_t size)
{
    (void)transport;
    CHECK(captured_count<CHIAKI_FEEDBACK_HISTORY_PACKET_QUEUE_SIZE);
    Packet *p=&captured[captured_count++];p->sequence=sequence;p->size=size;
    CHECK(size<=sizeof(p->bytes));memcpy(p->bytes,bytes,size);
    return transport_result;
}
'''
drain_call = "feedback_sender_send_history_packet(s,s->history_packet_sequences[i],s->history_packets[i],s->history_packet_sizes[i]);" if sequenced else "feedback_sender_send_history_packet(s,s->history_packets[i],s->history_packet_sizes[i]);"
suffix = r'''
static void init_sender(ChiakiFeedbackSender *s)
{
    memset(s,0,sizeof(*s));captured_count=0;transport_result=0;
    CHECK(chiaki_feedback_history_buffer_init(&s->history_buf,FEEDBACK_HISTORY_BUFFER_SIZE)==0);
}
static void emit_state(ChiakiFeedbackSender *s,ChiakiControllerState a,ChiakiControllerState b)
{
    feedback_sender_record_history(s,&a,&b);
    feedback_sender_flush_history_locked(s);
}
static void drain(ChiakiFeedbackSender *s)
{
    captured_count=0;
    while(s->history_packet_len) {
        size_t i=s->history_packet_begin;
        DRAIN_CALL
        s->history_packet_begin=(i+1)%CHIAKI_FEEDBACK_HISTORY_PACKET_QUEUE_SIZE;
        --s->history_packet_len;
    }
}
static void head(size_t index,uint8_t type,uint8_t id)
{ CHECK(index<captured_count);CHECK(captured[index].bytes[0]==type);CHECK(captured[index].bytes[1]==id); }
int main(void)
{
    ChiakiFeedbackSender s;
    ChiakiControllerState idle={{{-1,0,0},{-1,0,0}},0,0,0};
    ChiakiControllerState a={{{7,100,200},{9,400,500}},0,0,0},b=idle;
    init_sender(&s);b.buttons=CHIAKI_CONTROLLER_BUTTON_PS;
    emit_state(&s,a,b);
    printf("two UP + PS: queued=%zu (expected 3)\n",s.history_packet_len);
    CHECK(s.history_packet_len==3);drain(&s);
    head(0,0xc0,7);head(1,0xc0,9);head(2,0x80,0xae);
    CHECK(captured[0].sequence==0 && captured[1].sequence==1 && captured[2].sequence==2);
    CHECK(captured[0].size==5 && captured[1].size==10 && captured[2].size==12);
    CHECK(memcmp(captured[1].bytes+5,captured[0].bytes,5)==0);
    CHECK(memcmp(captured[2].bytes+2,captured[1].bytes,10)==0);
    chiaki_feedback_history_buffer_fini(&s.history_buf);

    init_sender(&s);a=idle;b=idle;b.touches[0]=(Contact){7,100,200};
    b.buttons=CHIAKI_CONTROLLER_BUTTON_TOUCHPAD;
    emit_state(&s,a,b);drain(&s);CHECK(captured_count==2);head(0,0xd0,7);head(1,0x80,0xb1);
    a=b;b=idle;emit_state(&s,a,b);drain(&s);CHECK(captured_count==2);head(0,0xc0,7);head(1,0x80,0x91);
    CHECK(captured[0].sequence==2 && captured[1].sequence==3);
    a=b;emit_state(&s,a,b);CHECK(s.history_packet_len==0);
    chiaki_feedback_history_buffer_fini(&s.history_buf);

    init_sender(&s);a=idle;a.touches[0]=(Contact){7,100,200};b=a;b.touches[0]=(Contact){8,300,400};
    emit_state(&s,a,b);drain(&s);CHECK(captured_count==2);head(0,0xc0,7);head(1,0xd0,8);
    chiaki_feedback_history_buffer_fini(&s.history_buf);

    init_sender(&s);a=idle;b=idle;b.touches[0]=(Contact){7,1919,1079};b.touches[1]=(Contact){9,0,0};
    b.buttons=0xffff;b.l2_state=255;b.r2_state=127;
    emit_state(&s,a,b);drain(&s);CHECK(captured_count==20);
    for(size_t i=0;i<captured_count;++i) CHECK(captured[i].sequence==i);
    CHECK(captured[0].bytes[2]==119 && captured[0].bytes[3]==244 && captured[0].bytes[4]==55);
    a=b;b=idle;emit_state(&s,a,b);drain(&s);CHECK(captured_count==20);head(0,0xc0,7);head(1,0xc0,9);
    chiaki_feedback_history_buffer_fini(&s.history_buf);

    init_sender(&s);s.history_seq_num=UINT16_MAX;a=idle;b=idle;b.buttons=(1u<<14)|(1u<<15);b.l2_state=1;
    emit_state(&s,a,b);drain(&s);CHECK(captured_count==3);
    CHECK(captured[0].sequence==65535 && captured[1].sequence==0 && captured[2].sequence==1);
    chiaki_feedback_history_buffer_fini(&s.history_buf);

    init_sender(&s);a=idle;b=idle;
    for(unsigned i=0;i<CHIAKI_FEEDBACK_HISTORY_PACKET_QUEUE_SIZE+8;++i) {
        b.buttons^=CHIAKI_CONTROLLER_BUTTON_PS;emit_state(&s,a,b);a=b;
    }
    CHECK(s.history_packet_len==CHIAKI_FEEDBACK_HISTORY_PACKET_QUEUE_SIZE);drain(&s);
    CHECK(captured_count==CHIAKI_FEEDBACK_HISTORY_PACKET_QUEUE_SIZE);
    for(size_t i=0;i<captured_count;++i) CHECK(captured[i].sequence==i+8);
    // Remaining packets retain recent redundancy even after a local queue drop.
    CHECK(captured[0].size==2*(FEEDBACK_HISTORY_RESEND_EVENT_COUNT+1));
    chiaki_feedback_history_buffer_fini(&s.history_buf);

    // Deterministic simultaneous two-contact transitions: no transport timing.
    init_sender(&s);a=idle;
    for(unsigned i=0;i<2000;++i) {
        b=idle;
        if(i%4!=3) {b.touches[0]=(Contact){7,(uint16_t)(i%1920),(uint16_t)(i%1080)};b.touches[1]=(Contact){9,300,400};}
        if(i%3==0) b.buttons=CHIAKI_CONTROLLER_BUTTON_PS;
        emit_state(&s,a,b);drain(&s);
        CHECK(captured_count<=4);
        for(size_t j=1;j<captured_count;++j) CHECK((uint16_t)(captured[j].sequence-captured[j-1].sequence)==1);
        a=b;
    }
    chiaki_feedback_history_buffer_fini(&s.history_buf);
    puts("Production history packet regressions passed (including 2,000 multi-contact transitions).");
    return 0;
}
'''.replace("DRAIN_CALL", drain_call)
with tempfile.TemporaryDirectory() as d:
    path = Path(d)/"history_test.c"
    exe = Path(d)/("history_test.exe" if os.name == "nt" else "history_test")
    path.write_text(prefix+serializers+production+suffix, encoding="utf-8")
    flags = shlex.split(os.environ.get("CFLAGS", ""))
    subprocess.run([os.environ.get("CC", "gcc"), "-std=c11", "-Wall", "-Wextra", "-Werror", *flags, str(path), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
