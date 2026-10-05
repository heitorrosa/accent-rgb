"""Sync MonsGeek FUN60 Pro static color to the Windows accent color.

Reads the accent DWORD from the registry and sends it to the keyboard
over USB HID (same packet as Lightning-13/monsgeek-rgb).

Runs in the foreground by default; use pythonw.exe or --once for background use.
Only writes to the keyboard when the accent actually changes -- the Custom
Layer commits to flash, so spamming it on a timer would wear it out.

Registry sources (first hit wins):
  HKCU\\SOFTWARE\\Microsoft\\Windows\\DWM\\AccentColor
  HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Accent\\AccentColorMenu
  HKCU\\SOFTWARE\\Microsoft\\Windows\\DWM\\ColorizationColor (fallback)

DWORD layout is 0xAABBGGRR, so R = low byte.

Usage:
  pip install -r requirements.txt
  python accent_rgb.py              # poll every 3s, update on change
  pythonw.exe accent_rgb.py         # same, no console window (background)
  python accent_rgb.py --once       # set once and exit
  python accent_rgb.py --check      # print accent, don't touch keyboard
"""

import argparse
import time
import winreg

# ponytail: vendored from Lightning-13/monsgeek-rgb (MIT) so this repo stays one file.
# Upstream: https://github.com/Lightning-13/monsgeek-rgb (monsgeek_rgb/protocol.py, devices.py)
SUPPORTED_DEVICES = [
    {"vendor_id": 0x3151, "product_id": 0x5026, "usage_page": 0xFFFF, "usage": 0x02},  # FUN60 Pro 2.4 GHz (upstream)
    {"vendor_id": 0x3151, "product_id": 0x502F, "usage_page": 0xFFFF, "usage": 0x02},  # FUN60 Pro wired (upstream)
    {"vendor_id": 0x3151, "product_id": 0x502D, "usage_page": 0xFFFF, "usage": 0x02},  # observed MI_02 on this machine
]


def _checksum(data: bytes) -> int:
    return (0xFF - (sum(data) & 0xFF)) & 0xFF


def static_color_packet(r: int, g: int, b: int) -> bytes:
    if not all(0 <= x <= 255 for x in (r, g, b)):
        raise ValueError("RGB values must be between 0 and 255.")
    p = bytearray(65)
    p[1], p[2], p[3], p[4], p[5] = 0x07, 0x01, 0x04, 0x04, 0x08
    p[6], p[7], p[8] = r, g, b
    p[9] = _checksum(p[1:9])
    return bytes(p)


def find_keyboard_path():
    import hid  # ponytail: import here so --check works without hidapi installed

    for d in hid.enumerate():
        for s in SUPPORTED_DEVICES:
            if (d["vendor_id"], d["product_id"], d.get("usage_page"), d.get("usage")) == (
                s["vendor_id"], s["product_id"], s["usage_page"], s["usage"]):
                return d["path"]
    return None


def set_keyboard(r: int, g: int, b: int) -> None:
    import hid

    path = find_keyboard_path()
    if path is None:
        raise RuntimeError("Compatible MonsGeek keyboard not found (0x3151:0x5026/0x502F/0x502D).")
    dev = hid.device()
    try:
        dev.open_path(path)
        dev.send_feature_report(static_color_packet(r, g, b))
    finally:
        dev.close()


ACCENT_KEYS = [
    (r"SOFTWARE\Microsoft\Windows\DWM", "AccentColor"),
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent", "AccentColorMenu"),
    (r"SOFTWARE\Microsoft\Windows\DWM", "ColorizationColor"),  # fallback
]


def read_accent_dword() -> tuple[int, str]:
    """Return (dword, 'subkey\\value') for the first registry key that exists."""
    for subkey, value in ACCENT_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as k:
                dword, _ = winreg.QueryValueEx(k, value)
                return int(dword), f"{subkey}\\{value}"
        except OSError:
            continue
    raise RuntimeError("No Windows accent color found in registry (DWM\\AccentColor missing).")


def dword_to_rgb(dword: int) -> tuple[int, int, int]:
    dword &= 0xFFFFFFFF
    return dword & 0xFF, (dword >> 8) & 0xFF, (dword >> 16) & 0xFF  # 0xAABBGGRR


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync MonsGeek RGB to Windows accent color.")
    ap.add_argument("--once", action="store_true", help="set once and exit")
    ap.add_argument("--check", action="store_true", help="print accent color, don't touch keyboard")
    ap.add_argument("--poll", type=float, default=3.0, help="registry poll interval in seconds (default 3)")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    def log(*m):
        if args.verbose or args.check:
            print(*m, flush=True)

    if args.check:
        dword, src = read_accent_dword()
        r, g, b = dword_to_rgb(dword)
        print(f"{src} = {dword} (0x{dword:08X}) -> RGB({r}, {g}, {b}) #{r:02X}{g:02X}{b:02X}")
        return 0

    last = None
    while True:
        try:
            dword, src = read_accent_dword()
        except RuntimeError as e:
            print(f"registry: {e}", flush=True)
            if args.once:
                return 1
            time.sleep(args.poll)
            continue
        rgb = dword_to_rgb(dword)
        if rgb != last:
            try:
                set_keyboard(*rgb)
            except Exception as e:  # keyboard unplugged, hid missing, etc. -- retry next poll
                print(f"keyboard: {e}", flush=True)
                if args.once:
                    return 1
            else:
                log(f"set #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X} from {src}")
                last = rgb
        if args.once:
            return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
