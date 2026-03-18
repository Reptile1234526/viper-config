"""
CustomTkinter GUI for Razer Viper Mini Config.
Pages: Buttons | DPI | Macros | Lighting
Sidebar navigation replaces CTkTabview.
"""

import threading
import uuid
import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog

import customtkinter as ctk

from config import Config
from device import ViperMini
from remapper import ButtonRemapper, BTN_MIDDLE, BTN_BACK, BTN_FORWARD, BUTTON_NAMES, _action_queue

# ── Theme ─────────────────────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

import time as _time

BG       = "#111114"
SIDEBAR  = "#0d0d10"
SURFACE  = "#1c1c24"
BORDER   = "#252530"
ACCENT   = "#818cf8"
ACCENT_H = "#6366f1"
TEXT     = "#efefef"
MUTED    = "#60607a"
DIM      = "#38384a"
SUCCESS  = "#4ade80"
WARNING  = "#fbbf24"
ERROR    = "#f87171"
BTN      = "#232330"
BTN_HOV  = "#2d2d3c"
DANGER   = "#321818"
DANGER_H = "#4a2020"

# Keep old names as aliases so internal widget code keeps working
BTN_FG   = BTN


# ── Reusable widgets ──────────────────────────────────────────────────────────

def _label(parent, text, size=13, bold=False, color=TEXT, **kw):
    weight = "bold" if bold else "normal"
    return ctk.CTkLabel(parent, text=text,
                        font=ctk.CTkFont(size=size, weight=weight),
                        text_color=color, **kw)


def _btn(parent, text, command, width=120, fg=BTN, hover=BTN_HOV, **kw):
    _last = [0.0]
    def _fire(e=None):
        t = _time.monotonic()
        if t - _last[0] > 0.1:
            _last[0] = t
            command()
    b = ctk.CTkButton(parent, text=text, command=_fire, width=width,
                      fg_color=fg, hover_color=hover,
                      corner_radius=6, font=ctk.CTkFont(size=13), **kw)
    b._viper_fire = _fire
    b.bind("<ButtonRelease-1>", _fire, add="+")
    b.bind("<B1-Motion>", _fire, add="+")
    return b


def _section(parent, title):
    """Return a labelled section frame."""
    frame = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=8)
    _label(frame, title, size=10, bold=True, color=MUTED).pack(
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


# ── Shortcut recorder widget ──────────────────────────────────────────────────

class ShortcutEntry(ctk.CTkFrame):
    """Entry + Record button — press Record then hit a key combo to capture it."""

    def __init__(self, parent, initial: str, on_change, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self._on_change = on_change
        self._recording = False
        self._held_mods: set[str] = set()
        self._bind_ids: list[tuple] = []

        self._var = ctk.StringVar(value=initial)
        self._entry = ctk.CTkEntry(self, textvariable=self._var,
                                    placeholder_text="cmd+c",
                                    width=130)
        self._entry.pack(side="left", padx=(0, 4))
        self._entry.bind("<FocusOut>", self._on_focus_out)

        self._rec_btn = ctk.CTkButton(
            self, text="Record", width=72,
            fg_color=BTN, hover_color=BTN_HOV,
            corner_radius=6, font=ctk.CTkFont(size=12),
            command=self._start)
        self._rec_btn.pack(side="left")

    def get(self) -> str:
        return self._var.get().strip()

    def set(self, value: str):
        self._var.set(value)

    def _on_focus_out(self, _event=None):
        val = self._var.get().strip()
        if val:
            self._on_change(val)

    def _start(self):
        if self._recording:
            return
        self._recording = True
        self._held_mods.clear()
        self._rec_btn.configure(text="Listening…",
                                 fg_color="#4a2a82", hover_color="#4a2a82")
        root = self.winfo_toplevel()
        bid1 = root.bind("<KeyPress>",   self._on_press,   add="+")
        bid2 = root.bind("<KeyRelease>", self._on_release, add="+")
        self._bind_ids = [(root, "<KeyPress>", bid1), (root, "<KeyRelease>", bid2)]
        root.focus_force()

    def _stop(self):
        self._recording = False
        for widget, event, bid in self._bind_ids:
            try:
                widget.unbind(event, bid)
            except Exception:
                pass
        self._bind_ids.clear()
        self._rec_btn.configure(text="Record",
                                 fg_color=BTN, hover_color=BTN_HOV)

    def _on_release(self, event):
        sym = event.keysym
        if sym in ("Control_L", "Control_R"):   self._held_mods.discard("ctrl")
        elif sym in ("Meta_L", "Meta_R"):        self._held_mods.discard("cmd")
        elif sym in ("Shift_L", "Shift_R"):      self._held_mods.discard("shift")
        elif sym in ("Alt_L", "Alt_R"):          self._held_mods.discard("alt")

    def _on_press(self, event):
        if not self._recording:
            return
        sym = event.keysym
        if sym in ("Control_L", "Control_R"):   self._held_mods.add("ctrl");  return
        if sym in ("Meta_L", "Meta_R"):          self._held_mods.add("cmd");   return
        if sym in ("Shift_L", "Shift_R"):        self._held_mods.add("shift"); return
        if sym in ("Alt_L", "Alt_R"):            self._held_mods.add("alt");   return
        if sym == "Escape":                      self._stop();                  return

        self._stop()

        _SPECIAL = {
            "Return": "enter", "Prior": "pageup", "Next": "pagedown",
            "BackSpace": "backspace", "Delete": "delete", "Tab": "tab",
            "Up": "up", "Down": "down", "Left": "left", "Right": "right",
            "Home": "home", "End": "end", "space": "space",
            **{f"F{n}": f"f{n}" for n in range(1, 13)},
        }
        key = _SPECIAL.get(sym, sym.lower())
        parts = [m for m in ("cmd", "ctrl", "shift", "alt") if m in self._held_mods]
        parts.append(key)
        combo = "+".join(parts)
        self._var.set(combo)
        self._on_change(combo)


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
            anchor="w", padx=16, pady=(12, 2))
        _label(self, "Side buttons are intercepted in software (requires Accessibility).",
               color=MUTED, size=12).pack(anchor="w", padx=16, pady=(0, 10))

        card = _section(self, "CONFIGURABLE BUTTONS")
        card.pack(fill="x", padx=16, pady=4)

        for btn_num in (BTN_BACK, BTN_FORWARD, BTN_MIDDLE):
            self._add_row(card, btn_num)

        _label(self, "Left and Right click cannot be remapped via software.",
               color=MUTED, size=11).pack(anchor="w", padx=16, pady=(10, 0))

    def _add_row(self, parent, btn_num: int):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=7)

        _label(row, BUTTON_NAMES[btn_num], size=13, width=160).pack(
            side="left", padx=(0, 10))

        action = self.config.button_action(btn_num)
        label = _action_to_label(action, self.config.macros)

        var = ctk.StringVar(value=label)
        combo = ctk.CTkComboBox(
            row, values=_ACTION_LABELS, variable=var, width=220,
            command=lambda v, n=btn_num, sv=var: self._on_select(n, sv))
        combo.pack(side="left", padx=4)

        # Shortcut recorder (shown only when "Keyboard shortcut" is selected)
        initial_key = action.get("key", "") if action.get("type") == "key" else ""
        key_widget = ShortcutEntry(
            row, initial=initial_key,
            on_change=lambda val, n=btn_num: self._save_key(n, val))
        if action.get("type") == "key":
            key_widget.pack(side="left", padx=4)

        self._rows[btn_num] = {
            "combo": combo, "var": var,
            "key_entry": key_widget,
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

    def _save_key(self, btn_num: int, combo: str):
        combo = combo.strip()
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
            anchor="w", padx=16, pady=(12, 2))
        _label(self, "Set up to 5 DPI stages. Cycle through them with the DPI button.",
               color=MUTED, size=12).pack(anchor="w", padx=16, pady=(0, 10))

        card = _section(self, "STAGES")
        card.pack(fill="x", padx=16, pady=4)

        for i in range(5):
            self._add_stage_row(card, i)

        # Active stage
        active_card = _section(self, "ACTIVE STAGE ON STARTUP")
        active_card.pack(fill="x", padx=16, pady=(10, 4))
        row = ctk.CTkFrame(active_card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(6, 12))
        for i in range(5):
            ctk.CTkRadioButton(
                row, text=f"Stage {i+1}", variable=self._active_var, value=i,
                command=self._on_active_change,
                radiobutton_width=16, radiobutton_height=16,
            ).pack(side="left", padx=8)

        # Apply button
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(14, 4))
        _btn(btn_row, "Apply to Device", self._apply,
             width=160, fg=ACCENT, hover=ACCENT_H).pack(side="left", padx=4)
        self._status = _label(btn_row, "", color=MUTED, size=12)
        self._status.pack(side="left", padx=8)

    def _add_stage_row(self, parent, idx: int):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=7)

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
        pane.pack(fill="both", expand=True, padx=16, pady=12)

        # ── Left: macro list ──────────────────────────────────────────────────
        left = ctk.CTkFrame(pane, fg_color=SURFACE, corner_radius=8, width=180)
        left.pack(side="left", fill="y", padx=(0, 10), pady=0)
        left.pack_propagate(False)

        _label(left, "MACROS", size=10, bold=True, color=MUTED).pack(
            anchor="w", padx=12, pady=(10, 4))

        self._list_frame = ctk.CTkScrollableFrame(
            left, fg_color="transparent", width=160)
        self._list_frame.pack(fill="both", expand=True, padx=6)

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=8)
        _btn(btn_row, "+ New", self._new_macro, width=72, fg=ACCENT,
             hover=ACCENT_H).pack(side="left")
        _btn(btn_row, "Delete", self._delete_macro, width=72, fg=DANGER,
             hover=DANGER_H).pack(side="right")

        # ── Right: editor ─────────────────────────────────────────────────────
        right = ctk.CTkFrame(pane, fg_color=SURFACE, corner_radius=8)
        right.pack(side="left", fill="both", expand=True)

        _label(right, "EDITOR", size=10, bold=True, color=MUTED).pack(
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
             fg=BTN, hover=BTN_HOV).pack(side="left")

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

        row = ctk.CTkFrame(self._steps_frame, fg_color=DIM, corner_radius=6)
        row.pack(fill="x", pady=2)
        _label(row, f"{idx+1}. {display}", size=12).pack(side="left", padx=10, pady=5)
        _btn(row, "x", lambda i=idx: self._remove_step(i),
             width=28, height=24, fg=DANGER, hover=DANGER_H).pack(
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
            anchor="w", padx=16, pady=(12, 2))
        _label(self, "Controls the Razer logo LED on the Viper Mini.",
               color=MUTED, size=12).pack(anchor="w", padx=16, pady=(0, 10))

        card = _section(self, "EFFECT")
        card.pack(fill="x", padx=16, pady=4)

        effect_row = ctk.CTkFrame(card, fg_color="transparent")
        effect_row.pack(fill="x", padx=12, pady=(6, 10))
        _label(effect_row, "Effect:", size=13, width=70).pack(side="left")
        self._effect_var = ctk.StringVar(value=lcfg["effect"].capitalize())
        ctk.CTkComboBox(effect_row, values=_EFFECTS,
                         variable=self._effect_var, width=150,
                         command=self._on_effect_change).pack(side="left", padx=6)

        # Colour
        color_card = _section(self, "COLOR")
        color_card.pack(fill="x", padx=16, pady=4)

        c1_row = ctk.CTkFrame(color_card, fg_color="transparent")
        c1_row.pack(fill="x", padx=12, pady=(6, 8))
        _label(c1_row, "Color 1:", size=13, width=70).pack(side="left")
        self._color_btn = ColorButton(
            c1_row, lcfg["color"],
            on_change=lambda c: self._on_color(c, "color"))
        self._color_btn.pack(side="left", padx=6)

        # Speed
        speed_card = _section(self, "SPEED  (breathing / reactive)")
        speed_card.pack(fill="x", padx=16, pady=4)
        speed_row = ctk.CTkFrame(speed_card, fg_color="transparent")
        speed_row.pack(fill="x", padx=12, pady=(6, 12))
        _label(speed_row, "Fast", size=12, color=MUTED, width=36).pack(side="left")
        self._speed_var = ctk.IntVar(value=lcfg["speed"])
        ctk.CTkSlider(speed_row, from_=1, to=3, number_of_steps=2,
                       variable=self._speed_var,
                       command=lambda v: self._on_speed(v)).pack(
            side="left", fill="x", expand=True, padx=4)
        _label(speed_row, "Slow", size=12, color=MUTED, width=36).pack(side="left")

        # Apply
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(14, 4))
        _btn(btn_row, "Apply to Device", self._apply,
             width=160, fg=ACCENT, hover=ACCENT_H).pack(side="left", padx=4)
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
        self.geometry("860x560")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        self.config = Config()
        self.device = ViperMini()
        self.remapper = ButtonRemapper(self.config)

        self._build()
        self.after(300, self._connect_device)
        self.after(100, self._start_remapper)
        self.after(20, self._drain_action_queue)
        self._btn_was_pressed = False
        self.after(10, self._poll_button_clicks)

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=SIDEBAR, corner_radius=0, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)

        _label(header, "Viper Mini", size=15, bold=True).pack(
            side="left", padx=18, pady=0)

        self._conn_label = _label(header, "Searching…", size=12, color=MUTED)
        self._conn_label.pack(side="right", padx=18)

        # ── Accessibility warning (hidden until needed) ────────────────────────
        self._acc_bar = ctk.CTkFrame(self, fg_color="#2a1a0a", corner_radius=0)
        _label(self._acc_bar,
               "Accessibility access required for button remapping.  ",
               color=WARNING, size=12).pack(side="left", padx=14, pady=6)
        _btn(self._acc_bar, "Grant Access", self._grant_access,
             width=110, fg="#7c4a00", hover="#a36200").pack(side="left")

        # ── Body: sidebar + content ────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # Sidebar (130px)
        sidebar = ctk.CTkFrame(body, fg_color=SIDEBAR, corner_radius=0, width=130)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # 1px separator line
        sep = ctk.CTkFrame(body, fg_color=BORDER, corner_radius=0, width=1)
        sep.pack(side="left", fill="y")

        # Content area
        self._content = ctk.CTkFrame(body, fg_color=BG, corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

        # ── Nav buttons ───────────────────────────────────────────────────────
        nav_top = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav_top.pack(fill="x", padx=8, pady=(12, 0))

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        for page_name in ("Buttons", "DPI", "Macros", "Lighting"):
            btn = ctk.CTkButton(
                nav_top, text=page_name, anchor="w",
                height=36, corner_radius=6,
                fg_color="transparent", hover_color=BTN_HOV,
                text_color=MUTED,
                font=ctk.CTkFont(size=13),
                command=lambda n=page_name: self._show_page(n))
            btn._viper_fire = lambda n=page_name: self._show_page(n)
            btn.pack(fill="x", pady=2)
            self._nav_buttons[page_name] = btn

        # ── Sidebar footer ────────────────────────────────────────────────────
        sidebar_footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        sidebar_footer.pack(side="bottom", fill="x", padx=8, pady=10)

        reset_btn = _btn(sidebar_footer, "Factory Reset", self._factory_reset,
                         width=114, fg=DANGER, hover=DANGER_H)
        reset_btn.configure(font=ctk.CTkFont(size=11))
        reset_btn.pack(fill="x")

        self._footer_status = _label(sidebar_footer, "", size=10, color=MUTED)
        self._footer_status.pack(pady=(0, 6))

        # ── Content pages ─────────────────────────────────────────────────────
        self._pages: dict[str, ctk.CTkFrame] = {}

        btns_page = ctk.CTkFrame(self._content, fg_color="transparent")
        self._btns_tab = ButtonsTab(btns_page, self.config, self)
        self._btns_tab.pack(fill="both", expand=True)
        self._pages["Buttons"] = btns_page

        dpi_page = ctk.CTkFrame(self._content, fg_color="transparent")
        self._dpi_tab = DPITab(dpi_page, self.config, self.device)
        self._dpi_tab.pack(fill="both", expand=True)
        self._pages["DPI"] = dpi_page

        macros_page = ctk.CTkFrame(self._content, fg_color="transparent")
        self._macros_tab = MacrosTab(macros_page, self.config,
                                     on_macros_changed=self._on_macros_changed)
        self._macros_tab.pack(fill="both", expand=True)
        self._pages["Macros"] = macros_page

        lighting_page = ctk.CTkFrame(self._content, fg_color="transparent")
        self._light_tab = LightingTab(lighting_page, self.config, self.device)
        self._light_tab.pack(fill="both", expand=True)
        self._pages["Lighting"] = lighting_page

        # Show default page
        self._current_page: str | None = None
        self._show_page("Buttons")

    # ── Page switching ────────────────────────────────────────────────────────

    def _show_page(self, name: str):
        if self._current_page == name:
            return
        # Hide current page
        if self._current_page and self._current_page in self._pages:
            self._pages[self._current_page].pack_forget()
        # Show new page
        self._pages[name].pack(fill="both", expand=True)
        self._current_page = name
        # Update nav button styles
        for btn_name, btn in self._nav_buttons.items():
            if btn_name == name:
                btn.configure(fg_color=SURFACE, text_color=ACCENT,
                              font=ctk.CTkFont(size=13, weight="bold"))
            else:
                btn.configure(fg_color="transparent", text_color=MUTED,
                              font=ctk.CTkFont(size=13, weight="normal"))

    # ── Device connection ─────────────────────────────────────────────────────

    def _connect_device(self):
        ok = self.device.connected
        if ok:
            self._conn_label.configure(text="Razer Viper Mini", text_color=SUCCESS)
        else:
            self._conn_label.configure(text="Device not found", text_color=ERROR)
            self.after(5000, self._connect_device)

    # ── Remapper ──────────────────────────────────────────────────────────────

    def _poll_button_clicks(self):
        """Quartz-based click detection — works even when macOS swallows tkinter events."""
        try:
            import Quartz as _Q
            pressed = _Q.CGEventSourceButtonState(
                _Q.kCGEventSourceStateCombinedSessionState,
                _Q.kCGMouseButtonLeft)
            if pressed and not self._btn_was_pressed:
                x, y = self.winfo_pointerxy()
                w = self.winfo_containing(x, y)
                for _ in range(12):
                    if w is None:
                        break
                    vf = getattr(w, '_viper_fire', None)
                    if vf is not None:
                        vf()
                        break
                    try:
                        w = w.master
                    except Exception:
                        break
            self._btn_was_pressed = bool(pressed)
        except Exception:
            pass
        self.after(10, self._poll_button_clicks)

    def _drain_action_queue(self):
        try:
            while True:
                func = _action_queue.get_nowait()
                func()
        except Exception:
            pass
        self.after(20, self._drain_action_queue)

    def _start_remapper(self):
        if not ButtonRemapper.accessibility_ok():
            self._acc_bar.pack(fill="x")
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
                text="Sent reset (unconfirmed)", text_color=WARNING)

        self.after(4000, lambda: self._footer_status.configure(text=""))

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_macros_changed(self):
        self._btns_tab.refresh()

    def on_close(self):
        self.remapper.stop()
        self.device.disconnect()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
