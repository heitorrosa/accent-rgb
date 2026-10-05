"""Interactive color calibration for accent-rgb.

LEDs + diffuser shift hues, so sending the accent RGB verbatim looks off.
This script walks you through ~20 target colors: it puts each one on the
keyboard AND opens a matching swatch in your browser. You type the RGB that
*looks* right to you; the script fits a 3x4 affine correction (3x3 matrix +
bias, least squares, pure stdlib) and saves it to calibration.json.
accent_rgb.py then applies it automatically on every update.

Usage:
  python calibrate.py            # tune all 20 (resumes where you left off)
  python calibrate.py --refit    # re-fit matrix from saved pairs, no tuning
"""

import json
import sys
import tempfile
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from accent_rgb import set_keyboard  # ponytail: reuse, don't re-implement HID

HERE = Path(__file__).parent
CALIB = HERE / "calibration.json"

# 20 targets: primaries, secondaries, tricky hues, grays, real Windows accents.
TARGETS = [
    "FF0000", "00FF00", "0000FF", "FFFF00", "00FFFF", "FF00FF",
    "FF8000", "8000FF", "00C0A0", "FF60A0", "80FF00", "FF0040",
    "FFFFFF", "B0B0B0", "808080", "404040", "FFD9A0", "40A0FF",
    "0078D4", "234452",
]


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def parse_rgb(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip("#").replace(",", " ")
    if len(s) == 6 and all(c in "0123456789abcdefABCDEF" for c in s):
        return hex_to_rgb(s)
    parts = [int(x) for x in s.split()]
    if len(parts) != 3 or not all(0 <= x <= 255 for x in parts):
        raise ValueError("enter R G B (0-255), a hex like ff8040, or empty to accept")
    return parts[0], parts[1], parts[2]


def solve_4x4(A, y):
    """Gaussian elimination, 4x4. A is 4x4, y is 4. Returns x."""
    M = [list(A[i]) + [y[i]] for i in range(4)]
    for col in range(4):
        piv = max(range(col, 4), key=lambda r: abs(M[r][col]))
        M[col], M[piv] = M[piv], M[col]
        for row in range(4):
            if row != col and M[row][col] != 0:
                f = M[row][col] / M[col][col]
                for k in range(col, 5):
                    M[row][k] -= f * M[col][k]
    return [M[i][4] / M[i][i] for i in range(4)]


def fit(pairs):
    """Least-squares affine map target->sent. pairs: [((tr,tg,tb),(sr,sg,sb))]."""
    n = len(pairs)
    if n < 4:
        raise ValueError(f"need >=4 pairs, have {n}")
    # Normal equations over features (r,g,b,1).
    XtX = [[0.0] * 4 for _ in range(4)]
    for (t, _) in pairs:
        f = [float(t[0]), float(t[1]), float(t[2]), 1.0]
        for i in range(4):
            for j in range(4):
                XtX[i][j] += f[i] * f[j]
    rows = []
    for ch in range(3):
        Xty = [0.0] * 4
        for (t, s) in pairs:
            f = [float(t[0]), float(t[1]), float(t[2]), 1.0]
            for i in range(4):
                Xty[i] += f[i] * float(s[ch])
        rows.append(solve_4x4(XtX, Xty))
    return rows  # 3 rows of [mr, mg, mb, bias]


def open_swatches():
    cells = "".join(
        f'<div class="c" id="s{i:02d}"><div class="s" style="background:#{h}">'
        f"</div><div>#{h}</div></div>"
        for i, h in enumerate(TARGETS)
    )
    html = (
        "<html><head><style>body{background:#111;color:#ccc;font:14px monospace}"
        ".c{display:inline-block;margin:8px;text-align:center}"
        ".s{width:120px;height:80px;border:1px solid #555}</style></head><body>"
        + cells + "</body></html>"
    )
    p = Path(tempfile.gettempdir()) / "accent-rgb-swatches.html"
    p.write_text(html)
    webbrowser.open(p.as_uri())


def collect():
    data = json.loads(CALIB.read_text()) if CALIB.exists() else {"pairs": []}
    done = {tuple(p[0]) for p in data["pairs"]}
    open_swatches()
    print("Browser has the target swatches. Keyboard shows each target;")
    print("type what LOOKS right (e.g. '255 120 40' or 'ff7828'), Enter = accept, q = save+quit.\n")
    try:
        for h in TARGETS:
            t = hex_to_rgb(h)
            if t in done:
                print(f"#{h} already tuned, skipping")
                continue
            set_keyboard(*t)
            while True:
                ans = input(f"target #{h} -> keyboard shows it. corrected RGB? ").strip()
                if ans.lower() in ("q", "quit"):
                    raise KeyboardInterrupt
                try:
                    s = t if ans == "" else parse_rgb(ans)
                    break
                except ValueError as e:
                    print(f"  {e}")
            data["pairs"].append([list(t), list(s)])
            done.add(t)
            CALIB.write_text(json.dumps(data, indent=1))
            print(f"  saved {len(data['pairs'])}/{len(TARGETS)}\n")
    except KeyboardInterrupt:
        print(f"\nprogress saved ({len(data['pairs'])}/{len(TARGETS)}). re-run to resume.")
    return data["pairs"]


def main() -> int:
    args = sys.argv[1:]
    if "--drop" in args:  # e.g. --drop 00FFFF 00C0A0 -> forget those pairs so next run re-tunes them
        i = args.index("--drop")
        hs = []
        for a in args[i + 1:]:
            if a.startswith("--"):
                break
            hs.append(a.strip().lstrip("#").upper())
        data = json.loads(CALIB.read_text()) if CALIB.exists() else {"pairs": []}
        before = len(data["pairs"])
        data["pairs"] = [p for p in data["pairs"] if "%02X%02X%02X" % tuple(p[0]) not in hs]
        CALIB.write_text(json.dumps(data, indent=1))
        print(f"dropped {before - len(data['pairs'])} pair(s); {len(data['pairs'])} remain. re-run to retune.")
        return 0
    refit_only = "--refit" in args
    pairs = None
    if not refit_only:
        pairs = collect()
    else:
        pairs = [ (tuple(p[0]), tuple(p[1]))
                  for p in json.loads(CALIB.read_text())["pairs"] ]
    if len(pairs) >= 4:
        data = json.loads(CALIB.read_text())
        data["matrix"] = fit([(tuple(a), tuple(b)) for a, b in pairs])
        CALIB.write_text(json.dumps(data, indent=1))
        [[print(f"  ch{i}: {row[0]:+.4f}*R {row[1]:+.4f}*G {row[2]:+.4f}*B {row[3]:+.2f}") for row in data["matrix"]] for i in [0]]
        print(f"fitted correction from {len(pairs)} pairs -> calibration.json")
    else:
        print(f"only {len(pairs)} pairs; need >=4 to fit. tune more, then --refit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
