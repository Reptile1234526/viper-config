#!/usr/bin/env python3
"""
Reactive lighting daemon — flashes the selected color on click then fades out.
Usage: python reactive_daemon.py <r> <g> <b> <speed>   (speed: 1=fast, 2=medium, 3=slow)

Writes PID to ~/.config/viper-config/reactive.pid
"""

import math
import os
import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from device import ViperMini

PID_FILE = Path.home() / ".config" / "viper-config" / "reactive.pid"

def main():
    args = sys.argv[1:]
    r, g, b = (int(args[i]) if i < len(args) else v
               for i, v in enumerate([130, 140, 248]))
    speed = int(args[3]) if len(args) > 3 else 2
    fade_secs = {1: 0.4, 2: 0.8, 3: 1.6}.get(speed, 0.8)

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))

    fade_lock = threading.Lock()

    def do_fade():
        """Open device, flash color, fade to black, then close."""
        with fade_lock:
            d = ViperMini()
            if not d.connect():
                return
            try:
                steps = 30
                for i in range(steps, -1, -1):
                    brightness = i / steps
                    d.set_static(
                        round(r * brightness),
                        round(g * brightness),
                        round(b * brightness),
                    )
                    time.sleep(fade_secs / steps)
            finally:
                d.disconnect()

    def on_click(x, y, button, pressed):
        nonlocal fade_thread
        if not pressed:
            return
        # Cancel ongoing fade and start a fresh one
        with fade_lock:
            t = threading.Thread(target=do_fade, daemon=True)
            fade_thread = t
        t.start()

    try:
        from pynput.mouse import Listener
        with Listener(on_click=on_click) as lst:
            lst.join()
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass

if __name__ == "__main__":
    main()
