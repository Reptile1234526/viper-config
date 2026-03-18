"""
CustomTkinter GUI for Razer Viper Mini Config.
Tabs: Buttons | DPI | Macros | Lighting
"""

import threading
import uuid
import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog

import customtkinter as ctk

from config import Config
from device import ViperMini
from remapper import ButtonRemapper, BTN_MIDDLE, BTN_BACK, BTN_FORWARD, BUTTON_NAMES

# ── Theme ─────────────────────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG       = "#030311"
CARD     = "#101028"
ACCENT   = "#818cf8"
ACCENT2  = "#38bdf8"
TEXT     = "#e2e8f0"
MUTED    = "#94a3b8"
BTN_FG   = "#251e52"
BTN_HOV  = "#352a72"
SUCCESS  = "#4ade80"
WARNING  = "#fbbf24"
ERROR    = "#f87171"


# ── Reusable widgets ──────────────────────────────────────────────────────────

def _label(parent, text, size=13, bold=False, color=TEXT, **kw):
    weight = "bold" if bold else "normal"
    return ctk.CTkLabel(parent, text=text,
                        font=ctk.CTkFont(size=size, weight=weight),
                        text_color=color, **kw)


def _btn(parent, text, command, width=120, fg=BTN_FG, hover=BTN_HOV, **kw):
    return ctk.CTkButton(parent, text=text, command=command, width=width,
                         fg_color=fg, hover_color=hover,
                         corner_radius=8, font=ctk.CTkFont(size=13), **kw)


def _section(parent, title):
    """Return a labelled card frame."""
    frame = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=10)
    _label(frame, title, size=12, bold=True, color=MUTED).pack(
        anchor="w", padx=14, pady=(10, 4))
    return frame


# ── Colour-picker button ──────────────────────────────────────────────────────

class ColorButton(ctk.CTkButton):
    """Button that shows a colour swatch and opens a colour-picker dialog."""

    def __init__(self, parent, color: list[int], on_change, **kw):
        self._color = color[:]
        self._on_change = on_change
        super().__init__(parent, text="", width=44, height=28,
                         fg_color=self._hex(), hover_color=self._hex(),
                         corner_radius=6, command=self._pick, **kw)

    def _hex(self):
        return "#{:02x}{:02x}{:02x}".format(*self._color)

    def _pick(self):
        init = self._hex()
        res = colorchooser.askcolor(color=init, title="Pick colour")
        if res and res[0]:
            self._color = [int(x) for x in res[0]]
            self.configure(fg_color=self._hex(), hover_color=self._hex())
            self._on_change(self._color)

    def set_color(self, color: list[int]):
        self._color = color[:]
        self.configure(fg_color=self._hex(), hover_color=self._hex())

    def get_color(self) -> list[int]:
        return self._color[:]


# ── Buttons tab ───────────────────────────────────────────────────────────────

_ACTION_LABELS = [
    "Default (pass-through)",
    "Disabled",
    "Keyboard shortcut",
    "Mouse: Left Click",
    "Mouse: Right Click",
    "Mouse: Middle Click",
    "Mouse: Back",
    "Mouse: Forward",
    "Macro…",
]

_ACTION_VALUE = {
    "Default (pass-through)": {"type": "default"},
    "Disabled":               {"type": "disabled"},
    "Mouse: Left Click":      {"type": "mouse", "button": "left"},
    "Mouse: Right Click":     {"type": "mouse", "button": "right"},
    "Mouse: Middle Click":    {"type": "mouse", "button": "middle"},
    "Mouse: Back":            {"type": "mouse", "button": "back"},
    "Mouse: Forward":         {"type": "mouse", "button": "forward"},
}


def _action_to_label(action: dict, macros: dict) -> str:
    t = action.get("type", "default")
    if t == "default":     return "Default (pass-through)"
    if t == "disabled":    return "Disabled"
    if t == "key":         return f"Key: {action.get('key', '')}"
    if t == "macro":
        mid = action.get("macro_id", "")
        name = macros.get(mid, {}).get("name", mid)
        return f"Macro: {name}"
    if t == "mouse":
        b = action.get("button", "")
        return f"Mouse: {b.capitalize()}"
    return "Default (pass-through)"


class ButtonsTab(ctk.CTkFrame):
    def __init__(self, parent, config: Config, app):
        super().__init__(parent, fg_color="transparent")
        self.config = config
        self.app = app
        self._rows: dict[int, dict] = {}
        self._build()

    def _build(self):
        _label(self, "Button Remapping", size=15, bold=True).pack(
            anchor="w", padx=4, pady=(8, 2))
        _label(self, "Side buttons are intercepted in software (requires Accessibility).",
               color=MUTED, size=12).pack(anchor="w", padx=4, pady=(0, 10))

        card = _section(self, "CONFIGURABLE BUTTONS")
        card.pack(fill="x", padx=4, pady=4)

        for btn_num in (BTN_BACK, BTN_FORWARD, BTN_MIDDLE):
            self._add_row(card, btn_num)

        _label(self, "Left and Right click cannot be remapped via software.",
               color=MUTED, size=11).pack(anchor="w", padx=4, pady=(8, 0))

    def _add_row(self, parent, btn_num: int):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=5)

        _label(row, BUTTON_NAMES[btn_num], size=13, width=160).pack(
            side="left", padx=(0, 10))

        action = self.config.button_action(btn_num)
        label = _action_to_label(action, self.config.macros)

        var = ctk.StringVar(value=label)
        combo = ctk.CTkComboBox(
            row, values=_ACTION_LABELS, variable=var, width=220,
            command=lambda v, n=btn_num, sv=var: self._on_select(n, sv))
        combo.pack(side="left", padx=4)

        # Key-entry (shown only when "Keyboard shortcut" is selected)
        key_var = ctk.StringVar(
            value=action.get("key", "") if action.get("type") == "key" else "")
        key_entry = ctk.CTkEntry(row, textvariable=key_var,
                                  placeholder_text="e.g. cmd+c  or  ctrl+z",
                                  width=160)
        if action.get("type") == "key":
            key_entry.pack(side="left", padx=4)

        key_entry.bind("<FocusOut>",
                       lambda e, n=btn_num, sv=key_var: self._save_key(n, sv))

        self._rows[btn_num] = {
            "combo": combo, "var": var,
            "key_entry": key_entry, "key_var": key_var,
        }

    def _on_select(self, btn_num: int, var: ctk.StringVar):
        label = var.get()
        row = self._rows[btn_num]
        entry = row["key_entry"]

        if label == "Keyboard shortcut":
            entry.pack(side="left", padx=4)
        else:
            entry.pack_forget()

        if label == "Macro…":
            self._pick_macro(btn_num)
            return

        if label in _ACTION_VALUE:
            self.config.set_button_action(btn_num, _ACTION_VALUE[label])
            self.config.save()
            self.app.remapper.config = self.config

    def _save_key(self, btn_num: int, key_var: ctk.StringVar):
        combo = key_var.get().strip()
        if combo:
            self.config.set_button_action(btn_num, {"type": "key", "key": combo})
            self.config.save()

    def _pick_macro(self, btn_num: int):
        macros = self.config.macros
        if not macros:
            messagebox.showinfo("No Macros",
                                "Create a macro in the Macros tab first.")
            self._rows[btn_num]["var"].set(
                _action_to_label(self.config.button_action(btn_num),
                                 self.config.macros))
            return

        names = [f"{mid}: {m['name']}" for mid, m in macros.items()]
        choice = simpledialog.askstring(
            "Pick Macro", "Macro ID: name\n" + "\n".join(names) +
            "\n\nEnter macro ID:")
        if choice and choice in macros:
            self.config.set_button_action(
                btn_num, {"type": "macro", "macro_id": choice})
            self.config.save()
            label = _action_to_label(
                self.config.button_action(btn_num), self.config.macros)
            self._rows[btn_num]["var"].set(label)
        else:
            self._rows[btn_num]["var"].set(
                _action_to_label(self.config.button_action(btn_num),
                                 self.config.macros))

    def refresh(self):
        """Refresh macro names in combo labels after macro changes."""
        for btn_num, row in self._rows.items():
            action = self.config.button_action(btn_num)
            row["var"].set(_action_to_label(action, self.config.macros))


# ── DPI tab ───────────────────────────────────────────────────────────────────

class DPITab(ctk.CTkFrame):
    def __init__(self, parent, config: Config, device: ViperMini):
        super().__init__(parent, fg_color="transparent")
        self.config = config
        self.device = device
        self._sliders: list[dict] = []
        self._active_var = ctk.IntVar(value=config.dpi_active)
        self._build()

    def _build(self):
        _label(self, "DPI Stages", size=15, bold=True).pack(
            anchor="w", padx=4, pady=(8, 2))
        _label(self, "Set up to 5 DPI stages. Cycle through them with the DPI button.",
               color=MUTED, size=12).pack(anchor="w", padx=4, pady=(0, 10))

        card = _section(self, "STAGES")
        card.pack(fill="x", padx=4, pady=4)

        for i in range(5):
            self._add_stage_row(card, i)

        # Active stage
        active_card = _section(self, "ACTIVE STAGE ON STARTUP")
        active_card.pack(fill="x", padx=4, pady=(8, 4))
        row = ctk.CTkFrame(active_card, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(4, 10))
        for i in range(5):
            ctk.CTkRadioButton(
                row, text=f"Stage {i+1}", variable=self._active_var, value=i,
                command=self._on_active_change,
                radiobutton_width=16, radiobutton_height=16,
            ).pack(side="left", padx=8)

        # Apply button
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=4, pady=(12, 4))
        _btn(btn_row, "Apply to Device", self._apply,
             width=160, fg=ACCENT, hover="#6366f1").pack(side="left", padx=4)
        self._status = _label(btn_row, "", color=MUTED, size=12)
        self._status.pack(side="left", padx=8)

    def _add_stage_row(self, parent, idx: int):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=6)

        enabled_var = ctk.BooleanVar(value=self.config.dpi_enabled[idx])
        chk = ctk.CTkCheckBox(row, text=f"Stage {idx+1}", variable=enabled_var,
                               width=90, checkbox_width=16, checkbox_height=16,
                               command=lambda i=idx, v=enabled_var: self._on_enable(i, v))
        chk.pack(side="left", padx=(0, 8))

        dpi_val = self.config.dpi_stages[idx]
        slider_var = ctk.IntVar(value=dpi_val)

        val_label = _label(row, f"{dpi_val:,}", size=13, width=60)
        val_label.pack(side="right", padx=(8, 4))

        slider = ctk.CTkSlider(
            row, from_=100, to=30400, variable=slider_var,
            number_of_steps=304,
            command=lambda v, i=idx, lbl=val_label, sv=slider_var:
                self._on_dpi_slide(i, sv, lbl))
        slider.pack(side="left", fill="x", expand=True, padx=4)

        if not enabled_var.get():
            slider.configure(state="disabled")

        self._sliders.append({
            "enabled_var": enabled_var, "slider_var": slider_var,
            "slider": slider, "label": val_label,
        })

    def _on_enable(self, idx: int, var: ctk.BooleanVar):
        self.config.dpi_enabled[idx] = var.get()
        state = "normal" if var.get() else "disabled"
        self._sliders[idx]["slider"].configure(state=state)
        self.config.save()

    def _on_dpi_slide(self, idx: int, var: ctk.IntVar, label: ctk.CTkLabel):
        v = round(var.get() / 100) * 100
        var.set(v)
        label.configure(text=f"{v:,}")
        self.config.dpi_stages[idx] = v
        self.config.save()

    def _on_active_change(self):
        self.config.data["dpi"]["active"] = self._active_var.get()
        self.config.save()

    def _apply(self):
        if not self.device.connected:
            self._status.configure(text="Device not connected", text_color=WARNING)
            return
        stages = self.config.active_dpi_stages()
        if not stages:
            self._status.configure(text="No stages enabled", text_color=WARNING)
            return
        self._status.configure(text="Applying…", text_color=MUTED)
        self.after(50, self._do_apply)

    def _do_apply(self):
        ok = self.device.apply_dpi_stages(
            self.config.active_dpi_stages(), self.config.dpi_active)
        if ok:
            self._status.configure(text="Applied!", text_color=SUCCESS)
        else:
            self._status.configure(text="Failed (check connection)", text_color=ERROR)
        self.after(3000, lambda: self._status.configure(text=""))


# ── Macros tab ────────────────────────────────────────────────────────────────

_STEP_TYPES = ["Key Press", "Delay (ms)", "Type Text", "Mouse Click"]
_MOUSE_BTNS = ["left", "right", "middle", "back", "forward"]


class MacrosTab(ctk.CTkFrame):
    def __init__(self, parent, config: Config, on_macros_changed):
        super().__init__(parent, fg_color="transparent")
        self.config = config
        self.on_macros_changed = on_macros_changed
        self._selected_id: str | None = None
        self._step_rows: list[dict] = []
        self._build()
        self._refresh_list()

    def _build(self):
        pane = ctk.CTkFrame(self, fg_color="transparent")
        pane.pack(fill="both", expand=True, padx=4, pady=4)

        # ── Left: macro list ──────────────────────────────────────────────────
        left = ctk.CTkFrame(pane, fg_color=CARD, corner_radius=10, width=180)
        left.pack(side="left", fill="y", padx=(0, 8), pady=0)
        left.pack_propagate(False)

        _label(left, "MACROS", size=12, bold=True, color=MUTED).pack(
            anchor="w", padx=12, pady=(10, 4))

        self._list_frame = ctk.CTkScrollableFrame(
            left, fg_color="transparent", width=160)
        self._list_frame.pack(fill="both", expand=True, padx=6)

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=8)
        _btn(btn_row, "+ New", self._new_macro, width=72, fg=ACCENT,
             hover="#6366f1").pack(side="left")
        _btn(btn_row, "Delete", self._delete_macro, width=72, fg="#3b1e1e",
             hover="#5c2626").pack(side="right")

        # ── Right: editor ─────────────────────────────────────────────────────
        right = ctk.CTkFrame(pane, fg_color=CARD, corner_radius=10)
        right.pack(side="left", fill="both", expand=True)

        _label(right, "EDITOR", size=12, bold=True, color=MUTED).pack(
            anchor="w", padx=14, pady=(10, 4))

        name_row = ctk.CTkFrame(right, fg_color="transparent")
        name_row.pack(fill="x", padx=12, pady=(0, 8))
        _label(name_row, "Name:", size=13, width=50).pack(side="left")
        self._name_var = ctk.StringVar()
        self._name_entry = ctk.CTkEntry(name_row, textvariable=self._name_var,
                                         width=200)
        self._name_entry.pack(side="left", padx=6)
        self._name_entry.bind("<FocusOut>", self._save_name)

        _label(right, "Steps:", size=13, bold=True).pack(anchor="w", padx=14)
        self._steps_frame = ctk.CTkScrollableFrame(right, fg_color="transparent",
                                                    height=200)
        self._steps_frame.pack(fill="both", expand=True, padx=10)

        add_row = ctk.CTkFrame(right, fg_color="transparent")
        add_row.pack(fill="x", padx=12, pady=8)

        self._new_type_var = ctk.StringVar(value="Key Press")
        ctk.CTkComboBox(add_row, values=_STEP_TYPES,
                         variable=self._new_type_var, width=130).pack(
            side="left", padx=(0, 6))
        self._new_val_var = ctk.StringVar()
        ctk.CTkEntry(add_row, textvariable=self._new_val_var,
                      placeholder_text="value", width=140).pack(
            side="left", padx=(0, 6))
        _btn(add_row, "+ Add", self._add_step, width=80,
             fg=BTN_FG, hover=BTN_HOV).pack(side="left")

        self._editor_placeholder = _label(
            right, "Select or create a macro", color=MUTED, size=13)
        self._editor_placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # ── List management ───────────────────────────────────────────────────────

    def _refresh_list(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        for mid, macro in self.config.macros.items():
            btn = ctk.CTkButton(
                self._list_frame, text=macro["name"],
                fg_color=ACCENT if mid == self._selected_id else "transparent",
                hover_color=BTN_HOV, anchor="w",
                command=lambda m=mid: self._select(m),
                font=ctk.CTkFont(size=13), height=30, corner_radius=6)
            btn.pack(fill="x", pady=2)

    def _select(self, macro_id: str):
        self._selected_id = macro_id
        self._refresh_list()
        self._load_editor(macro_id)
        self._editor_placeholder.place_forget()

    def _new_macro(self):
        mid = str(uuid.uuid4())[:8]
        self.config.add_macro(mid, "New Macro", [])
        self.config.save()
        self._refresh_list()
        self._select(mid)
        self.on_macros_changed()

    def _delete_macro(self):
        if not self._selected_id:
            return
        self.config.delete_macro(self._selected_id)
        self.config.save()
        self._selected_id = None
        self._refresh_list()
        self._clear_editor()
        self.on_macros_changed()

    # ── Editor ────────────────────────────────────────────────────────────────

    def _load_editor(self, macro_id: str):
        macro = self.config.macros.get(macro_id, {})
        self._name_var.set(macro.get("name", ""))
        self._rebuild_steps(macro.get("steps", []))

    def _clear_editor(self):
        self._name_var.set("")
        self._rebuild_steps([])
        self._editor_placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _rebuild_steps(self, steps: list[dict]):
        for w in self._steps_frame.winfo_children():
            w.destroy()
        self._step_rows = []
        for i, step in enumerate(steps):
            self._add_step_row(i, step)

    def _add_step_row(self, idx: int, step: dict):
        t = step.get("type", "")
        if t == "key_press":    display = f"Key: {step.get('key','')}"
        elif t == "delay":      display = f"Delay: {step.get('ms',50)} ms"
        elif t == "type_text":  display = f"Type: {step.get('text','')}"
        elif t == "mouse_click": display = f"Click: {step.get('button','left')}"
        else:                   display = str(step)

        row = ctk.CTkFrame(self._steps_frame, fg_color="#1a1a38", corner_radius=6)
        row.pack(fill="x", pady=2)
        _label(row, f"{idx+1}. {display}", size=12).pack(side="left", padx=10, pady=4)
        _btn(row, "✕", lambda i=idx: self._remove_step(i),
             width=28, height=24, fg="#3b1e1e", hover="#5c2626").pack(
            side="right", padx=4)

    def _add_step(self):
        if not self._selected_id:
            return
        t = self._new_type_var.get()
        val = self._new_val_var.get().strip()

        if t == "Key Press":
            step = {"type": "key_press", "key": val or "cmd+c"}
        elif t == "Delay (ms)":
            try:
                ms = int(val)
            except ValueError:
                ms = 100
            step = {"type": "delay", "ms": ms}
        elif t == "Type Text":
            step = {"type": "type_text", "text": val}
        elif t == "Mouse Click":
            btn = val if val in _MOUSE_BTNS else "left"
            step = {"type": "mouse_click", "button": btn}
        else:
            return

        macro = self.config.macros[self._selected_id]
        macro["steps"].append(step)
        self.config.save()
        self._rebuild_steps(macro["steps"])
        self._new_val_var.set("")

    def _remove_step(self, idx: int):
        if not self._selected_id:
            return
        macro = self.config.macros[self._selected_id]
        if 0 <= idx < len(macro["steps"]):
            macro["steps"].pop(idx)
            self.config.save()
            self._rebuild_steps(macro["steps"])

    def _save_name(self, _event=None):
        if not self._selected_id:
            return
        name = self._name_var.get().strip() or "Unnamed"
        self.config.macros[self._selected_id]["name"] = name
        self.config.save()
        self._refresh_list()
        self.on_macros_changed()


# ── Lighting tab ──────────────────────────────────────────────────────────────

_EFFECTS = ["Off", "Static", "Breathing", "Reactive"]


class LightingTab(ctk.CTkFrame):
    def __init__(self, parent, config: Config, device: ViperMini):
        super().__init__(parent, fg_color="transparent")
        self.config = config
        self.device = device
        self._build()

    def _build(self):
        lcfg = self.config.data["lighting"]

        _label(self, "Lighting", size=15, bold=True).pack(
            anchor="w", padx=4, pady=(8, 2))
        _label(self, "Controls the Razer logo LED on the Viper Mini.",
               color=MUTED, size=12).pack(anchor="w", padx=4, pady=(0, 10))

        card = _section(self, "EFFECT")
        card.pack(fill="x", padx=4, pady=4)

        effect_row = ctk.CTkFrame(card, fg_color="transparent")
        effect_row.pack(fill="x", padx=10, pady=(4, 8))
        _label(effect_row, "Effect:", size=13, width=70).pack(side="left")
        self._effect_var = ctk.StringVar(value=lcfg["effect"].capitalize())
        ctk.CTkComboBox(effect_row, values=_EFFECTS,
                         variable=self._effect_var, width=150,
                         command=self._on_effect_change).pack(side="left", padx=6)

        # Colour
        color_card = _section(self, "COLOR")
        color_card.pack(fill="x", padx=4, pady=4)

        c1_row = ctk.CTkFrame(color_card, fg_color="transparent")
        c1_row.pack(fill="x", padx=10, pady=(4, 4))
        _label(c1_row, "Color 1:", size=13, width=70).pack(side="left")
        self._color_btn = ColorButton(
            c1_row, lcfg["color"],
            on_change=lambda c: self._on_color(c, "color"))
        self._color_btn.pack(side="left", padx=6)


        # Speed
        speed_card = _section(self, "SPEED  (breathing / reactive)")
        speed_card.pack(fill="x", padx=4, pady=4)
        speed_row = ctk.CTkFrame(speed_card, fg_color="transparent")
        speed_row.pack(fill="x", padx=10, pady=(4, 10))
        _label(speed_row, "Fast", size=12, color=MUTED, width=36).pack(side="left")
        self._speed_var = ctk.IntVar(value=lcfg["speed"])
        ctk.CTkSlider(speed_row, from_=1, to=3, number_of_steps=2,
                       variable=self._speed_var,
                       command=lambda v: self._on_speed(v)).pack(
            side="left", fill="x", expand=True, padx=4)
        _label(speed_row, "Slow", size=12, color=MUTED, width=36).pack(side="left")

        # Apply
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=4, pady=(12, 4))
        _btn(btn_row, "Apply to Device", self._apply,
             width=160, fg=ACCENT, hover="#6366f1").pack(side="left", padx=4)
        self._status = _label(btn_row, "", color=MUTED, size=12)
        self._status.pack(side="left", padx=8)

    def _on_effect_change(self, val: str):
        self.config.data["lighting"]["effect"] = val.lower()
        self.config.save()

    def _on_color(self, color: list[int], key: str):
        self.config.data["lighting"][key] = color
        self.config.save()

    def _on_speed(self, val):
        self.config.data["lighting"]["speed"] = round(float(val))
        self.config.save()

    def _apply(self):
        if not self.device.connected:
            self._status.configure(text="Device not connected", text_color=WARNING)
            return
        self._status.configure(text="Applying…", text_color=MUTED)
        self.after(50, self._do_apply)

    def _do_apply(self):
        ok = self.device.apply_lighting(self.config.data["lighting"])
        if ok:
            self._status.configure(text="Applied!", text_color=SUCCESS)
        else:
            self._status.configure(text="Applied (unconfirmed — check your mouse)",
                                   text_color=WARNING)
        self.after(4000, lambda: self._status.configure(text=""))


# ── Main App window ───────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Viper Mini Config")
        self.geometry("820x560")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        self.config = Config()
        self.device = ViperMini()
        self.remapper = ButtonRemapper(self.config)

        self._build()
        self.after(300, self._connect_device)
        self.after(100, self._start_remapper)

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        # Top bar
        bar = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        _label(bar, "🖱  Razer Viper Mini Config", size=16, bold=True).pack(
            side="left", padx=18, pady=12)

        self._conn_label = _label(bar, "⬤  Searching…", size=13, color=MUTED)
        self._conn_label.pack(side="right", padx=18)

        # Accessibility warning (hidden until needed)
        self._acc_bar = ctk.CTkFrame(self, fg_color="#2a1a0a", corner_radius=0)
        _label(self._acc_bar,
               "⚠  Accessibility access required for button remapping.  ",
               color=WARNING, size=12).pack(side="left", padx=14, pady=6)
        _btn(self._acc_bar, "Grant Access", self._grant_access,
             width=110, fg="#7c4a00", hover="#a36200").pack(side="left")

        # Tab view
        self._tabs = ctk.CTkTabview(
            self, fg_color=BG, segmented_button_fg_color=CARD,
            segmented_button_selected_color=BTN_FG,
            segmented_button_selected_hover_color=BTN_HOV,
            segmented_button_unselected_color=CARD,
            segmented_button_unselected_hover_color="#1a1a38",
            text_color=TEXT, text_color_disabled=MUTED)
        self._tabs.pack(fill="both", expand=True, padx=10, pady=(4, 6))

        for name in ("Buttons", "DPI", "Macros", "Lighting"):
            self._tabs.add(name)

        self._btns_tab = ButtonsTab(
            self._tabs.tab("Buttons"), self.config, self)
        self._btns_tab.pack(fill="both", expand=True)

        self._dpi_tab = DPITab(
            self._tabs.tab("DPI"), self.config, self.device)
        self._dpi_tab.pack(fill="both", expand=True)

        self._macros_tab = MacrosTab(
            self._tabs.tab("Macros"), self.config,
            on_macros_changed=self._on_macros_changed)
        self._macros_tab.pack(fill="both", expand=True)

        self._light_tab = LightingTab(
            self._tabs.tab("Lighting"), self.config, self.device)
        self._light_tab.pack(fill="both", expand=True)

        # Bottom bar with factory reset
        footer = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=44)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        _btn(footer, "⚠  Factory Reset", self._factory_reset,
             width=160, fg="#3b1e1e", hover="#5c2626").pack(
            side="right", padx=12, pady=8)

        self._footer_status = _label(footer, "", size=12, color=MUTED)
        self._footer_status.pack(side="right", padx=8, pady=8)

    # ── Device connection ─────────────────────────────────────────────────────

    def _connect_device(self):
        ok = self.device.connect()
        if ok:
            name = self.device.product_name()
            self._conn_label.configure(text=f"⬤  {name}", text_color=SUCCESS)
        else:
            self._conn_label.configure(text="⬤  Device not found", text_color=ERROR)
            self.after(5000, self._connect_device)

    # ── Remapper ──────────────────────────────────────────────────────────────

    def _start_remapper(self):
        if not ButtonRemapper.accessibility_ok():
            self._acc_bar.pack(fill="x", after=self._tabs)
        else:
            self.remapper.start()

    def _grant_access(self):
        ButtonRemapper.request_accessibility()
        messagebox.showinfo(
            "Accessibility",
            "Please add Terminal (or your Python binary) to:\n"
            "System Settings → Privacy & Security → Accessibility\n\n"
            "Then restart this app.")

    # ── Factory reset ─────────────────────────────────────────────────────────

    def _factory_reset(self):
        if not self.device.connected:
            messagebox.showwarning("Not Connected",
                                   "Plug in the Viper Mini first.")
            return

        confirmed = messagebox.askyesno(
            "Factory Reset",
            "This will reset the mouse to factory defaults:\n\n"
            "  • DPI → 800\n"
            "  • Lighting → static white\n\n"
            "Your saved config in this app will also be reset.\n\n"
            "Continue?",
            icon="warning")

        if not confirmed:
            return

        self._footer_status.configure(text="Resetting…", text_color=MUTED)
        self.update()

        ok = self.device.factory_reset()

        # Reset local config to defaults too
        from copy import deepcopy
        from config import _DEFAULTS
        self.config.data = deepcopy(_DEFAULTS)
        self.config.save()

        if ok:
            self._footer_status.configure(text="Reset complete!", text_color=SUCCESS)
        else:
            self._footer_status.configure(
                text="Sent reset (some commands may not confirm)", text_color=WARNING)

        self.after(4000, lambda: self._footer_status.configure(text=""))

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_macros_changed(self):
        self._btns_tab.refresh()

    def on_close(self):
        self.remapper.stop()
        self.device.disconnect()
        self.destroy()
