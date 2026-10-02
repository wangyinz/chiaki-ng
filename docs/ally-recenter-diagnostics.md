# Ally follow-up: menu-time motion reset and rumble diagnostics

Baseline: `d6e10330bfb7f0b6d6e387985ee490ab29ba684d`; tested installation reported `1.10.0-ally.1+gf62756d804d6`.

## Evidence and limits

The owner reports stable touchpad, corners and three-finger PS, but R2 still feels weaker. Opening the PS menu can briefly send the displayed controller spinning. The supplied session log contains repeated motion-origin resets and pre-mix PCM envelopes, but no verbose trigger-effect/mixer-output records. It cannot identify which motor/source caused the R2 difference or establish the raw IMU trajectory during a menu opening. Raw user logs are not included in this repository.

## Motion candidate

The existing Controller reset seeds a neutral reference, then re-enters the cold-start Madgwick warmup (`beta=20`, normal `beta=0.05`, first 30 samples). This is unnecessary after capturing a running sensor's neutral acceleration and amplifies small synthetic noise into a transient orientation oscillation.

Add a recenter API which seeds neutral pose, samples and timestamp exactly once, then starts with normal correction gain. Use it ONLY for a running ROG Ally profile; keep normal startup, non-Ally reset, sensor axis transform, timestamps, gyro rates, touch router and touch history unchanged. Invalid/nonfinite samples leave the previous state intact. This does not suppress gyro input for an arbitrary second and does not ignore the console's reset request.

The test compiles the actual orientation implementation with reduced data-type headers. A stationary synthetic input with 0.005g sinusoidal perturbations, zero gyro and 20ms update spacing yields about 46.59 degrees peak error on the old reset and about 0.074 degrees on the candidate. Tests also cover 5–35ms spacing, repeated recentering, timestamp wrap, invalid samples and continued response to real angular input. This is a numerical regression, NOT proof of the exact hardware cause or a measured Ally result.

## Rumble: no new strength or spatial-mapping assumptions

The installed fallback intentionally sends the strongest body/trigger envelope to BOTH low/high outputs. Thus bilateral vibration is consistent with the implemented compatibility downmix, not evidence that Sony L2 and R2 packets are being confused. It discards spatial localization; it does not prove the Ally hardware is incapable of independently driven output.

Do not add a fixed R2 gain or claim equal physical sensation. Preserve the mixer arithmetic and the saved experimental setting. Promote input-only trigger effect metadata and final mixer diagnostics to INFO (final output <=4Hz, including zero), log actual L2/R2 positions and label PCM-envelope records explicitly as PRE-MIX. The next hardware log can distinguish input/active-zone gating, body/classic contributions and final low/high output.

## Hardware validation

First leave the Ally stationary while opening/closing PS menu several times. Confirm neutral recenter without a transient wobble, then normal motion response. Next fully press L2 alone, release, and fully press R2 alone for about two seconds each, using the same in-game test. Capture the INFO records `Ally rumble input`, `Trigger effects`, `Ally motion reset result`, and `Haptic PCM envelope`.

Do not publish full protocol/verbose logs. Existing Windows CI builds an overwrite installer and portable archive with source-SHA identity without modifying the existing build workflow; the new motion regression is run separately during this review. Keep this candidate separate from main pending physical confirmation.
