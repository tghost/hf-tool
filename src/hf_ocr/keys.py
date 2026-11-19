"""Raw evdev keyboard reader.

The device has no touch input, so every interaction must come from the 46-key
TCA8418 keypad. The python3-evdev module is not installed on the device, so we
talk to the kernel input interface directly: open /dev/input/eventN, select on
it, and decode the classic `struct input_event` layout.

Key codes below are the real values from Linux input-event-codes.h. The
cardputer keypad driver reports standard codes (verified against the EV_KEY
capability bitmap of /dev/input/event3), so no remapping table is needed.
"""

import glob
import os
import select
import struct

EVENT_FORMAT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

EV_KEY = 0x01
KEY_PRESS = 0x01

# The keypad is exposed through a stable by-path symlink; fall back to a scan
# of /dev/input/event* matched by device name.
BY_PATH = "/dev/input/by-path/platform-3f804000.i2c-event"

# Linux input-event-codes.h subset that matters for this keypad.
KEY_CODES = {
    1: "ESC",
    2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8",
    10: "9", 11: "0",
    12: "MINUS", 13: "EQUAL", 14: "BACKSPACE", 15: "TAB",
    16: "Q", 17: "W", 18: "E", 19: "R", 20: "T", 21: "Y", 22: "U", 23: "I",
    24: "O", 25: "P", 26: "LBRACKET", 27: "RBRACKET",
    28: "ENTER", 29: "LEFTCTRL",
    30: "A", 31: "S", 32: "D", 33: "F", 34: "G", 35: "H", 36: "J", 37: "K",
    38: "L", 39: "SEMICOLON", 40: "APOSTROPHE", 41: "GRAVE", 42: "LEFTSHIFT",
    43: "BACKSLASH", 44: "Z", 45: "X", 46: "C", 47: "V", 48: "B", 49: "N",
    50: "M", 51: "COMMA", 52: "DOT", 53: "SLASH", 54: "RIGHTSHIFT",
    55: "KPSTAR", 56: "LEFTALT", 57: "SPACE", 58: "CAPSLOCK",
    59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6", 65: "F7",
    66: "F8", 67: "F9", 68: "F10", 87: "F11", 88: "F12",
    # Numeric keypad (layer 1 of the device keymap).
    71: "KP7", 72: "KP8", 73: "KP9", 74: "KPMINUS",
    75: "KP4", 76: "KP5", 77: "KP6", 78: "KP1", 79: "KP2", 80: "KP3",
    81: "KP0", 82: "KPDOT", 83: "KPENTER",
    96: "KPENTER", 97: "RIGHTCTRL", 98: "KPSLASH", 99: "SYSRQ",
    100: "RIGHTALT", 101: "LINEFEED",
    102: "HOME", 103: "UP", 104: "PAGEUP", 105: "LEFT", 106: "RIGHT",
    107: "END", 108: "DOWN", 109: "PAGEDOWN", 110: "INSERT", 111: "DELETE",
    119: "PAUSE", 125: "LEFTMETA", 126: "RIGHTMETA", 127: "COMPOSE",
    138: "HELP", 163: "KEY_163", 164: "KEY_164", 165: "KEY_165",
    224: "KEY_224", 225: "KEY_225", 383: "KEY_383", 389: "KEY_389",
}

# Physical keys that stand in for navigation, so the app stays usable no matter
# which of them the user reaches for first.
#
# The 46-key TCA8418 reports standard Linux codes, but the reported code
# depends on the modifier that is held, so one physical key yields different
# codes per layer. Decoded from the device DTS (3 x 46-entry linux,keymap
# tables, 5 rows x 10 columns):
#
#   base : number row  2 3 4 5 6 7 8 9 0 BKSP   /  QWERTY..  /  A..L ENT
#           Z X C V B N M  +  FN turns Z X C F into LEFT DOWN RIGHT UP
#   SYM  : punctuation on the number row, KP7..KP0 on the letter rows
#   FN   : F1..F12 on the number row, INS/END/PGDN on the bottom letter row
#
# Every navigation action therefore accepts several spellings:
#   - the plain digit on the base layer     ("4", "6", "2", "8")
#   - the FN-layer arrow cluster            ("LEFT", "RIGHT", "UP", "DOWN")
#     whose physical keys are Z / C / F / X
#   - the SYM-layer keypad twin             ("KP4", "KP6", "KP8", "KP5")
#
# Scheme used by the UI hints: 4 = back, 6 = forward, 2 = up, 8 = down.
NEXT_KEYS = ("RIGHT", "KP6", "6", "C")
PREV_KEYS = ("LEFT", "KP4", "4", "Z")
UP_KEYS = ("UP", "KP8", "2", "F")
DOWN_KEYS = ("DOWN", "KP5", "8", "X")
CONFIRM_KEYS = ("ENTER", "KPENTER", "SPACE")
BACK_KEYS = ("ESC", "BACKSPACE")


def _device_name(path):
    base = "/sys/class/input/%s/device/name" % os.path.basename(path)
    try:
        with open(base, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


class Keyboard:
    """Reads key presses from the cardputer keypad."""

    def __init__(self, device=None):
        self.device = device or self._discover()
        self._fh = None
        if self.device:
            try:
                self._fh = open(self.device, "rb", buffering=0)
            except OSError:
                self._fh = None

    @staticmethod
    def _discover():
        if os.path.exists(BY_PATH):
            return BY_PATH
        preferred = []
        fallback = []
        for path in sorted(glob.glob("/dev/input/event*")):
            name = _device_name(path).lower()
            if not name:
                continue
            if "tca8418" in name or "cardputer" in name:
                preferred.append(path)
            elif "kbd" in name or "keyboard" in name:
                fallback.append(path)
        return (preferred or fallback or [None])[0]

    def read_key(self, timeout=None):
        """Block until a key is pressed. Returns a key name, or None on timeout."""
        if not self._fh:
            return None
        ready, _, _ = select.select([self._fh], [], [], timeout)
        if not ready:
            return None
        while True:
            data = self._fh.read(EVENT_SIZE)
            if data is None or len(data) < EVENT_SIZE:
                return None
            _, _, etype, code, value = struct.unpack(EVENT_FORMAT, data)
            if etype != EV_KEY or value != KEY_PRESS:
                continue
            return KEY_CODES.get(code, "KEY%d" % code)

    def close(self):
        if self._fh:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
