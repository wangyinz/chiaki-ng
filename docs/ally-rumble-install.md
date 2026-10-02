# Ally rumble source separation and in-place installation

Baseline: `04ee4182baf1044e45b133d714f0c7ec89e0d201` (test 9). User reports touchpad no longer sticks and gyro/corners/three-finger PS all work. Those input paths and the per-event feedback-history fix are retained without behavioral changes.

## Verified API distinction

1. Classic rumble events represent low/high-frequency motor magnitudes.
2. PS5 haptic PCM has left/right audio channels. They are not low/high-frequency bands.
3. DualSense adaptive-trigger effects configure L2/R2 actuators, independently of body haptics. Modes 0x21/0x25 are resistance/weapon effects, not ordinary body vibration. Only the opt-in 0x26 vibration approximation is supported here.

SDL explicitly documents that each SDL_GameControllerRumble call replaces the previous effect. The old Ally fallback sent L2 to the low-frequency motor and R2 to the high-frequency motor, and separate classic/PCM callbacks could overwrite each other. This did not provide symmetric L2/R2 feedback.

References (API facts/community protocol format, not claims of hardware equivalence):
- https://wiki.libsdl.org/SDL2/SDL_GameControllerRumble
- https://learn.microsoft.com/en-us/windows/win32/api/xinput/ns-xinput-xinput_vibration
- https://github.com/MysteriousJ/Joystick-Input-Examples/blob/main/README.md
- https://gist.github.com/Nielk1/6d54cc2c00d2201ccb8c2720ad7538db

## New Ally-only output

`allyrumble.h` preserves the three sources separately. Classic low/high remains distinct. Stereo haptic amplitudes are downmixed by peak envelope to a common low/high pair; this sacrifices spatial fidelity rather than incorrectly assigning the stereo channels to different-frequency actuators. L2 and R2 vibration use the same transfer function and the same output motor pair. A strongest-source mix avoids adding potentially duplicate descriptions of the same impact. A single GUI-thread writer publishes the combined result.

The opt-in trigger approximation retains the existing 50% cap, ignores unsupported/resistance modes and zero frequency, respects active zones and current trigger input, and has separate console trigger gain from body-haptic gain. Uniform ten-zone input thresholds are an approximation. We do not synthesize the requested DualSense frequency/waveform or adaptive resistance, and do not claim the Ally has independent trigger actuators. Swapping identical L2/R2 effects gives identical output commands. Different game-provided haptic audio/effects can still feel different; subjective equality has not been hardware-verified for this change.

Real DualSense native effect forwarding is retained. The experimental setting's saved value is preserved (leave it enabled for trigger-to-body vibration). Classic rumble does not require it. Stop/disconnect clears the Ally mixer, and Ally rumble commands use a short renewable 100 ms lease.

Tests cover isolated body vs trigger gain/off, unsupported/zero-frequency modes, active-zone input, source stop events, expiry, saturation and 10,000 deterministic mirrored L2/R2 cases. Existing touch/history tests still run. Touch router, gesture adapter and feedback sender are source-checked unchanged.

## Installer / CI

The same Windows-only workflow runs on PRs, main pushes and manual dispatch. It produces both a portable ZIP and an Inno Setup EXE, with source SHA, BUILD-INFO.txt and SHA256SUMS.txt. No extra platform jobs or automatic release publication are enabled. Version label: 1.10.0-ally.1+g<source SHA>; upstream numeric version remains 1.10.0.

Keep the upstream AppId `{A329DCDE-074D-4C82-959A-3CFAC9A26B1F}` so an existing installation in the same scope is detected. Reuse its directory/privileges, request normal application closure (not forced termination), and replace private application files with ignoreversion. There is no user-settings deletion. Close chiaki-ng before installing and review the selected directory. A portable extraction has no installer registration, so select the intended target yourself; per-user and all-users installs are different scopes. Back up important settings before changing installation scope.

CI installs the generated EXE into an isolated per-user directory, saves AppData/registry sentinels, substitutes an old binary marker, and installs again without /DIR. It checks previous directory reuse, binary replacement and untouched sentinels. This is an installer smoke test, not every possible existing Windows installation. Installer is unsigned unless signing is configured separately; do not bypass security warnings from unrelated binaries.
