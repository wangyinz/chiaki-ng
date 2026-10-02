from pathlib import Path
import subprocess

base='04ee4182baf1044e45b133d714f0c7ec89e0d201'
def check(path):
    expected=subprocess.check_output(['git','rev-parse',base+':'+path],text=True).strip()
    actual=subprocess.check_output(['git','hash-object',path],text=True).strip()
    if actual!=expected: raise RuntimeError('Unexpected preimage '+path)
def once(c,a,b):
    if c.count(a)!=1: raise RuntimeError('Anchor count '+str(c.count(a))+': '+a[:160])
    return c.replace(a,b,1)
def save(p,c): Path(p).write_text(c.rstrip()+'\n')
for p in ['gui/src/streamsession.cpp','gui/include/streamsession.h','gui/src/controllermanager.cpp','CMakeLists.txt','scripts/chiaki-ng.iss']:
    check(p)
p='gui/include/streamsession.h'; c=Path(p).read_text()
c=once(c,'#include "touchscreenrouter.h"','#include "touchscreenrouter.h"\n#include "allyrumble.h"')
c=once(c,'\t\tuint16_t trigger_rumble_left = 0;\n\t\tuint16_t trigger_rumble_right = 0;', '''\t\tChiakiAllyRumble::Mixer ally_rumble;
\t\tQTimer *rumble_haptics_timer = nullptr;
\t\tbool ally_rumble_running = true;
\t\tuint64_t ally_rumble_log_ms = 0;''')
c=once(c,'\t\tvoid ConnectRumbleHaptics();','\t\tvoid ConnectRumbleHaptics();\n\t\tvoid UpdateAllyRumble();\n\t\tvoid StopAllyRumble();')
save(p,c)
p='gui/src/streamsession.cpp'; c=Path(p).read_text()
start=c.index('static uint16_t TriggerVibrationToRumble('); end=c.index('#define MICROPHONE_SAMPLES',start)
c=c[:start]+c[end:]
c=once(c,'\t\tConnectRumbleHaptics();\n\t}\n\tUpdateGamepads();','\t}\n\t// The Ally mixer also owns classic rumble when DualSense audio is disabled.\n\tConnectRumbleHaptics();\n\tUpdateGamepads();')
c=once(c,'StreamSession::~StreamSession()\n{','StreamSession::~StreamSession()\n{\n\tStopAllyRumble();')
c=once(c,'void StreamSession::Start()\n{','void StreamSession::Start()\n{\n\tally_rumble_running = true;\n\tif(rumble_haptics_timer) rumble_haptics_timer->start();')
c=once(c,'void StreamSession::Stop()\n{','void StreamSession::Stop()\n{\n\tStopAllyRumble();')
start=c.index('void StreamSession::ConnectRumbleHaptics()'); end=c.index('\nvoid StreamSession::QueueRumbleHaptics',start)
c=c[:start]+'''void StreamSession::UpdateAllyRumble()
{
	if(!ally_rumble_running) return;
	const uint64_t now = chiaki_time_now_monotonic_ms();
	for(auto controller : controllers)
	{
		if(!controller->IsRogAlly()) continue;
		ChiakiAllyRumble::Sources sources;
		if(connected && haptics_handheld > 0)
		{
			const auto input = controller->GetState();
			sources = ally_rumble.sample(input.l2_state, input.r2_state, now,
				rumble_haptics_intensity != RumbleHapticsIntensity::Off,
				ally_trigger_rumble_enabled);
		}
		// One writer for this device: a zero from classic/audio cannot erase
		// another source. SDL arguments are LOW/HIGH frequency, never L2/R2.
		controller->SetHapticRumble(sources.output.low, sources.output.high);
		if(now - ally_rumble_log_ms >= 250 && (sources.output.low || sources.output.high))
		{
			CHIAKI_LOGV(log.GetChiakiLog(),
				"Ally rumble classic low/high=%u/%u body=%u/%u trigger L2/R2=%u/%u -> motor low/high=%u/%u",
				sources.classic.low, sources.classic.high, sources.body.low, sources.body.high,
				sources.l2, sources.r2, sources.output.low, sources.output.high);
			ally_rumble_log_ms = now;
		}
	}
}

void StreamSession::StopAllyRumble()
{
	ally_rumble_running = false;
	if(rumble_haptics_timer) rumble_haptics_timer->stop();
	ally_rumble.reset();
	for(auto controller : controllers)
		if(controller->IsRogAlly()) controller->SetHapticRumble(0, 0);
}

void StreamSession::ConnectRumbleHaptics()
{
	if(rumble_haptics_connected) return;
	rumble_haptics = {};
	rumble_haptics.reserve(20);
	connect(this, &StreamSession::RumbleHapticPushed, this, &StreamSession::QueueRumbleHaptics);
	rumble_haptics_timer = new QTimer(this);
	rumble_haptics_timer->setInterval(RUMBLE_HAPTICS_PACKETS_PER_RUMBLE * 10);
	connect(rumble_haptics_timer, &QTimer::timeout, this, [this] {
		uint32_t left_sum = 0, right_sum = 0;
		for(size_t i = 0; i < RUMBLE_HAPTICS_PACKETS_PER_RUMBLE; ++i)
		{
			if(rumble_haptics.isEmpty()) break;
			const auto frame = rumble_haptics.dequeue();
			left_sum += frame.first; right_sum += frame.second;
		}
		const uint16_t left = left_sum / RUMBLE_HAPTICS_PACKETS_PER_RUMBLE;
		const uint16_t right = right_sum / RUMBLE_HAPTICS_PACKETS_PER_RUMBLE;
		ally_rumble.setBody({left, right}, chiaki_time_now_monotonic_ms());
		UpdateAllyRumble();
		// Preserve the existing non-Ally / external DualSense path.
		for(auto controller : controllers)
		{
			if(controller->IsRogAlly()) continue;
#if CHIAKI_GUI_ENABLE_STEAMDECK_NATIVE
			if(haptics_handheld < 1 && (controller->IsHandheld() || (sdeck && controller->IsSteamVirtualUnmasked())))
#else
			if(haptics_handheld < 1 && controller->IsHandheld())
#endif
				continue;
			if(left || right || rumble_haptics_on) controller->SetHapticRumble(left, right);
		}
		rumble_haptics_on = left || right;
	});
	rumble_haptics_timer->start();
	rumble_haptics_connected = true;
}
''' + c[end:]
c=once(c,'\t\tcase CHIAKI_EVENT_QUIT:\n','\t\tcase CHIAKI_EVENT_QUIT:\n\t\t\tQMetaObject::invokeMethod(this, &StreamSession::StopAllyRumble, Qt::QueuedConnection);\n')
c=once(c,'\t\t\tQMetaObject::invokeMethod(this, [this, left, right, left_adj, right_adj]() {\n\t\t\t\tfor(auto controller : controllers)\n\t\t\t\t{', '''\t\t\tQMetaObject::invokeMethod(this, [this, left, right, left_adj, right_adj]() {
				ally_rumble.setClassic(left, right, chiaki_time_now_monotonic_ms());
				UpdateAllyRumble();
				for(auto controller : controllers)
				{
					if(controller->IsRogAlly()) continue;''')
for label,next_label,body in [
 ('CHIAKI_EVENT_HAPTIC_INTENSITY','CHIAKI_EVENT_TRIGGER_INTENSITY','''
			const double ally_body_gain = rumble_multiplier;
			QMetaObject::invokeMethod(this, [this, ally_body_gain]() {
				ally_rumble.setBodyGain(ally_body_gain); UpdateAllyRumble();
			});
'''),
 ('CHIAKI_EVENT_TRIGGER_INTENSITY','CHIAKI_EVENT_TRIGGER_EFFECTS','''
			const double ally_trigger_gain = ps5_trigger_intensity < 0 ? 0.0 :
				(ps5_trigger_intensity == 0x90 ? 0.33 : ps5_trigger_intensity == 0x60 ? 0.5 : 1.0);
			QMetaObject::invokeMethod(this, [this, ally_trigger_gain]() {
				ally_rumble.setTriggerGain(ally_trigger_gain); UpdateAllyRumble();
			});
''')]:
    start=c.index('\t\tcase '+label+':'); end=c.index('\t\tcase '+next_label+':',start)
    block=c[start:end]
    mark='\t\t\tuint8_t trigger_intensity = (ps5_trigger_intensity < 0)'
    block=once(block,mark,body+mark)
    c=c[:start]+block+c[end:]
start=c.index('\t\tcase CHIAKI_EVENT_TRIGGER_EFFECTS:'); end=c.index('\n\t\tdefault:',start)
block=c[start:end]
block=once(block,'\t\t\tif(ps5_trigger_intensity < 0)\n\t\t\t\treturn;\n','')
a=block.index('\t\t\tconst uint16_t fallback_left'); b=block.index('\n\t\t\tbreak;',a)
block=block[:a]+'''			ChiakiAllyRumble::TriggerEffect left_effect, right_effect;
			left_effect.type = type_left; right_effect.type = type_right;
			std::copy_n(data_left, 10, left_effect.data.begin());
			std::copy_n(data_right, 10, right_effect.data.begin());
			QMetaObject::invokeMethod(this,
				[this, type_left, data_left, type_right, data_right, left_effect, right_effect]() {
					ally_rumble.setTriggers(left_effect, right_effect);
					UpdateAllyRumble();
					// Native DualSense retains its unmodified trigger-effect path.
					for(auto controller : controllers)
						controller->SetTriggerEffects(type_left, data_left, type_right, data_right);
				});'''+block[b:]
c=c[:start]+block+c[end:]
assert 'trigger_rumble_left' not in c and 'TriggerVibrationToRumble' not in c
save(p,c)
p='gui/src/controllermanager.cpp'; c=Path(p).read_text()
c=once(c,'SDL_GameControllerRumble(controller, left, right, 5000);','SDL_GameControllerRumble(controller, left, right, is_rog_ally ? 100 : 5000);')
save(p,c)
p='CMakeLists.txt'; c=Path(p).read_text()
c=once(c,'-ally-test.9','-ally.1')
c=once(c,'set(CPACK_PACKAGE_NAME "chiaki-ng")','file(WRITE "${CMAKE_BINARY_DIR}/ally-build-version.txt" "${CHIAKI_VERSION}\\n")\n\nset(CPACK_PACKAGE_NAME "chiaki-ng")')
save(p,c)
p='scripts/chiaki-ng.iss'; c=Path(p).read_text()
a=c.index('#define MyAppVersion()');b=c.index('\n[Setup]',a)
c=c[:a]+'#ifndef MyAppVersion\n'+c[a:b].rstrip()+'\n#endif\n'+c[b:]
c=once(c,'DisableDirPage=no','''DisableDirPage=no
UsePreviousAppDir=yes
UsePreviousPrivileges=yes
CloseApplications=yes
RestartApplications=no''')
save(p,c)
protected=['gui/include/touchscreenrouter.h','lib/src/feedbacksender.c','lib/include/chiaki/feedbacksender.h','gui/src/qmlmainwindow.cpp']
for p in protected: check(p)
baseline=subprocess.check_output(['git','show',base+':gui/src/streamsession.cpp'],text=True)
current=Path('gui/src/streamsession.cpp').read_text()
for name,next_name in [('ApplyTouchscreenStates','ResetTouchscreen'),('ResetTouchscreen','HandleTouchEvent'),('HandleTouchEvent','HandleDpadTouchEvent')]:
    start='void StreamSession::'+name+'(';end='void StreamSession::'+next_name+'('
    assert baseline[baseline.index(start):baseline.index(end)]==current[current.index(start):current.index(end)],name
print('Applied Ally rumble separation; validated touch/gyro source invariants.')
