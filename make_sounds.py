"""Makes the short sound files in sounds/. Run this on your computer:

    python make_sounds.py

Only Python's standard library is used, so the files are plain .wav. main.py
never imports this file or the wave module: it just loads the finished sounds.
"""

import array
import json
import math
import os
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sounds")


def load_config():
    with open(os.path.join(HERE, "data", "game.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)["sounds"]


def shape(kind, phase):
    if kind == "sine":
        return math.sin(phase)
    if kind == "square":
        return 0.6 if math.sin(phase) >= 0 else -0.6
    # saw: a ramp down once per cycle, good for an angry sound
    return 2.0 * (0.5 - (phase / (2.0 * math.pi)) % 1.0)


def note(rate, freq, seconds, kind="sine", volume=0.8, decay=2.0, to_freq=None):
    """One short tone that fades out, with a small fade in and out to stop clicks."""
    total = int(rate * seconds)
    out = []
    phase = 0.0
    for index in range(total):
        part = index / total if total else 0.0
        now = freq if to_freq is None else freq + (to_freq - freq) * part
        phase += 2.0 * math.pi * now / rate
        value = shape(kind, phase) * volume * math.exp(-decay * part * 4.0)
        edge = min(1.0, part * 40.0, (1.0 - part) * 40.0)
        out.append(value * edge)
    return out


def write(config, name, samples):
    path = os.path.join(OUT, config["files"][name])
    data = array.array("h", [int(max(-1.0, min(1.0, s)) * 32767) for s in samples])
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(config["sample_rate"])
        handle.writeframes(data.tobytes())
    return path


def main():
    config = load_config()
    rate = config["sample_rate"]
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    sounds = {
        "hit": note(rate, 620, 0.07, "square", volume=0.5, decay=4.0),
        "gem": note(rate, 880, 0.05, volume=0.5) + note(rate, 1320, 0.09, volume=0.5),
        "level": (note(rate, 660, 0.09, volume=0.6, decay=1.2)
                  + note(rate, 880, 0.09, volume=0.6, decay=1.2)
                  + note(rate, 1320, 0.16, volume=0.6, decay=1.0)),
        "hurt": note(rate, 200, 0.18, "saw", volume=0.7, decay=1.5, to_freq=110),
        "end": note(rate, 330, 0.25, volume=0.7, decay=1.0) + note(rate, 247, 0.4, volume=0.7, decay=1.0),
    }
    print("wrote %d sounds to sounds/ (%d Hz, mono):" % (len(sounds), rate))
    for name, samples in sounds.items():
        path = write(config, name, samples)
        print("  %-9s %d ms   %s" % (name, len(samples) * 1000 // rate, os.path.basename(path)))


if __name__ == "__main__":
    main()
