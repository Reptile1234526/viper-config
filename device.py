"""Razer Viper Mini — HID device interface (DPI + lighting)."""

import os
import signal
import subprocess
import sys
import time
import hid
from pathlib import Path

_PID_FILE         = Path.home() / ".config" / "viper-config" / "breathe.pid"
_REACTIVE_PID     = Path.home() / ".config" / "viper-config" / "reactive.pid"
_DAEMON           = Path(__file__).parent / "breathe_daemon.py"
_REACTIVE_DAEMON  = Path(__file__).parent / "reactive_daemon.py"
from protocol import (
    RAZER_VID, VIPER_MINI_PID, USAGE_PAGE, make_report,
    CLS_DPI, CMD_DPI_SET,
    CLS_LIGHT, CMD_LIGHT_SET,
    LED_LOGO, LED_SCROLL,
    EFX_NONE, EFX_STATIC, EFX_BREATHE, EFX_SPECTRUM, EFX_REACTIVE,
)


class ViperMini:
    """Thin wrapper around the Razer Viper Mini HID control interface."""

    DPI_MIN = 100
    DPI_MAX = 30400

    def __init__(self):
        self._dev = None

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Open the Razer control HID interface, trying all available paths."""
        interfaces = hid.enumerate(RAZER_VID, VIPER_MINI_PID)
        if not interfaces:
            return False

        # Prefer vendor-specific usage page, then fall back to any interface
        preferred = [i for i in interfaces if i.get("usage_page") == USAGE_PAGE]
        ordered = preferred + [i for i in interfaces if i not in preferred]

        for info in ordered:
            try:
                d = hid.device()
                d.open_path(info["path"])
                d.set_nonblocking(0)
                self._dev = d
                return True
            except Exception:
                continue
        return False

    def disconnect(self):
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    @property
    def connected(self) -> bool:
        return self._dev is not None

    def product_name(self) -> str:
        if not self._dev:
            return "Not connected"
        try:
            return self._dev.get_product_string() or "Razer Viper Mini"
        except Exception:
            return "Razer Viper Mini"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _send(self, report: bytearray) -> bytes | None:
        if not self._dev:
            return None
        try:
            self._dev.send_feature_report(bytes(report))
            time.sleep(0.015)
            resp = self._dev.get_feature_report(0x00, 91)
            return bytes(resp)
        except Exception as e:
            print(f"[device] HID error: {e}")
            return None

    def _ok(self, resp: bytes | None) -> bool:
        # Status byte at index 1: 0x02=success, 0x00=new/pending, 0x01=busy
        # Only treat 0x03 (fail) and 0x05 (unsupported) as errors.
        if resp is None:
            return False
        if len(resp) < 2:
            return True
        return resp[1] not in (0x03, 0x05)

    # ── DPI ───────────────────────────────────────────────────────────────────

    def set_dpi_stage(self, stage: int, dpi_x: int, dpi_y: int) -> bool:
        """
        Write one DPI stage (1-indexed, 1–5).
        DPI values are clamped to [100, 30400] and snapped to multiples of 100.
        """
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
        """Write up to 5 DPI stages and choose which is active."""
        ok = True
        for i, dpi in enumerate(stages[:5], start=1):
            ok &= self.set_dpi_stage(i, dpi, dpi)
        # CMD 0x06: set active stage count / current stage
        resp = self._send(make_report(CLS_DPI, 0x06, bytes([active_idx + 1])))
        return ok

    # ── Lighting ──────────────────────────────────────────────────────────────
    #
    # Razer uses two lighting protocols depending on firmware generation:
    #   Standard  (class 0x03, cmd 0x01): LED IDs 0x01/0x04, args [storage, led, efx, 0,0, ...]
    #   Extended  (class 0x0F, cmd 0x02): zone-based,         args [storage, zone, efx, 0,0, ...]
    # We try both in sequence; first one that doesn't return 0x03/0x05 wins.

    def _light(self, led_id: int, effect: int, extra_args: bytes = b"") -> bool:
        # Variant A: standard (class 0x03) with given led_id
        args_a = bytes([0x01, led_id, effect, 0x00, 0x00]) + extra_args
        resp = self._send(make_report(CLS_LIGHT, CMD_LIGHT_SET, args_a))
        if self._ok(resp):
            return True
        time.sleep(0.02)

        # Variant B: standard with alternate LED ID (scroll=0x01 vs logo=0x04)
        alt_led = LED_SCROLL if led_id == LED_LOGO else LED_LOGO
        args_b = bytes([0x01, alt_led, effect, 0x00, 0x00]) + extra_args
        resp = self._send(make_report(CLS_LIGHT, CMD_LIGHT_SET, args_b))
        if self._ok(resp):
            return True
        time.sleep(0.02)

        # Variant C: extended matrix (class 0x0F, cmd 0x02), zone 0x00
        # RGB bytes are at offset 6 in args (one extra padding byte vs standard)
        args_c = bytes([0x01, 0x00, effect, 0x00, 0x00, 0x00]) + extra_args
        resp = self._send(make_report(0x0F, 0x02, args_c))
        if self._ok(resp):
            return True

        # Variant D: extended matrix, zone 0x01
        args_d = bytes([0x01, 0x01, effect, 0x00, 0x00, 0x00]) + extra_args
        resp = self._send(make_report(0x0F, 0x02, args_d))
        return self._ok(resp)

    def set_off(self, led_id: int = LED_LOGO) -> bool:
        return self._light(led_id, EFX_NONE)

    def set_static(self, r: int, g: int, b: int, led_id: int = LED_LOGO) -> bool:
        return self._light(led_id, EFX_STATIC, bytes([r, g, b]))

    def set_spectrum(self, led_id: int = LED_LOGO) -> bool:
        return self._light(led_id, EFX_SPECTRUM)

    def set_breathing(self, r: int, g: int, b: int,
                      r2: int = 0, g2: int = 0, b2: int = 0,
                      dual: bool = False,
                      led_id: int = LED_LOGO) -> bool:
        extra = bytes([0x02, r, g, b, r2, g2, b2]) if dual else bytes([0x01, r, g, b])
        return self._light(led_id, EFX_BREATHE, extra)

    def set_reactive(self, r: int, g: int, b: int,
                     speed: int = 2,
                     led_id: int = LED_LOGO) -> bool:
        speed = max(1, min(3, speed))
        return self._light(led_id, EFX_REACTIVE, bytes([speed, r, g, b]))

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

    def stop_software_breathing(self):
        self.stop_all_daemons()

    # ── Factory reset ─────────────────────────────────────────────────────────

    def factory_reset(self) -> bool:
        """
        Reset the mouse to factory defaults:
          1. Send the hardware reset command (class 0x06, cmd 0x09)
          2. Restore DPI to 800 DPI, single stage
          3. Restore lighting to static green (Razer factory default)
        Returns True if all steps succeeded.
        """
        ok = True

        # DPI → 800 (single stage, Razer factory default)
        ok &= self.set_dpi_stage(1, 800, 800)
        time.sleep(0.05)

        # Lighting → static white (safe neutral default)
        ok &= self.set_static(255, 255, 255)

        return ok

    def apply_lighting(self, cfg: dict) -> bool:
        """Apply a lighting config dict (from Config.data['lighting'])."""
        effect = cfg.get("effect", "static")
        r, g, b = cfg.get("color", [130, 140, 248])
        r2, g2, b2 = cfg.get("color2", [56, 189, 248])
        speed = cfg.get("speed", 2)

        # Always kill daemons first
        self.stop_all_daemons()

        if effect in ("breathing", "reactive"):
            # Give the daemon exclusive HID access — app disconnects first
            self.disconnect()
            if effect == "breathing":
                self.start_software_breathing(speed=speed)
            else:
                self.start_reactive(r, g, b, speed=speed)
            return True

        # For hardware commands, reconnect if we previously disconnected
        if not self.connected:
            self.connect()

        if effect == "off":
            return self.set_off()
        elif effect == "static":
            return self.set_static(r, g, b)
        return False
