"""Browser KeyboardEvent.code -> Windows virtual-key code."""

from __future__ import annotations

CODE_TO_VK: dict[str, int] = {}

for i in range(26):
    CODE_TO_VK[f"Key{chr(65 + i)}"] = 0x41 + i
for i in range(10):
    CODE_TO_VK[f"Digit{i}"] = 0x30 + i
    CODE_TO_VK[f"Numpad{i}"] = 0x60 + i
for i in range(1, 25):
    CODE_TO_VK[f"F{i}"] = 0x6F + i

CODE_TO_VK.update({
    "Backspace": 0x08, "Tab": 0x09, "Enter": 0x0D, "Escape": 0x1B, "Space": 0x20,
    "PageUp": 0x21, "PageDown": 0x22, "End": 0x23, "Home": 0x24,
    "ArrowLeft": 0x25, "ArrowUp": 0x26, "ArrowRight": 0x27, "ArrowDown": 0x28,
    "PrintScreen": 0x2C, "Insert": 0x2D, "Delete": 0x2E,
    "MetaLeft": 0x5B, "MetaRight": 0x5C, "ContextMenu": 0x5D,
    "NumpadMultiply": 0x6A, "NumpadAdd": 0x6B, "NumpadSubtract": 0x6D,
    "NumpadDecimal": 0x6E, "NumpadDivide": 0x6F, "NumpadEnter": 0x0D,
    "CapsLock": 0x14, "NumLock": 0x90, "ScrollLock": 0x91, "Pause": 0x13,
    "ShiftLeft": 0xA0, "ShiftRight": 0xA1, "ControlLeft": 0xA2, "ControlRight": 0xA3,
    "AltLeft": 0xA4, "AltRight": 0xA5,
    "Semicolon": 0xBA, "Equal": 0xBB, "Comma": 0xBC, "Minus": 0xBD, "Period": 0xBE,
    "Slash": 0xBF, "Backquote": 0xC0, "BracketLeft": 0xDB, "Backslash": 0xDC,
    "BracketRight": 0xDD, "Quote": 0xDE, "IntlBackslash": 0xE2,
    # Korean keyboards: 한/영 and 한자
    "Lang1": 0x15, "Lang2": 0x19, "HangulMode": 0x15, "Hanja": 0x19,
})

# Keys that need KEYEVENTF_EXTENDEDKEY
EXTENDED_CODES = frozenset({
    "PageUp", "PageDown", "End", "Home", "ArrowLeft", "ArrowUp", "ArrowRight",
    "ArrowDown", "Insert", "Delete", "MetaLeft", "MetaRight", "ContextMenu",
    "NumpadDivide", "NumpadEnter", "ControlRight", "AltRight", "PrintScreen",
    "NumLock",
})

MODIFIER_CODES = frozenset({
    "ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight", "AltLeft",
    "AltRight", "MetaLeft", "MetaRight",
})


def lookup(code: str) -> tuple[int, bool] | None:
    vk = CODE_TO_VK.get(code)
    if vk is None:
        return None
    return vk, code in EXTENDED_CODES
