"""Razer Viper Mini — HID device interface (DPI + lighting).

The device is opened only for the duration of each command, then immediately
closed. This prevents conflicts with background daemons that also need access.
"""

import os
import signal
import subprocess
import sys
import time
import hid
from pathlib import Path

from protocol import (
    RAZER_VID, VIPER_MINI_PID, USAGE_PAGE, make_report,
    CLS_DPI, CMD_DPI_SET,
    CLS_LIGHT, CMD_LIGHT_SET,
    LED_LOGO, LED_SCROLL,
    EFX_NONE, EFX_STATIC, EFX_BREATHE, EFX_SPECTRUM, EFX_REACTIVE,
)

_PID_FILE        = Path.home() / ".config" / "viper-config" / "breathe.pid"
_REACTIVE_PID    = Path.home() / ".config" / "viper-config" / "reactive.pid"
_DAEMON          = Path(__file__).parent / "breathe_daemon.py"
_REACTIVE_DAEMON = Path(__file__).parent / "reactive_daemon.py"


def _daemon_running() -> bool:
    """Return True if a breathing or reactive daemon is currently running."""
    for pf in (_PID_FILE, _REACTIVE_PID):
        try:
            if pf.exists():
                pid = int(pf.read_text().strip())
                os.kill(pid, 0)   # signal 0 = just check existence
                return True
        except (ProcessLookupError, ValueError, OSError):
            pass
    return False


class ViperMini:
    """Razer Viper Mini interface — opens the HID device per command only."""

    DPI_MIN = 100
    DPI_MAX = 30400

    # ── Device presence ───────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        """True if the device is enumerable (does NOT open it)."""
        return bool(hid.enumerate(RAZER_VID, VIPER_MINI_PID))

    def product_name(self) -> str:
        return "Razer Viper Mini" if self.connected else "Not connected"

    # ── Legacy stubs (kept so GUI code still compiles) ────────────────────────

    def connect(self) -> bool:
        return self.connected

    def disconnect(self):
        pass  # nothing to close — we don't hold the device open

    # ── Internal: open → send → close ────────────────────────────────────────

    def _send(self, report: bytearray) -> bytes | None:
        """Open the device, send one feature report, read response, close."""
        interfaces = hid.enumerate(RAZER_VID, VIPER_MINI_PID)
        if not interfaces:
            return None

        preferred = [i for i in interfaces if i.get("usage_page") == USAGE_PAGE]
        ordered = preferred + [i for i in interfaces if i not in preferred]

        for info in ordered:
            d = hid.device()
            try:
                d.open_path(info["path"])
                d.set_nonblocking(0)
                d.send_feature_report(bytes(report))
                time.sleep(0.015)
                resp = bytes(d.get_feature_report(0x00, 91))
                return resp
            except Exception:
                continue
            finally:
                try:
                    d.close()
                except Exception:
                    pass
        return None

    def _ok(self, resp: bytes | None) -> bool:
        if resp is None:
            return False
        if len(resp) < 2:
            return True
        return resp[1] not in (0x03, 0x05)

    # ── DPI ───────────────────────────────────────────────────────────────────

    def set_dpi_stage(self, stage: int, dpi_x: int, dpi_y: int) -> bool:
        dpi_x = max(self.DPI_MIN, min(self.DPI_MAX, round(dpi_x / 100) * 100))
        dpi_y = max(self.DPI_MIN, min(self.DPI_MAX, round(dpi_y / 100) * 100))
        args = bytes([
            stage & 0xFF,
            (dpi_x >> 8) & 0xFF, dpi_x & 0xFF,
            (dpi_y >> 8) & 0xFF, dpi_y & 0xFF,
            0x00,
        ])
        return self._ok(self._send(make_report(CLS_DPI, CMD_DPI_SET, args)))

    def apply_dpi_stages(self, stages: list[int], active_idx: int = 0) -> bool:
        ok = True
        for i, dpi in enumerate(stages[:5], start=1):
            ok &= self.set_dpi_stage(i, dpi, dpi)
        self._send(make_report(CLS_DPI, 0x06, bytes([active_idx + 1])))
        return ok

    # ── Lighting ──────────────────────────────────────────────────────────────

    def _light(self, led_id: int, effect: int, extra_args: bytes = b"") -> bool:
        # Variant A: standard (class 0x03, cmd 0x01)
        args_a = bytes([0x01, led_id, effect, 0x00, 0x00]) + extra_args
        if self._ok(self._send(make_report(CLS_LIGHT, CMD_LIGHT_SET, args_a))):
            return True
        time.sleep(0.02)

        # Variant B: alternate LED ID
        alt = LED_SCROLL if led_id == LED_LOGO else LED_LOGO
        args_b = bytes([0x01, alt, effect, 0x00, 0x00]) + extra_args
        if self._ok(self._send(make_report(CLS_LIGHT, CMD_LIGHT_SET, args_b))):
            return True
        time.sleep(0.02)

        # Variant C: extended matrix (class 0x0F, cmd 0x02), extra padding byte
        args_c = bytes([0x01, 0x00, effect, 0x00, 0x00, 0x00]) + extra_args
        if self._ok(self._send(make_report(0x0F, 0x02, args_c))):
            return True

        # Variant D: extended matrix, zone 0x01
        args_d = bytes([0x01, 0x01, effect, 0x00, 0x00, 0x00]) + extra_args
        return self._ok(self._send(make_report(0x0F, 0x02, args_d)))

    def set_off(self, led_id: int = LED_LOGO) -> bool:
        return self._light(led_id, EFX_NONE)

    def set_static(self, r: int, g: int, b: int, led_id: int = LED_LOGO) -> bool:
        return self._light(led_id, EFX_STATIC, bytes([r, g, b]))

    def set_spectrum(self, led_id: int = LED_LOGO) -> bool:
        return self._light(led_id, EFX_SPECTRUM)

    def set_breathing(self, r, g, b, r2=0, g2=0, b2=0,
                      dual=False, led_id=LED_LOGO) -> bool:
        extra = bytes([0x02, r, g, b, r2, g2, b2]) if dual else bytes([0x01, r, g, b])
        return self._light(led_id, EFX_BREATHE, extra)

    def set_reactive(self, r, g, b, speed=2, led_id=LED_LOGO) -> bool:
        return self._light(led_id, EFX_REACTIVE, bytes([max(1, min(3, speed)), r, g, b]))

    # ── Daemons ───────────────────────────────────────────────────────────────

    def _kill_pid_file(self, pid_file: Path):
        try:
            if pid_file.exists():
                pid = int(pid_file.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                pid_file.unlink(missing_ok=True)
        except (ProcessLookupError, ValueError, OSError):
            pass

    def stop_all_daemons(self):
        self._kill_pid_file(_PID_FILE)
        self._kill_pid_file(_REACTIVE_PID)
        time.sleep(0.15)   # wait for daemons to release the device

    def stop_software_breathing(self):
        self.stop_all_daemons()

    def start_software_breathing(self, speed: int = 2):
        self.stop_all_daemons()
        subprocess.Popen(
            [sys.executable, str(_DAEMON), str(speed)],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def start_reactive(self, r: int, g: int, b: int, speed: int = 2):
        self.stop_all_daemons()
        subprocess.Popen(
            [sys.executable, str(_REACTIVE_DAEMON),
             str(r), str(g), str(b), str(speed)],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # ── Lighting apply ────────────────────────────────────────────────────────

    def apply_lighting(self, cfg: dict) -> bool:
        effect = cfg.get("effect", "static")
        r, g, b   = cfg.get("color",  [130, 140, 248])
        r2, g2, b2 = cfg.get("color2", [56, 189, 248])
        speed     = cfg.get("speed", 2)

        self.stop_all_daemons()   # kills daemons and waits 150ms for device release

        if effect == "breathing":
            self.start_software_breathing(speed=speed)
            return True
        elif effect == "reactive":
            self.start_reactive(r, g, b, speed=speed)
            return True
        elif effect == "off":
            return self.set_off()
        elif effect == "static":
            return self.set_static(r, g, b)
        return False

    # ── Factory reset ─────────────────────────────────────────────────────────

    def factory_reset(self) -> bool:
        self.stop_all_daemons()
        ok = self.set_dpi_stage(1, 800, 800)
        time.sleep(0.05)
        ok &= self.set_static(255, 255, 255)
        return ok
