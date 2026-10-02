"""One-shot, preimage-checked source update for the user's Ally review branch."""
from pathlib import Path
import subprocess
import re

BASE = '7c92ab67d74d2bcef69814e51d9c8b54f3b16679'
changes = {}
def load(path):
    data = Path(path).read_bytes()
    expected = subprocess.check_output(['git','rev-parse',f'{BASE}:{path}'],text=True).strip()
    actual = subprocess.check_output(['git','hash-object','--stdin'],input=data).decode().strip()
    if actual != expected:
        raise RuntimeError(f'Preimage changed: {path}; refusing to overwrite')
    return data.decode('utf-8')
def replace(text, old, new, count=1):
    if text.count(old) != count:
        raise RuntimeError(f'Expected {count} occurrences, got {text.count(old)}: {old[:120]!r}')
    return text.replace(old,new)
def save(path,text):
    changes[path] = text

p='gui/include/streamsession.h';s=load(p)
s=replace(s,'#include <QPointF>','#include "touchscreenrouter.h"')
a=s.index('\t\tQMap<int, uint8_t> touch_tracker;');b=s.index('\t\tint8_t mouse_touch_id;',a)
s=s[:a]+'''\t\tChiakiTouch::Router touchscreen;
\t\tQTimer *touchscreen_timer = nullptr;
\t\tbool ally_trigger_rumble_enabled = false;
\t\tvoid ApplyTouchscreenStates(const std::vector<ChiakiTouch::Snapshot> &states);
'''+s[b:]
s=replace(s,'\t\tvoid HandleTouchEvent(QTouchEvent *event, qreal width, qreal height);','\t\tvoid HandleTouchEvent(QTouchEvent *event, qreal width, qreal height);\n\t\tvoid ResetTouchscreen();')
s=replace(s,'void BlockInput(bool block) { input_block = block ? 1 : 2; SendFeedbackState(); }','void BlockInput(bool block) { if(block) ResetTouchscreen(); input_block = block ? 1 : 2; SendFeedbackState(); }')
save(p,s)

p='gui/src/streamsession.cpp';s=load(p)
for line in ['#define TOUCH_TAP_MAX_DURATION_MS 400\n','#define TOUCH_TAP_MAX_DISTANCE 0.07\n','#define TOUCH_DOUBLE_TAP_INTERVAL_MS 650\n','#define TOUCH_DOUBLE_TAP_MAX_DISTANCE 0.18\n']:
    s=replace(s,line,'')
a=s.index('\ttouch_tracker = QMap<int, uint8_t>();');b=s.index('\tmouse_touch_id=-1;',a)
s=s[:a]+'''\tChiakiTouch::Config touch_config;
\tfor(int corner = 0; corner < 4; ++corner)
\t\ttouch_config.corners[corner] = connect_info.settings->GetTouchscreenCorner(corner);
\ttouch_config.cornerPercent = connect_info.settings->GetTouchscreenCornerSize();
\ttouch_config.edgeClick = connect_info.settings->GetTouchscreenEdgeClick();
\ttouch_config.threeFingerPs = connect_info.settings->GetTouchscreenThreeFingerPs();
\ttouch_config.doubleTapMs = connect_info.settings->GetTouchscreenDoubleTapMs();
\ttouchscreen = ChiakiTouch::Router(touch_config);
\tally_trigger_rumble_enabled = connect_info.settings->GetAllyTriggerRumbleEnabled();
\ttouchscreen_timer = new QTimer(this);
\ttouchscreen_timer->setTimerType(Qt::PreciseTimer);
\ttouchscreen_timer->setInterval(10);
\tconnect(touchscreen_timer, &QTimer::timeout, this, [this] {
\t\tconst uint64_t now = chiaki_time_now_monotonic_ms();
\t\tApplyTouchscreenStates(touchscreen.tick(now));
\t\tif(!touchscreen.hasPulse(now)) touchscreen_timer->stop();
\t});
\tCHIAKI_LOGI(log.GetChiakiLog(),
\t\t"Touchscreen config: corners=%d,%d,%d,%d size=%d%% edge=%d three_finger_ps=%d double_tap_gap=%dms",
\t\ttouch_config.corners[0], touch_config.corners[1], touch_config.corners[2], touch_config.corners[3],
\t\ttouch_config.cornerPercent, touch_config.edgeClick, touch_config.threeFingerPs, touch_config.doubleTapMs);
'''+s[b:]
a=s.index('void StreamSession::HandleTouchEvent(');b=s.index('\nvoid StreamSession::HandleDpadTouchEvent',a)
s=s[:a]+'''void StreamSession::ApplyTouchscreenStates(const std::vector<ChiakiTouch::Snapshot> &states)
{
\tstatic_assert(ChiakiTouch::TouchpadButton == CHIAKI_CONTROLLER_BUTTON_TOUCHPAD, "Touchpad bit mismatch");
\tstatic_assert(ChiakiTouch::PsButton == CHIAKI_CONTROLLER_BUTTON_PS, "PS bit mismatch");
\tfor(const auto &snapshot : states)
\t{
\t\tconst bool transition = touch_state.buttons != snapshot.buttons ||
\t\t\ttouch_state.touches[0].id != snapshot.touches[0].id ||
\t\t\ttouch_state.touches[1].id != snapshot.touches[1].id;
\t\ttouch_state.buttons = snapshot.buttons;
\t\tfor(size_t i = 0; i < CHIAKI_CONTROLLER_TOUCHES_MAX; ++i)
\t\t{
\t\t\ttouch_state.touches[i].id = static_cast<int8_t>(snapshot.touches[i].id);
\t\t\ttouch_state.touches[i].x = static_cast<uint16_t>(std::lround(snapshot.touches[i].x * (PS_TOUCHPAD_MAX_X - 1)));
\t\t\ttouch_state.touches[i].y = static_cast<uint16_t>(std::lround(snapshot.touches[i].y * (PS_TOUCHPAD_MAX_Y - 1)));
\t\t}
\t\tif(transition)
\t\t\tCHIAKI_LOGV(log.GetChiakiLog(), "Touchscreen routed buttons=%08x slots=%d,%d",
\t\t\t\ttouch_state.buttons, touch_state.touches[0].id, touch_state.touches[1].id);
\t\tSendFeedbackState();
\t}
}

void StreamSession::ResetTouchscreen()
{
\tif(touchscreen_timer) touchscreen_timer->stop();
\tApplyTouchscreenStates(touchscreen.reset(chiaki_time_now_monotonic_ms()));
}

void StreamSession::HandleTouchEvent(QTouchEvent *event, qreal width, qreal height)
{
\tif(input_block) { ResetTouchscreen(); return; }
\tChiakiTouch::Phase phase = ChiakiTouch::Phase::Update;
\tif(event->type() == QEvent::TouchBegin) phase = ChiakiTouch::Phase::Begin;
\telse if(event->type() == QEvent::TouchEnd) phase = ChiakiTouch::Phase::End;
\telse if(event->type() == QEvent::TouchCancel) phase = ChiakiTouch::Phase::Cancel;
\tstd::vector<ChiakiTouch::Point> points;
\tpoints.reserve(event->points().size());
\tfor(const auto &point : event->points())
\t{
\t\tChiakiTouch::PointState state = ChiakiTouch::PointState::Stationary;
\t\tif(point.state() == QEventPoint::State::Pressed) state = ChiakiTouch::PointState::Pressed;
\t\telse if(point.state() == QEventPoint::State::Released) state = ChiakiTouch::PointState::Released;
\t\telse if(point.state() == QEventPoint::State::Updated) state = ChiakiTouch::PointState::Moved;
\t\tpoints.push_back({point.id(), point.scenePosition().x(), point.scenePosition().y(), state});
\t}
\tconst uint64_t now = chiaki_time_now_monotonic_ms();
\tApplyTouchscreenStates(touchscreen.update(phase, points, width, height, now));
\tif(touchscreen.hasPulse(now)) touchscreen_timer->start();
\telse touchscreen_timer->stop();
\tevent->accept();
}
'''+s[b:]
s=replace(s,'void StreamSession::Stop()\n{\n','void StreamSession::Stop()\n{\n\tResetTouchscreen();\n')
s=replace(s,'StreamSession::~StreamSession()\n{','StreamSession::~StreamSession()\n{\n\tif(touchscreen_timer) touchscreen_timer->stop();')
a=s.index('\t\t\tif(controller->IsRogAlly() && mouse_touch_enabled)');b=s.index('\t\t\tif(controller->IsHandheld())',a)
s=s[:a]+s[b:]
s=replace(s,'void StreamSession::HandleMouseMoveEvent(QMouseEvent *event, qreal width, qreal height)\n{','void StreamSession::HandleMouseMoveEvent(QMouseEvent *event, qreal width, qreal height)\n{\n\tif(width <= 0 || height <= 0) return;')
s=replace(s,'std::clamp(0.0, event->scenePosition().x(), width)','std::clamp(event->scenePosition().x(), qreal(0), width)')
s=replace(s,'std::clamp(0.0, event->scenePosition().y(), height)','std::clamp(event->scenePosition().y(), qreal(0), height)')
s=replace(s,'\t\tif(temp_left == 0 && temp_right == 0)\n\t\t\treturn;\n','')
s=replace(s,'uint32_t temp_left = (suml / buf_count);','uint32_t temp_left = std::min<uint32_t>(suml / buf_count, UINT16_MAX);')
s=replace(s,'uint32_t temp_right = (sumr / buf_count);','uint32_t temp_right = std::min<uint32_t>(sumr / buf_count, UINT16_MAX);')
a=s.index('\t\tbool send_rumble_haptics = false;');b=s.index('\n\t\treturn;',a)
s=s[:a]+'\t\temit RumbleHapticPushed(left, right);'+s[b:]
s=replace(s,'\trumble_haptics.enqueue(qMakePair(left, right));','\twhile(rumble_haptics.size() >= 12) rumble_haptics.dequeue();\n\trumble_haptics.enqueue(qMakePair(left, right));')
s=replace(s,'if(controller->IsRogAlly())\n\t\t\t\t{\n\t\t\t\t\toutput_left = qMax(output_left, trigger_rumble_left);\n\t\t\t\t\toutput_right = qMax(output_right, trigger_rumble_right);\n\t\t\t\t}', '''if(controller->IsRogAlly() && ally_trigger_rumble_enabled && ps5_trigger_intensity >= 0)
\t\t\t\t{
\t\t\t\t\t// Experimental approximation, not DualSense trigger resistance.
\t\t\t\t\t// Effect packets describe configuration; never vibrate an untouched trigger.
\t\t\t\t\tconst auto input = controller->GetState();
\t\t\t\t\tif(input.l2_state > 25) output_left = qMax(output_left, trigger_rumble_left);
\t\t\t\t\tif(input.r2_state > 25) output_right = qMax(output_right, trigger_rumble_right);
\t\t\t\t}''')
s=replace(s,'trigger_rumble_left > 0 || trigger_rumble_right > 0;','(ally_trigger_rumble_enabled && (trigger_rumble_left > 0 || trigger_rumble_right > 0));')
save(p,s)

p='gui/include/settings.h';s=load(p)
anchor='\t\tbool GetForceRogAllyInputProfile() const';pos=s.index(anchor)
s=s[:pos]+'''\t\tint GetTouchscreenCorner(int corner) const
\t\t{ return corner >= 0 && corner < 4 ? qBound(0, settings.value(QString("settings/touchscreen_corner_%1").arg(corner), 0).toInt(), 16) : 0; }
\t\tvoid SetTouchscreenCorner(int corner, int action)
\t\t{ if(corner >= 0 && corner < 4) settings.setValue(QString("settings/touchscreen_corner_%1").arg(corner), qBound(0, action, 16)); }
\t\tint GetTouchscreenCornerSize() const { return qBound(3, settings.value("settings/touchscreen_corner_size", 8).toInt(), 20); }
\t\tvoid SetTouchscreenCornerSize(int value) { settings.setValue("settings/touchscreen_corner_size", qBound(3, value, 20)); }
\t\tbool GetTouchscreenEdgeClick() const { return settings.value("settings/touchscreen_edge_click", true).toBool(); }
\t\tvoid SetTouchscreenEdgeClick(bool value) { settings.setValue("settings/touchscreen_edge_click", value); }
\t\tbool GetTouchscreenThreeFingerPs() const { return settings.value("settings/touchscreen_three_finger_ps", true).toBool(); }
\t\tvoid SetTouchscreenThreeFingerPs(bool value) { settings.setValue("settings/touchscreen_three_finger_ps", value); }
\t\tint GetTouchscreenDoubleTapMs() const { return qBound(200, settings.value("settings/touchscreen_double_tap_ms", 650).toInt(), 1000); }
\t\tvoid SetTouchscreenDoubleTapMs(int value) { settings.setValue("settings/touchscreen_double_tap_ms", qBound(200, value, 1000)); }
\t\tbool GetAllyTriggerRumbleEnabled() const { return settings.value("settings/ally_trigger_rumble_enabled", false).toBool(); }
\t\tvoid SetAllyTriggerRumbleEnabled(bool value) { settings.setValue("settings/ally_trigger_rumble_enabled", value); }

'''+s[pos:];save(p,s)

props=[('int','touchscreenCornerSize','TouchscreenCornerSize'),('bool','touchscreenEdgeClick','TouchscreenEdgeClick'),('bool','touchscreenThreeFingerPs','TouchscreenThreeFingerPs'),('int','touchscreenDoubleTapMs','TouchscreenDoubleTapMs'),('bool','allyTriggerRumbleEnabled','AllyTriggerRumbleEnabled')]
p='gui/include/qmlsettings.h';s=load(p)
anchor='    Q_PROPERTY(bool forceRogAllyInputProfile READ forceRogAllyInputProfile WRITE setForceRogAllyInputProfile NOTIFY forceRogAllyInputProfileChanged)'
lines='\n    Q_PROPERTY(QVariantList touchscreenCorners READ touchscreenCorners NOTIFY touchscreenChanged)'
for typ,name,cap in props:
    lines+=f'\n    Q_PROPERTY({typ} {name} READ {name} WRITE set{cap} NOTIFY touchscreenChanged)'
s=replace(s,anchor,anchor+lines)
anchor='    bool forceRogAllyInputProfile() const;'
methods='    QVariantList touchscreenCorners() const;\n    Q_INVOKABLE void setTouchscreenCorner(int corner, int action);\n'
for typ,name,cap in props: methods+=f'    {typ} {name}() const;\n    void set{cap}({typ} value);\n'
s=replace(s,anchor,methods+'\n'+anchor)
s=replace(s,'    void forceRogAllyInputProfileChanged();','    void forceRogAllyInputProfileChanged();\n    void touchscreenChanged();')
s=re.sub(r'(#include [^\n]+\n)',r'\1#include <QVariant>\n',s,count=1);save(p,s)
p='gui/src/qmlsettings.cpp';s=load(p)
new='''
QVariantList QmlSettings::touchscreenCorners() const
{
    QVariantList values;
    for(int i = 0; i < 4; ++i) values.append(settings->GetTouchscreenCorner(i));
    return values;
}
void QmlSettings::setTouchscreenCorner(int corner, int action)
{
    settings->SetTouchscreenCorner(corner, action);
    emit touchscreenChanged();
}
'''
for typ,name,cap in props:
    new+=f'''{typ} QmlSettings::{name}() const {{ return settings->Get{cap}(); }}
void QmlSettings::set{cap}({typ} value)
{{ settings->Set{cap}(value); emit touchscreenChanged(); }}
'''
s+='\n'+new;save(p,s)

p='gui/src/qml/SettingsDialog.qml';s=load(p)
anchor='''                        RowLayout {
                            spacing: 10
                            Layout.alignment: Qt.AlignHCenter
                            Label {
                                Layout.alignment: Qt.AlignRight
                                text: qsTr("ROG Ally Input Profile:")'''
new='''                        ColumnLayout {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.preferredWidth: 620
                            spacing: 10
                            Label { text: qsTr("Touchscreen / Corner Buttons"); font.bold: true }
                            Label {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                text: qsTr("Original behavior keeps touch coordinates and edge clicks. A mapped corner captures its finger as a button until release. Changes apply on the next stream.")
                            }
                            Repeater {
                                model: [qsTr("Top left"), qsTr("Top right"), qsTr("Bottom left"), qsTr("Bottom right")]
                                delegate: RowLayout {
                                    required property int index
                                    required property string modelData
                                    Layout.fillWidth: true
                                    Label { text: modelData; Layout.preferredWidth: 130 }
                                    C.ComboBox {
                                        Layout.fillWidth: true
                                        model: [qsTr("Original behavior"), qsTr("Cross"), qsTr("Circle"), qsTr("Square"), qsTr("Triangle"), qsTr("Dpad Left"), qsTr("Dpad Right"), qsTr("Dpad Up"), qsTr("Dpad Down"), qsTr("L1"), qsTr("R1"), qsTr("L3"), qsTr("R3"), qsTr("Options"), qsTr("Share"), qsTr("Touchpad Click"), qsTr("PS")]
                                        currentIndex: Chiaki.settings.touchscreenCorners[parent.index]
                                        onActivated: value => Chiaki.settings.setTouchscreenCorner(parent.index, value)
                                    }
                                }
                            }
                            RowLayout {
                                Label { text: qsTr("Corner size:") }
                                Slider {
                                    from: 3; to: 20; stepSize: 1
                                    value: Chiaki.settings.touchscreenCornerSize
                                    onMoved: Chiaki.settings.touchscreenCornerSize = value
                                }
                                Label { text: Chiaki.settings.touchscreenCornerSize + qsTr("% of width and height") }
                            }
                            C.CheckBox {
                                text: qsTr("Original edge touchpad click (5% border)")
                                checked: Chiaki.settings.touchscreenEdgeClick
                                onToggled: Chiaki.settings.touchscreenEdgeClick = checked
                            }
                            C.CheckBox {
                                text: qsTr("Three-finger tap for PS (outside mapped corners)")
                                checked: Chiaki.settings.touchscreenThreeFingerPs
                                onToggled: Chiaki.settings.touchscreenThreeFingerPs = checked
                            }
                            RowLayout {
                                Label { text: qsTr("Double-tap gap:") }
                                Slider {
                                    from: 200; to: 1000; stepSize: 50
                                    value: Chiaki.settings.touchscreenDoubleTapMs
                                    onMoved: Chiaki.settings.touchscreenDoubleTapMs = value
                                }
                                Label { text: Chiaki.settings.touchscreenDoubleTapMs + qsTr(" ms") }
                            }
                            C.CheckBox {
                                text: qsTr("Experimental Ally trigger-to-rumble approximation")
                                checked: Chiaki.settings.allyTriggerRumbleEnabled
                                onToggled: Chiaki.settings.allyTriggerRumbleEnabled = checked
                            }
                        }
'''
s=replace(s,anchor,new+anchor);save(p,s)

p='gui/src/qmlmainwindow.cpp';s=load(p)
s=replace(s,'    case QEvent::MouseButtonDblClick:\n','    case QEvent::MouseButtonDblClick:\n        if (static_cast<QMouseEvent*>(event)->source() != Qt::MouseEventNotSynthesized)\n            return true;\n')
s=replace(s,'    case QEvent::TouchBegin:\n','    case QEvent::WindowDeactivate:\n        if (session) session->ResetTouchscreen();\n        break;\n    case QEvent::TouchBegin:\n')
s=replace(s,'            session->HandleTouchEvent(static_cast<QTouchEvent*>(event), width(), height());\n            return true;','            session->HandleTouchEvent(static_cast<QTouchEvent*>(event), width(), height());\n            event->accept();\n            return true;')
save(p,s)

p='gui/CMakeLists.txt';s=load(p)
s=replace(s,'\tinclude/streamsession.h\n','\tinclude/streamsession.h\n\tinclude/touchscreenrouter.h\n')
s=replace(s,'target_include_directories(chiaki PRIVATE include)','target_include_directories(chiaki PRIVATE include)\ntarget_compile_features(chiaki PRIVATE cxx_std_17)');save(p,s)

p='gui/src/controllermanager.cpp';s=load(p)
a=s.index('\t\t\t// RC71L calibration:');b=s.index('\t\t\tif(is_rog_ally)',a)
s=s[:a]+'''\t\t\t// Experimental Ally transform retained from the prior test branch.
\t\t\t// Axis/sign correctness still needs physical-device validation.
\t\t\t// Apply the same proper rotation to gyro and acceleration.
'''+s[b:]
s=replace(s,'\t\t\tcontroller = SDL_GameControllerOpen(i);\n','\t\t\tcontroller = SDL_GameControllerOpen(i);\n\t\t\tif(!controller) break;\n')
save(p,s)

p='lib/src/feedbacksender.c';s=load(p)
s=replace(s,'\t\telse if(state_now->touches[i].id >= 0','\t\t// A slot replacement requires BOTH old-UP and new-DOWN.\n\t\tif(state_now->touches[i].id >= 0')
s=replace(s,'\t\t\tchiaki_feedback_history_event_set_touchpad(&event, false,','\t\t\tCHIAKI_LOGV(feedback_sender->log, "Touch history UP slot=%zu id=%d", i, state_prev->touches[i].id);\n\t\t\tchiaki_feedback_history_event_set_touchpad(&event, false,')
s=replace(s,'\t\t\tchiaki_feedback_history_event_set_touchpad(&event, true,','\t\t\tif(state_prev->touches[i].id != state_now->touches[i].id)\n\t\t\t\tCHIAKI_LOGV(feedback_sender->log, "Touch history DOWN slot=%zu id=%d", i, state_now->touches[i].id);\n\t\t\tchiaki_feedback_history_event_set_touchpad(&event, true,')
save(p,s)

p='CMakeLists.txt';s=load(p)
s=replace(s,'set(CHIAKI_VERSION "${CHIAKI_VERSION_MAJOR}.${CHIAKI_VERSION_MINOR}.${CHIAKI_VERSION_PATCH}-ally-test.7")','''set(CHIAKI_VERSION "${CHIAKI_VERSION_MAJOR}.${CHIAKI_VERSION_MINOR}.${CHIAKI_VERSION_PATCH}-ally-test.8")
execute_process(COMMAND git rev-parse --short=12 HEAD
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    OUTPUT_VARIABLE CHIAKI_BUILD_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET RESULT_VARIABLE CHIAKI_GIT_RESULT)
if(CHIAKI_GIT_RESULT EQUAL 0)
    string(APPEND CHIAKI_VERSION "+g${CHIAKI_BUILD_COMMIT}")
endif()''');save(p,s)

p='.github/workflows/build-pr.yaml';s=load(p)
s=s[:s.index('\n  build-mac_arm64_github:')]
s=s[:s.index('\n      - name: Compile .ISS to .EXE Installer')]+ '\n'
s=replace(s,'jobs:\n','''permissions:
  contents: read
concurrency:
  group: ally-pr-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
''')
s=replace(s,'      contents: write','      contents: read')
s=replace(s,'          submodules: recursive','          submodules: recursive\n          ref: ${{ github.event.pull_request.head.sha }}')
s=replace(s,'      - name: Build libbplacebo','''      - name: Test touchscreen and feedback regressions
        run: |
          g++ -std=c++17 -Wall -Wextra -Werror -Igui/include tests/ally/touchscreenrouter_test.cpp -o touch-tests.exe
          ./touch-tests.exe
          python tests/ally/test_feedback_history.py

      - name: Build libbplacebo''')
s=replace(s,'          zip -r $RELEASE_PACKAGE_FILE chiaki-ng-Win','''          SOURCE_SHA="$(git rev-parse HEAD)"
          printf 'Source commit: %s\\nTest series: ally-test.8\\n' "$SOURCE_SHA" > chiaki-ng-Win/BUILD-INFO.txt
          sha256sum build/gui/chiaki.exe >> chiaki-ng-Win/BUILD-INFO.txt
          zip -r "$RELEASE_PACKAGE_FILE" chiaki-ng-Win''')
s=replace(s,'${{ github.sha }}.zip','${{ github.event.pull_request.head.sha }}.zip')
s=replace(s,'name: chiaki-ng-win_x64-MSYS2-Release-portable.zip','name: chiaki-ng-ally-${{ github.event.pull_request.head.sha }}-portable')
save(p,s)

for path,text in changes.items():
    Path(path).write_text(text,encoding='utf-8',newline='\n')
print('Applied source review to',len(changes),'files.')
