# Ally raw haptics capture

This diagnostic records the haptics payload that reaches
`StreamSession::PushHapticsFrame()` before envelope extraction or motor mixing.
It does not change rumble gains, trigger conversion, touch input, or gyro.

The capture is disabled by default. To enable it for one run on Windows, fully
quit chiaki-ng, choose a new output file, then launch the diagnostic build:

```powershell
$env:CHIAKI_HAPTICS_CAPTURE = "$env:USERPROFILE\Desktop\ally-haptics-raw.chpcm"
& "C:\Path\To\chiaki.exe"
```

The file must not already exist and its parent directory must already exist.
Capture is bounded to 4096 records, 4096 bytes per record, and 512 KiB of raw
payload. The ordinary session log contains only structural packet/frame
metadata when this environment variable is set.

After reproducing the issue, quit the stream and convert the capture to CSV:

```powershell
python .\scripts\analyze-ally-haptics.py "$env:USERPROFILE\Desktop\ally-haptics-raw.chpcm" --csv "$env:USERPROFILE\Desktop\ally-haptics-raw.csv"
Remove-Item Env:\CHIAKI_HAPTICS_CAPTURE
```

CHPCM001 stores each delivered raw payload unchanged, together with a monotonic
elapsed timestamp and wall-clock timestamp. The analyzer reports per-channel
S16LE statistics for comparison with the existing pre-mix/body diagnostics.
The raw bytes remain the authoritative diagnostic artifact; the analyzer does
not auto-swap channels or guess another sample format.

Treat the capture and session log as private diagnostic data. Do not publish a
full verbose session log because other protocol logging can contain credentials
or identifiers unrelated to haptics.
