"""Persistent JSON configuration for Viper Mini Config."""

import json
from pathlib import Path
from copy import deepcopy

CONFIG_PATH = Path.home() / ".config" / "viper-config" / "config.json"

_DEFAULTS: dict = {
    "dpi": {
        "stages": [800, 1600, 3200, 6400, 16000],
        "enabled": [True, True, True, False, False],
        "active": 0,
    },
    "lighting": {
        "effect": "static",
        "color": [130, 140, 248],       # indigo #818cf8
        "color2": [56, 189, 248],       # cyan #38bdf8
        "speed": 2,
        "breathing_dual": False,
    },
    "buttons": {
        # CGEvent button numbers: 2=middle, 3=X1/back, 4=X2/forward
        "2": {"type": "default"},
        "3": {"type": "default"},
        "4": {"type": "default"},
    },
    "macros": {},
}


class Config:
    def __init__(self):
        self.data: dict = deepcopy(_DEFAULTS)
        self.load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def load(self):
        try:
            raw = json.loads(CONFIG_PATH.read_text())
            self._merge(_DEFAULTS, raw, self.data)
        except Exception:
            pass  # use defaults

    def save(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(self.data, indent=2))

    def _merge(self, defaults: dict, source: dict, target: dict):
        """Recursively merge source into target, falling back to defaults."""
        for k, v in defaults.items():
            if k in source:
                if isinstance(v, dict) and isinstance(source[k], dict):
                    target[k] = {}
                    self._merge(v, source[k], target[k])
                else:
                    target[k] = source[k]
            else:
                target[k] = deepcopy(v)
        # Keep extra keys that aren't in defaults (e.g., user-defined macros)
        for k in source:
            if k not in defaults:
                target[k] = source[k]

    # ── DPI helpers ───────────────────────────────────────────────────────────

    @property
    def dpi_stages(self) -> list[int]:
        return self.data["dpi"]["stages"]

    @property
    def dpi_enabled(self) -> list[bool]:
        return self.data["dpi"]["enabled"]

    @property
    def dpi_active(self) -> int:
        return self.data["dpi"]["active"]

    def active_dpi_stages(self) -> list[int]:
        return [s for s, e in zip(self.dpi_stages, self.dpi_enabled) if e]

    # ── Button helpers ────────────────────────────────────────────────────────

    def button_action(self, btn_num: int) -> dict:
        return self.data["buttons"].get(str(btn_num), {"type": "default"})

    def set_button_action(self, btn_num: int, action: dict):
        self.data["buttons"][str(btn_num)] = action

    # ── Macro helpers ─────────────────────────────────────────────────────────

    @property
    def macros(self) -> dict:
        return self.data["macros"]

    def add_macro(self, macro_id: str, name: str, steps: list[dict]):
        self.data["macros"][macro_id] = {"name": name, "steps": steps}

    def delete_macro(self, macro_id: str):
        self.data["macros"].pop(macro_id, None)
        # Also clear any button bindings pointing to this macro
        for btn, action in self.data["buttons"].items():
            if action.get("type") == "macro" and action.get("macro_id") == macro_id:
                self.data["buttons"][btn] = {"type": "default"}
