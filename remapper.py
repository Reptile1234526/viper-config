"""
Software button remapper + macro engine for macOS.

Uses a Quartz CGEventTap (requires Accessibility permission) to intercept
mouse button events and optionally suppress them, then plays back the
configured action (keyboard shortcut, macro, or alternative mouse button).

If Quartz/pyobjc is not available, falls back to pynput listen-only mode
(macros fire but the original button press also fires).
"""

import threading
import time
import uuid
from config import Config

# ── Quartz event tap ──────────────────────────────────────────────────────────

try:
    import Quartz
    _QUARTZ = True
except ImportError:
    _QUARTZ = False
    print("[remapper] pyobjc-framework-Quartz not found — falling back to pynput")

# pynput used for keyboard/mouse simulation inside macro playback
try:
    from pynput.keyboard import Controller as _KbCtrl, Key as _Key, KeyCode as _KeyCode
    from pynput.mouse import Controller as _MouseCtrl, Button as _Button
    _PYNPUT = True
except ImportError:
    _PYNPUT = False
    print("[remapper] pynput not found — key/mouse simulation unavailable")


# ── Button number constants (CGEvent) ─────────────────────────────────────────
BTN_MIDDLE  = 2   # scroll-wheel click
BTN_BACK    = 3   # X1 / side-back
BTN_FORWARD = 4   # X2 / side-forward

BUTTON_NAMES = {
    BTN_MIDDLE:  "Middle Click",
    BTN_BACK:    "Side Back (X1)",
    BTN_FORWARD: "Side Forward (X2)",
}


# ── Keyboard simulation helpers ───────────────────────────────────────────────

def _parse_combo(combo: str):
    """
    Parse "cmd+c", "ctrl+shift+z", "f5", etc.
    Returns (list_of_modifier_Keys, main_key_or_None).
    """
    if not _PYNPUT:
        return [], None

    _MOD_MAP = {
        "cmd": _Key.cmd, "command": _Key.cmd,
        "ctrl": _Key.ctrl, "control": _Key.ctrl,
        "shift": _Key.shift,
        "alt": _Key.alt, "option": _Key.alt,
        "win": _Key.cmd,
    }
    _KEY_MAP = {
        "space": _Key.space, "return": _Key.enter, "enter": _Key.enter,
        "tab": _Key.tab, "esc": _Key.esc, "escape": _Key.esc,
        "backspace": _Key.backspace, "delete": _Key.delete,
        "up": _Key.up, "down": _Key.down, "left": _Key.left, "right": _Key.right,
        "home": _Key.home, "end": _Key.end,
        "pageup": _Key.page_up, "pagedown": _Key.page_down,
        "f1": _Key.f1, "f2": _Key.f2, "f3": _Key.f3, "f4": _Key.f4,
        "f5": _Key.f5, "f6": _Key.f6, "f7": _Key.f7, "f8": _Key.f8,
        "f9": _Key.f9, "f10": _Key.f10, "f11": _Key.f11, "f12": _Key.f12,
        "media_play_pause": _Key.media_play_pause,
        "media_next": _Key.media_next,
        "media_previous": _Key.media_previous,
        "media_volume_up": _Key.media_volume_up,
        "media_volume_down": _Key.media_volume_down,
        "media_volume_mute": _Key.media_volume_mute,
    }

    modifiers, main_key = [], None
    for part in combo.lower().split("+"):
        part = part.strip()
        if part in _MOD_MAP:
            modifiers.append(_MOD_MAP[part])
        elif part in _KEY_MAP:
            main_key = _KEY_MAP[part]
        elif len(part) == 1:
            main_key = _KeyCode.from_char(part)
    return modifiers, main_key


def press_combo(combo: str):
    """Simulate a key combo like 'cmd+c'."""
    if not _PYNPUT:
        return
    kb = _KbCtrl()
    modifiers, main_key = _parse_combo(combo)
    for m in modifiers:
        kb.press(m)
    if main_key:
        kb.press(main_key)
        kb.release(main_key)
    for m in reversed(modifiers):
        kb.release(m)


def click_mouse_btn(button_name: str):
    """Simulate a mouse button click by name (left/right/middle/back/forward)."""
    if not _PYNPUT:
        return
    _MAP = {
        "left": _Button.left, "right": _Button.right,
        "middle": _Button.middle,
        "back": _Button.x1, "forward": _Button.x2,
    }
    btn = _MAP.get(button_name, _Button.left)
    m = _MouseCtrl()
    m.press(btn)
    m.release(btn)


def play_macro(steps: list[dict]):
    """Execute macro steps (runs in the calling thread — call from a daemon thread)."""
    if not _PYNPUT:
        return
    kb = _KbCtrl()
    for step in steps:
        t = step.get("type")
        if t == "delay":
            time.sleep(step.get("ms", 50) / 1000.0)
        elif t == "key_press":
            press_combo(step.get("key", ""))
        elif t == "type_text":
            kb.type(step.get("text", ""))
        elif t == "mouse_click":
            click_mouse_btn(step.get("button", "left"))


# ── Remapper ──────────────────────────────────────────────────────────────────

class ButtonRemapper:
    """
    Intercepts mouse button events on macOS and dispatches configured actions.

    Usage:
        r = ButtonRemapper(config)
        r.start()
        ...
        r.stop()
    """

    def __init__(self, config: Config):
        self.config = config
        self._thread: threading.Thread | None = None
        self._run_loop_ref = None
        self._tap = None
        self._running = False

    @staticmethod
    def accessibility_ok() -> bool:
        if not _QUARTZ:
            return False
        try:
            from ApplicationServices import AXIsProcessTrusted
            return bool(AXIsProcessTrusted())
        except Exception:
            pass
        try:
            return bool(Quartz.AXIsProcessTrusted())
        except Exception:
            return False

    @staticmethod
    def request_accessibility():
        """Prompt the system accessibility-permission dialog."""
        if not _QUARTZ:
            return
        try:
            from ApplicationServices import (
                AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt)
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        except Exception:
            pass

    def start(self):
        if self._running:
            return
        self._running = True
        if _QUARTZ:
            self._thread = threading.Thread(target=self._run_quartz, daemon=True)
        else:
            self._thread = threading.Thread(target=self._run_pynput, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if _QUARTZ and self._run_loop_ref:
            try:
                Quartz.CFRunLoopStop(self._run_loop_ref)
            except Exception:
                pass

    # ── Quartz path ───────────────────────────────────────────────────────────

    def _run_quartz(self):
        event_mask = (
            (1 << Quartz.kCGEventOtherMouseDown) |
            (1 << Quartz.kCGEventOtherMouseUp)
        )

        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGHIDEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,   # active — can suppress
            event_mask,
            self._quartz_cb,
            None,
        )

        if not self._tap:
            print("[remapper] CGEventTapCreate failed — grant Accessibility access and restart.")
            return

        src = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._run_loop_ref = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(
            self._run_loop_ref, src, Quartz.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(self._tap, True)
        Quartz.CFRunLoopRun()  # blocks until stop() is called

    def _quartz_cb(self, proxy, event_type, event, refcon):
        btn = int(Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGMouseEventButtonNumber
        ))
        action = self.config.button_action(btn)
        action_type = action.get("type", "default")

        if action_type == "default":
            return event  # pass through unchanged

        if event_type == Quartz.kCGEventOtherMouseDown:
            self._dispatch(action)

        return None  # suppress original event

    # ── pynput fallback path (no suppression) ────────────────────────────────

    def _run_pynput(self):
        if not _PYNPUT:
            return
        from pynput.mouse import Listener, Button

        def on_click(x, y, button, pressed):
            if not pressed:
                return
            _map = {Button.x1: BTN_BACK, Button.x2: BTN_FORWARD,
                    Button.middle: BTN_MIDDLE}
            btn = _map.get(button)
            if btn is not None:
                action = self.config.button_action(btn)
                if action.get("type") not in ("default", "disabled"):
                    self._dispatch(action)

        with Listener(on_click=on_click) as lst:
            while self._running:
                time.sleep(0.1)
            lst.stop()

    # ── Action dispatcher ─────────────────────────────────────────────────────

    def _dispatch(self, action: dict):
        t = action.get("type")
        if t == "disabled":
            pass
        elif t == "key":
            threading.Thread(
                target=press_combo, args=(action.get("key", ""),), daemon=True
            ).start()
        elif t == "mouse":
            threading.Thread(
                target=click_mouse_btn, args=(action.get("button", "left"),), daemon=True
            ).start()
        elif t == "macro":
            macro_id = action.get("macro_id")
            macro = self.config.macros.get(macro_id)
            if macro:
                steps = macro.get("steps", [])
                threading.Thread(
                    target=play_macro, args=(steps,), daemon=True
                ).start()
