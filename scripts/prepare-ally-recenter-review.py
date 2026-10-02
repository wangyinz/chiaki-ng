#!/usr/bin/env python3
# Temporary, preimage-checked assembly helper; removed by its one-shot review job.
from pathlib import Path
import hashlib
import subprocess

ROOT = Path(__file__).resolve().parents[1]
expected = {
    'lib/src/orientation.c': 'a350737bf9021beb6f7e5d7f1e393f576f496bf0',
    'lib/include/chiaki/orientation.h': '43b5d1e3f889627dce8cc65aa09f7651bee08536',
    'gui/src/controllermanager.cpp': 'ca56331e0befaf1a6db8dc7d14473c96070a925f',
    'gui/src/streamsession.cpp': 'b2993193ccc4425008d762c6e8f40978a0b40ba6',
}
for path, sha in expected.items():
    data = (ROOT/path).read_bytes()
    actual = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    assert actual == sha, (path, actual, sha)

preserved = ['gui/include/touchscreenrouter.h', 'gui/include/allyrumble.h',
             'lib/src/feedbacksender.c', 'lib/include/chiaki/feedbacksender.h']
before = {path: (ROOT/path).read_bytes() for path in preserved}
controller_before = (ROOT/'gui/src/controllermanager.cpp').read_text()
stream_before = (ROOT/'gui/src/streamsession.cpp').read_text()

def replace(path, old, new):
    p = ROOT/path
    text = p.read_text()
    assert text.count(old) == 1, (path, old[:120], text.count(old))
    p.write_text(text.replace(old, new), newline='\n')

new_function = r'''

/* Recentring is not a cold sensor start. The captured acceleration already
 * defines the neutral reference, so do not replay the high-gain warmup. */
CHIAKI_EXPORT bool chiaki_orientation_tracker_recenter(ChiakiOrientationTracker *tracker,
        float gx, float gy, float gz, float ax, float ay, float az,
        ChiakiAccelNewZero *accel_zero, uint32_t timestamp_us)
{
    if(!isfinite(gx) || !isfinite(gy) || !isfinite(gz) ||
        !isfinite(ax) || !isfinite(ay) || !isfinite(az) ||
        (ax == 0.0f && ay == 0.0f && az == 0.0f))
        return false;
    chiaki_accel_new_zero_set_active(accel_zero, ax, ay, az, false);
    chiaki_orientation_tracker_init(tracker);
    /* Seed time and sensor state without integrating any pre-reset interval. */
    chiaki_orientation_tracker_update(tracker, gx, gy, gz, ax, ay, az,
        accel_zero, false, timestamp_us);
    tracker->sample_index = WARMUP_SAMPLES_COUNT;
    return true;
}
'''
p = ROOT/'lib/src/orientation.c'
p.write_text(p.read_text()+new_function, newline='\n')
replace('lib/include/chiaki/orientation.h',
    'CHIAKI_EXPORT void chiaki_orientation_tracker_apply_to_controller_state(',
    '/** Reset to the current neutral pose without restarting cold-start warmup.\n'
    ' * Returns false without changing state when the supplied sample is invalid. */\n'
    'CHIAKI_EXPORT bool chiaki_orientation_tracker_recenter(ChiakiOrientationTracker *tracker,\n'
    '\t\tfloat gx, float gy, float gz, float ax, float ay, float az,\n'
    '\t\tChiakiAccelNewZero *accel_zero, uint32_t timestamp_us);\n'
    'CHIAKI_EXPORT void chiaki_orientation_tracker_apply_to_controller_state(')
replace('gui/src/controllermanager.cpp',
    '\tchiaki_accel_new_zero_set_active(&accel_zero, real_accel.accel_x, real_accel.accel_y, real_accel.accel_z, false);\n\tchiaki_orientation_tracker_init(&orientation_tracker);',
    '\t// Preserve the calibrated sensor basis. Only a running Ally sensor is\n'
    '\t// recentered without high-gain startup; other controller paths stay intact.\n'
    '\tif(is_rog_ally && orientation_tracker.sample_index > 0)\n'
    '\t{\n'
    '\t\tif(chiaki_orientation_tracker_recenter(&orientation_tracker,\n'
    '\t\t\tstate.gyro_x, state.gyro_y, state.gyro_z,\n'
    '\t\t\treal_accel.accel_x, real_accel.accel_y, real_accel.accel_z,\n'
    '\t\t\t&accel_zero, last_motion_timestamp))\n'
    '\t\t{\n'
    '\t\t\tchiaki_orientation_tracker_apply_to_controller_state(&orientation_tracker, &state);\n'
    '\t\t\temit StateChanged();\n'
    '\t\t}\n'
    '\t\treturn;\n'
    '\t}\n'
    '\tchiaki_accel_new_zero_set_active(&accel_zero, real_accel.accel_x, real_accel.accel_y, real_accel.accel_z, false);\n\tchiaki_orientation_tracker_init(&orientation_tracker);')

replace('gui/src/streamsession.cpp',
    '\t\tChiakiAllyRumble::Sources sources;\n\t\tif(connected && haptics_handheld > 0)\n\t\t{\n\t\t\tconst auto input = controller->GetState();',
    '\t\tconst auto input = controller->GetState();\n\t\tChiakiAllyRumble::Sources sources;\n\t\tif(connected && haptics_handheld > 0)\n\t\t{')
replace('gui/src/streamsession.cpp',
    '\t\tif(now - ally_rumble_log_ms >= 250 && (sources.output.low || sources.output.high))\n\t\t{\n\t\t\tCHIAKI_LOGV(log.GetChiakiLog(),\n\t\t\t\t"Ally rumble classic low/high=%u/%u body=%u/%u trigger L2/R2=%u/%u -> motor low/high=%u/%u",\n\t\t\t\tsources.classic.low, sources.classic.high, sources.body.low, sources.body.high,',
    '\t\t// Input-only diagnostics at <=4 Hz, including zeros. These values are\n'
    '\t\t// the actual mixed command, unlike the upstream PCM-envelope log.\n'
    '\t\tif(now - ally_rumble_log_ms >= 250)\n\t\t{\n\t\t\tCHIAKI_LOGI(log.GetChiakiLog(),\n'
    '\t\t\t\t"Ally rumble input L2/R2=%u/%u trigger_enabled=%d connected=%d "\n'
    '\t\t\t\t"classic low/high=%u/%u body=%u/%u trigger L2/R2=%u/%u -> motor low/high=%u/%u",\n'
    '\t\t\t\tinput.l2_state, input.r2_state, ally_trigger_rumble_enabled, connected,\n'
    '\t\t\t\tsources.classic.low, sources.classic.high, sources.body.low, sources.body.high,')
replace('gui/src/streamsession.cpp',
    '"Rumble-haptics activity raw L=%u R=%u -> rumble L=%u R=%u"',
    '"Haptic PCM envelope raw L/R=%u/%u scaled L/R=%u/%u (pre-mix, not motor output)"')
replace('gui/src/streamsession.cpp',
    '\t\t\tCHIAKI_LOGV(log.GetChiakiLog(),\n\t\t\t\t"Trigger effects L[type=',
    '\t\t\tCHIAKI_LOGI(log.GetChiakiLog(),\n\t\t\t\t"Trigger effects L[type=')
replace('gui/src/streamsession.cpp',
    '\t\t\t\tfor(auto controller : controllers)\n\t\t\t\t\tcontroller->resetMotionControls();',
    '\t\t\t\tfor(auto controller : controllers)\n'
    '\t\t\t\t{\n'
    '\t\t\t\t\tcontroller->resetMotionControls();\n'
    '\t\t\t\t\tif(controller->IsRogAlly())\n'
    '\t\t\t\t\t{\n'
    '\t\t\t\t\t\tconst auto motion = controller->GetState();\n'
    '\t\t\t\t\t\tCHIAKI_LOGI(log.GetChiakiLog(),\n'
    '\t\t\t\t\t\t\t"Ally motion reset result gyro=%g,%g,%g accel=%g,%g,%g quat=%g,%g,%g,%g",\n'
    '\t\t\t\t\t\t\tmotion.gyro_x, motion.gyro_y, motion.gyro_z,\n'
    '\t\t\t\t\t\t\tmotion.accel_x, motion.accel_y, motion.accel_z,\n'
    '\t\t\t\t\t\t\tmotion.orient_w, motion.orient_x, motion.orient_y, motion.orient_z);\n'
    '\t\t\t\t\t}\n'
    '\t\t\t\t}')
replace('CMakeLists.txt', '${CHIAKI_VERSION_PATCH}-ally.1"', '${CHIAKI_VERSION_PATCH}-ally.2-rc.1"')
replace('.github/workflows/build-pr.yaml',
    '          python tests/ally/test_feedback_history.py',
    '          python tests/ally/test_feedback_history.py\n          python tests/ally/test_motion_reset.py')

for path in preserved:
    assert (ROOT/path).read_bytes() == before[path], path
controller_after=(ROOT/'gui/src/controllermanager.cpp').read_text()
a=controller_before.index('inline bool Controller::HandleSensorEvent')
b=controller_before.index('inline bool Controller::HandleTouchpadEvent',a)
assert controller_before[a:b] in controller_after
start=stream_before.index('void StreamSession::ApplyTouchscreenStates')
end=stream_before.index('void StreamSession::HandleDpadTouchEvent',start)
assert stream_before[start:end] in (ROOT/'gui/src/streamsession.cpp').read_text()
subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
print('Verified untouched touch routing/history, gyro basis and rumble transfer functions.')
