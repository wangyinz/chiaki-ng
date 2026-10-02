# Touch history investigation (test series 9)

## Scope

Baseline: `f9a3cadc08a81f92fb334ec8bf1391a80a45a334` (test series 8).
The user reports that gyro, corner mappings and three-finger PS work, but touchpad contacts still stick while those buttons continue to work. These are hardware observations, not observations from a newly uploaded test-8 log.

Freeze the touchscreen router, corner ownership, edge-click behavior, gesture timing, gyro transform and haptic output code for this iteration. The experimental trigger-to-rumble option remains unchanged and OFF by default; the user can retain their enabled setting. Left/right subjective strength remains an unresolved, separate issue.

## Confirmed source difference and candidate correction

At baseline, `feedback_sender_record_history()` records all changed touch/button events from one state update and `chiaki_feedback_sender_set_controller_state()` flushes them once. A simultaneous two-contact release plus PS press becomes one queued packet with three new events and only one sequence increment.

The earlier upstream implementation at `streetpea/chiaki-ng` commit `a16b712b70fd13ce6ec3892b4b2316b7c8b0e578`, before history batching, called `feedback_sender_send_history_packet()` immediately after each event was appended. Restore that one-new-event-per-history-snapshot convention, while retaining the newer asynchronous sending queue and the previously fixed old-UP/new-DOWN handling.

Each snapshot now receives its sequence number while it is enqueued. A full local queue can still drop the oldest snapshot, but must not renumber the surviving snapshots to hide the gap. Actual socket send errors are reported rather than ignored. The retained recent-event tail is unchanged.

This is a source-grounded candidate for the PS5-side stuck contacts, not proof that the reported physical failure has been fixed. The local tests do not emulate a PlayStation receiver or network delivery. In particular, logging a touch-UP or a successful local send does not establish that the console applied it.

## Regression evidence

The previous test stubbed history buffer pushes and only checked that events were generated. It did not check serialization, packet boundaries, sequence numbers or the send wrapper.

The expanded `tests/ally/test_feedback_history.py` extracts the production history functions, the production serializers and ring-buffer functions. Platform types/logging and the transport boundary are isolated. It checks two-UP-plus-PS, edge-touch plus Touchpad Click, live slot replacement, simultaneous changes exceeding the ring's size, sequence wrap, bounded-queue overflow with preserved sequence gaps and 2,000 deterministic multi-contact transitions.

Local result against the baseline source:

```
two UP + PS: queued=1 (expected 3)
FAIL: s.history_packet_len==3
```

Local result against the candidate:

```
two UP + PS: queued=3 (expected 3)
Production history packet regressions passed (including 2,000 multi-contact transitions).
```

The candidate also passed the isolated tests with `-fsanitize=address,undefined -g`. Full Windows compilation and physical Ally/PS5 validation are separate checks.

To reproduce the negative control after checkout:

```sh
git show f9a3cadc08a81f92fb334ec8bf1391a80a45a334:lib/src/feedbacksender.c > /tmp/feedbacksender-before.c
python3 tests/ally/test_feedback_history.py --sender-source /tmp/feedbacksender-before.c
# Expected failure at the first packet-boundary assertion.
python3 tests/ally/test_feedback_history.py
```

## Hardware test and input-only diagnostics

Keep existing mappings, gyro and vibration settings. Reconnect for a new test-9 session. Test two fingers lifting together and alternately, a normal edge touch/release, a configured corner, and three-finger PS followed by a fresh single-finger swipe. Record the time when a contact sticks and lift all fingers for two seconds before the next action.

Enable Verbose Logging only for the short diagnostic session. Relevant records are:

- `Touchscreen routed buttons=... slots=...` (local router state).
- `Touch history DOWN/UP slot=... id=...` (generated contact transition).
- `Feedback history send seq=... bytes=... newest=... id_or_code=... result=...` (transport call result, NOT a console acknowledgement).
- `Feedback Sender history packet queue overflow` and formatting/send errors.

Do not publish a complete verbose log: unrelated protocol dumps can contain authentication material even with partial sanitization. Extract only the diagnostic lines, for example in PowerShell, replacing the path with the actual new session log:

```powershell
$path = 'C:\path\to\chiaki_session.log'
Get-Content -LiteralPath $path |
    Where-Object { $_ -match '\] \[[VIWE]\] (Chiaki Version|Controller .*opened:|Touchscreen routed|Touch history|Feedback history|Feedback Sender)' } |
    Set-Content -Encoding utf8 -LiteralPath '.\chiaki-touch-only.log'
```
