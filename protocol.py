"""
Low-level Razer HID feature-report protocol for the Viper Mini.

91-byte buffer layout (report-ID byte 0 + 90-byte payload):
  [0]    Report ID   = 0x00
  [1]    Status      = 0x00  (0=new, 2=success, 3=fail)
  [2]    Transaction ID
  [3-4]  Remaining packets = 0x00 0x00
  [5]    Protocol type = 0x00
  [6]    Data size   = len(args)
  [7]    Command class
  [8]    Command ID
  [9-88] Arguments   (padded with 0x00)
  [89]   CRC         = XOR of bytes [3..88]
  [90]   Reserved    = 0x00
"""

RAZER_VID       = 0x1532
VIPER_MINI_PID  = 0x008A
USAGE_PAGE      = 0xFF00   # Razer vendor-specific control interface

TID = 0xFF  # default transaction ID


def _crc(buf: bytearray) -> int:
    result = 0
    for i in range(3, 89):
        result ^= buf[i]
    return result


def make_report(cmd_class: int, cmd_id: int, args: bytes = b"") -> bytearray:
    """Build a 91-byte Razer feature report."""
    assert len(args) <= 80, f"Too many arg bytes: {len(args)}"
    buf = bytearray(91)
    buf[0] = 0x00
    buf[1] = 0x00
    buf[2] = TID
    buf[5] = 0x00
    buf[6] = len(args)
    buf[7] = cmd_class
    buf[8] = cmd_id
    for i, b in enumerate(args):
        buf[9 + i] = b
    buf[89] = _crc(buf)
    return buf


# ── Command constants ──────────────────────────────────────────────────────────

# DPI
CLS_DPI       = 0x04
CMD_DPI_SET   = 0x05   # args: [stage, x_hi, x_lo, y_hi, y_lo, 0x00]
CMD_DPI_GET   = 0x85   # same layout, read-back variant

# Lighting  (standard Razer Chroma matrix, class 0x03)
CLS_LIGHT     = 0x03
CMD_LIGHT_SET = 0x01   # args: [variable_storage, led_id, effect, 0,0, r,g,b,...]

LED_LOGO      = 0x04
LED_SCROLL    = 0x01

EFX_NONE      = 0x00
EFX_STATIC    = 0x01
EFX_BREATHE   = 0x03
EFX_SPECTRUM  = 0x04
EFX_REACTIVE  = 0x05
