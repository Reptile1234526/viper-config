#!/usr/bin/env python3
"""
Rainbow breathing daemon — runs independently of the main app.
Usage: python breathe_daemon.py <speed>   (speed: 1=fast, 2=medium, 3=slow)

Writes its PID to ~/.config/viper-config/breathe.pid so the app can stop it.
"""

import math
import os
import sys
import time
from pathlib import Path

# Allow running from any working directory
sys.path.insert(0, str(Path(__file__).parent))

from device import ViperMini

PID_FILE = Path.home() / ".config" / "viper-config" / "breathe.pid"

def main():
    speed = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    cycle_secs = {1: 2.0, 2: 4.0, 3: 8.0}.get(speed, 4.0)
    hue_cycle = cycle_secs * 2

    d = ViperMini()
    if not d.connect():
        sys.exit(1)

    # Write PID so the app can kill us later
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))

    fps = 30
    interval = 1.0 / fps

    try:
        while True:
            t = time.monotonic()

            phase = (t % cycle_secs) / cycle_secs
            brightness = (1 - math.cos(phase * 2 * math.pi)) / 2

            hue = (t % hue_cycle) / hue_cycle
            h = hue * 6
            x = 1 - abs(h % 2 - 1)
            if   h < 1: rv, gv, bv = 1, x, 0
            elif h < 2: rv, gv, bv = x, 1, 0
            elif h < 3: rv, gv, bv = 0, 1, x
            elif h < 4: rv, gv, bv = 0, x, 1
            elif h < 5: rv, gv, bv = x, 0, 1
            else:        rv, gv, bv = 1, 0, x

            r = round(rv * brightness * 255)
            g = round(gv * brightness * 255)
            b = round(bv * brightness * 255)

            d.set_static(r, g, b)
            time.sleep(interval)
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass

if __name__ == "__main__":
    main()
