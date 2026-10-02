# Ally input review (test series 8)

Baseline reviewed: `7c92ab67d74d2bcef69814e51d9c8b54f3b16679` on `fix/rog-ally-input`.

## Touchscreen configuration

In **Settings > Controllers > Touchscreen / Corner Buttons**, set each corner independently. All four default to **Original behavior**. For a touchscreen PS button, set **Top right = PS**. Any Chiaki digital button can be selected (PS, Touchpad Click, Options, Share, face buttons, shoulder buttons, stick clicks, or D-pad). These settings are saved per application settings profile and take effect on the next stream.

Corner size defaults to 8% of window width and height, adjustable from 3% to 20%. Only configured corners capture input. Unconfigured corners and the rest of the screen continue to supply touchpad coordinates. The **Original edge touchpad click** option defaults ON and retains the upstream 5% border behavior: touch coordinates AND the touchpad button are sent. A configured corner takes priority over this edge behavior.

Ownership is chosen when a finger lands. A finger beginning in a mapped corner stays a button until released, even when dragged away. A normal swipe passing through that corner does not unexpectedly press PS. Multiple fingers mapped to the same button are combined: releasing one does not release another finger's hold.

**Three-finger tap for PS** remains available and defaults ON outside mapped corners. On the third contact, the router releases its touchpad slots and suppresses the remainder of that sequence. PS is pressed only once all fingers are lifted. Cancellation or focus loss aborts the gesture. The application no longer uses uncancellable delayed press callbacks.

**Double-tap gap** defaults to 650 ms, configurable from 200 to 1000 ms. This is the time from the first release to the second press. A tap must take at most 400 ms and move no more than 7% of the shorter window dimension; two taps may be separated by up to 18% of that dimension. Maximum travel is measured throughout the stroke, so an out-and-back swipe is not a tap. Any multi-touch sequence is excluded from tap recognition. The second press supplies a touchpad click, supports holding, and has a minimum 100 ms pulse for quick taps. Edge clicks and corner holds cannot be released by another gesture's timer.

## Confirmed review findings

- Earlier `std::clamp(0, coordinate, maximum)` calls had reversed argument roles; coordinates outside the window could violate clamp's bounds precondition. The router clamps `coordinate / size` between 0 and 1 and rejects non-finite/zero dimensions. Protocol coordinates stop at size minus one.
- Earlier tap recognition used the number of remaining allocated slots rather than the history of the physical sequence. The final finger of a multi-touch could be misclassified as a tap.
- Delayed lambdas could press a button after cancellation or release a different source's hold. A single deadline-driven state machine replaces those callbacks and is reset on cancellation, input blocking, focus loss and session stop.
- `feedback_sender_record_history()` used an `else if`: replacing a live touch ID in one slot emitted old-UP but omitted new-DOWN. The two conditions are now independent and covered by an isolated test of that production function.
- The original edge behavior did not exclude touch coordinates. Removing it was not justified by a report of a dead zone. It is restored by default, with explicit corner overrides.
- Synthesized mouse events were already filtered in the window. Disabling a user's real mouse globally for the Ally profile was unnecessary; that change is removed, and synthesized mouse double-clicks are filtered too.
- The rumble queue now retains silence, is bounded, and avoids iterating GUI-owned controllers from the decoder callback. Full-scale PCM amplitude is saturated rather than wrapping when narrowed to 16 bits.

These findings do **not** prove a single complete cause for the reported PS5-side stuck contact. Touch routing and touch-history DOWN/UP transitions have verbose diagnostics to distinguish local state errors from later transmission/console behavior. Do not publish raw verbose session logs: protocol dumps may contain identifying or authentication information even when some lines are sanitized.

## Motion and vibration limitations

This review deliberately does not guess another gyro matrix. The prior `(-Z, Y, X)` experimental transform remains; it is not presented as validated RC71L calibration. Hardware testing is still required, as is verification of the Xbox-identity detection heuristic on other devices.

**Experimental Ally trigger-to-rumble approximation** defaults OFF. It can be enabled for testing the existing 0x26 conversion. An unpressed trigger is now gated off. This is not a simulation of physical adaptive trigger resistance or a verified reconstruction of the DualSense waveform. SDL rumble components describe low/high-frequency output; they are not a portable guarantee of independently addressable physical left/right motors.

## Regression checks and build identity

Run the dependency-light tests from the repository root:

```sh
g++ -std=c++17 -Wall -Wextra -Werror -Igui/include tests/ally/touchscreenrouter_test.cpp -o /tmp/touch-tests
/tmp/touch-tests
python3 tests/ally/test_feedback_history.py
```

The router suite covers all four corners and all screen edges, corner capture, shared button ownership, quick and held double taps, multi-touch tap exclusion, all six three-finger release orders, cancellation, slot replacement, live ID wrap, invalid geometry, lost sequence recovery and 10,000 deterministic randomized sequences. The history test compiles the actual production history-recording function with isolated transport stubs. These tests are not an end-to-end PS5 test.

PR CI runs those checks before the Windows build and produces a portable ZIP only. Superseded PR runs are cancelled. The UI/log version includes the checked-out source commit; artifact names contain the full PR head SHA, and `BUILD-INFO.txt` records it with the executable checksum. CPack's numeric version remains separate.
