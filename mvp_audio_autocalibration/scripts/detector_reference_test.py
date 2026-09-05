#!/usr/bin/env python3
"""Self-checking old-vs-new detector model used before physical deployment."""

from collections import deque


def old_detector(values, on=1000, off=500, attack=4, release=4):
    active = False
    a = r = 0
    states = []
    for value in values:
        if not active:
            r = 0
            a = a + 1 if value >= on else 0
            if a >= attack:
                active, a = True, 0
        else:
            a = 0
            r = r + 1 if value <= off else 0
            if r >= release:
                active, r = False, 0
        states.append(active)
    return states


def new_detector(values, on=1000, off=500, k=3, n=5, attack=1,
                 release=2, hangover=3):
    active = False
    history = deque([False] * n, maxlen=n)
    a = r = h = 0
    states = []
    for value in values:
        history.append(value >= on)
        votes = sum(history)
        if not active:
            r = h = 0
            a = a + 1 if votes else 0
            if votes >= k and a >= attack:
                active, a = True, 0
        else:
            a = 0
            if value > off:
                r = h = 0
            elif r < release:
                r += 1
                h = 0
            elif h < hangover:
                h += 1
            else:
                active, r, h = False, 0, 0
                history = deque([False] * n, maxlen=n)
        states.append(active)
    return states


def main():
    silence = [100] * 12
    speech_with_gaps = [1500, 100, 1600, 200, 1700, 100, 1400, 100]
    tail = [100] * 8
    values = silence + speech_with_gaps + tail
    old = old_detector(values)
    new = new_detector(values)
    checks = {
        "old_misses_nonconsecutive_speech": not any(old),
        "new_detects_nonconsecutive_speech": any(new[12:20]),
        "new_has_no_silence_false_active": not any(new[:12]),
        "new_returns_quiet": not new[-1],
        "new_single_active_event": sum(a != b for a, b in zip([False] + new, new)) == 2,
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
