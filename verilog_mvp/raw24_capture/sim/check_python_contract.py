"""Independent Python-side golden vector for the RAW24 FPGA testbench."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from raspberry_mvp.raw24_diagnostic.safe_field_raw24_protocol import (
    Raw24Frame,
    encode_frame,
    pcm16_gain8,
)


RAW24_VALUES = (
    -8_388_608,
    -1_048_576,
    -8_389,
    -32,
    -1,
    0,
    1,
    31,
    32,
    839,
    26_527,
    265_271,
    1_048_575,
    4_204_263,
    8_388_606,
    8_388_607,
)

frame = Raw24Frame(
    seq=0,
    first_source_sample_counter=0,
    stride=2,
    flags=0x24,
    raw24_samples=RAW24_VALUES,
    pcm16_samples=tuple(pcm16_gain8(value) for value in RAW24_VALUES),
)
encoded = encode_frame(frame)

assert len(encoded) == 95
assert encoded[:13].hex().upper() == "A5C40121000000000000100224"
assert encoded[-2:].hex().upper() == "B969"
assert int.from_bytes(encoded[-2:], "little") == 0x69B9

print("TEST_RESULT: PASS (Python parser golden vector matches RTL TB)")
print(f"frame_bytes={len(encoded)}")
print(f"header={encoded[:13].hex().upper()}")
print(f"crc_wire={encoded[-2:].hex().upper()}")
print(f"crc_numeric={int.from_bytes(encoded[-2:], 'little'):04X}")
print(f"frame_sha256={hashlib.sha256(encoded).hexdigest().upper()}")
