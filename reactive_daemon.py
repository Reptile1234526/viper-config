#!/usr/bin/env python3
"""
Reactive lighting daemon — LED on while any button held, off on release.
Uses Quartz button-state polling (no event tap, no accessibility needed).
Usage: python reactive_daemon.py <r> <g> <b>
"""

import os
import sys
import time
import hid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from protocol import RAZER_VID, VIPER_MINI_PID, USAGE_PAGE, make_report, EFX_STATIC

PID_FILE = Path.home() / ".config" / "viper-config" / "reactive.pid"


def _open_device():
    interfaces = hid.enumerate(RAZER_VID, VIPER_MINI_PID)
    preferred = [i for i in interfaces if i.get("usage_page") == USAGE_PAGE]
    for info in (preferred + [i for i in interfaces if i not in preferred]):
        try:
            d = hid.device()
            d.open_path(info["path"])
            d.set_nonblocking(0)
            return d
        except Exception:
            continue
    return None


def _send_static(dev, r: int, g: int, b: int):
    args = bytes([0x01, 0x00, EFX_STATIC, 0x00, 0x00, 0x00, r, g, b])
    try:
        dev.send_feature_report(bytes(make_report(0x0F, 0x02, args)))
        time.sleep(0.015)
        dev.get_feature_report(0x00, 91)
    except Exception:
        pass


def main():
    args_in = sys.argv[1:]
    r = int(args_in[0]) if len(args_in) > 0 else 130
    g = int(args_in[1]) if len(args_in) > 1 else 140
    b = int(args_in[2]) if len(args_in) > 2 else 248

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))

    try:
        import Quartz
    except ImportError:
        print("pyobjc-framework-Quartz not found")
        sys.exit(1)

    BUTTONS = [
        Quartz.kCGMouseButtonLeft,
        Quartz.kCGMouseButtonRight,
        Quartz.kCGMouseButtonCenter,
        3, 4,  # side buttons
    ]

    def any_pressed() -> bool:
        return any(
            Quartz.CGEventSourceButtonState(
                Quartz.kCGEventSourceStateCombinedSessionState, btn)
            for btn in BUTTONS
        )

    prev = False

    def send_once(rr, gg, bb):
        """Open device, send command multiple times to ensure it registers, close."""
        dev = _open_device()
        if dev:
            try:
                for _ in range(15):
                    _send_static(dev, rr, gg, bb)
            finally:
                try:
                    dev.close()
                except Exception:
                    pass

    try:
        while True:
            now = any_pressed()
            if now != prev:
                if now:
                    send_once(r, g, b)
                else:
                    send_once(0, 0, 0)
                prev = now
            time.sleep(0.005)
    finally:
        send_once(0, 0, 0)
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
