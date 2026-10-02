#!/usr/bin/env python3
"""Inspect a CHPCM001 raw haptics capture without changing channel balance."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
from collections import Counter
from pathlib import Path

HEADER = struct.Struct("<IQQI")
MAX_CAPTURE = 2 * 1024 * 1024


def analyze(path: Path) -> list[dict[str, object]]:
    if path.stat().st_size > MAX_CAPTURE:
        raise ValueError("Capture exceeds the bounded diagnostic format limit")
    data = path.read_bytes()
    if data[:8] != b"CHPCM001":
        raise ValueError("Not a CHPCM001 capture")

    rows: list[dict[str, object]] = []
    cursor = 8
    while cursor < len(data):
        if len(data) - cursor < HEADER.size:
            raise ValueError("Truncated record header")
        index, epoch_us, elapsed_us, size = HEADER.unpack_from(data, cursor)
        cursor += HEADER.size
        if index != len(rows) or not 0 < size <= 4096 or cursor + size > len(data):
            raise ValueError("Invalid, missing, or truncated record")
        raw = data[cursor:cursor + size]
        cursor += size

        row: dict[str, object] = {
            "index": index,
            "epoch_us": epoch_us,
            "elapsed_us": elapsed_us,
            "bytes": size,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "valid_s16le_stereo_length": size % 4 == 0,
        }
        if size % 4 == 0:
            samples = struct.unpack("<" + "h" * (size // 2), raw)
            for label, values in (("L", samples[0::2]), ("R", samples[1::2])):
                row[label + "_nonzero"] = sum(x != 0 for x in values)
                row[label + "_peak"] = max(abs(x) for x in values)
                row[label + "_rms"] = math.sqrt(
                    sum(x * x for x in values) / len(values))
                row[label + "_mean"] = sum(values) / len(values)
                row[label + "_legacy_envelope"] = min(
                    65535, 2 * sum(abs(x) for x in values) // len(values))
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()

    try:
        rows = analyze(args.capture)
        keys = list(dict.fromkeys(key for row in rows for key in row))
        with args.csv.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)
        print(json.dumps({
            "records": len(rows),
            "record_sizes": dict(Counter(row["bytes"] for row in rows)),
            "invalid_stereo_lengths": sum(
                not row["valid_s16le_stereo_length"] for row in rows),
            "interpretation": "S16LE interleaved audit; raw bytes remain authoritative",
        }, indent=2))
    except (OSError, ValueError, struct.error) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
