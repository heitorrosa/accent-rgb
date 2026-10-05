# accent-rgb

Background script that paints a MonsGeek FUN60 Pro the current Windows accent color.

Protocol vendored (single file, MIT) from
[Lightning-13/monsgeek-rgb](https://github.com/Lightning-13/monsgeek-rgb) -
`monsgeek_rgb/protocol.py` + `devices.py` inlined into `accent_rgb.py`, so the
only install is `hidapi`. HID packet: 65-byte feature report
`07 01 04 04 08 RR GG BB checksum` to VID `0x3151` / PID `0x5026` (2.4 GHz) or
`0x502F` (wired), interface 2.

## Accent source (registry)

First key that exists wins; DWORD layout is `0xAABBGGRR` (R = low byte):

| Priority | Key | Value |
|---|---|---|
| 1 | `HKCU\SOFTWARE\Microsoft\Windows\DWM` | `AccentColor` |
| 2 | `HKCU\...\Explorer\Accent` | `AccentColorMenu` |
| 3 | `HKCU\SOFTWARE\Microsoft\Windows\DWM` | `ColorizationColor` (fallback) |

## Run

```powershell
pip install -r requirements.txt
python accent_rgb.py --check        # show accent, don't touch keyboard
python accent_rgb.py --once -v      # set once, verbose
python accent_rgb.py                # poll every 3s, update only on change
pythonw.exe accent_rgb.py           # background, no console window
```

Autostart: <kbd>Win</kbd>+<kbd>R</kbd> → `shell:startup` → shortcut to
`pythonw.exe "C:\path\to\accent-rgb\accent_rgb.py"`.

## Why change-only writes

The Custom Layer commits to flash (see upstream `docs/limitations.md`).
The script polls the registry but only sends a HID report when the RGB value
actually changes, so it won't wear flash or flicker.

## Calibration (keyboard lies about colors)

LEDs + diffuser shift hues, so the accent on screen never matches the keys.
Fix: `python calibrate.py` opens all 20 target swatches in your browser,
puts each one on the keyboard, and asks what RGB *looks* right (Enter =
accept, `q` = save + resume later). It fits a 3x4 color-correction matrix
(least squares, stdlib only) into `calibration.json`, which `accent_rgb.py`
then applies to every update. `python calibrate.py --refit` re-fits from
saved pairs without re-tuning.

## Files

- `accent_rgb.py` - the whole app (registry read + HID + poll loop)
- `calibrate.py` - one-time tuning UI + matrix fit
- `calibration.json` - your pairs + fitted matrix (gitignored, personal)
- `requirements.txt` - `hidapi`

## License

Licensed with GPL-3.0-or-later, see LICENSE.
