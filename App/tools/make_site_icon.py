"""Build the site pop-out icon: a dark rounded tile with an orange border, the penguin in the middle and a small orange
globe badge so it reads as "the website" and differs from the Suite ring logo and the site favicon.
Writes App/src-tauri/icons/site.png (256), site.rgba (raw 256x256, embedded in the shell) and site.ico (16-256). Run with Suite/.venv/Scripts/python.exe (Pillow)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "PinguinoSite" / "assets" / "channel" / "profile.png"
OUT = ROOT / "App" / "src-tauri" / "icons"
ORANGE, DEEP, DARK = (255, 138, 31, 255), (214, 92, 0, 255), (24, 18, 14, 255)
N = 1024
S = 2  # supersample for smooth edges

def rounded(size, radius, fill):
    im = Image.new("RGBA", (size * S, size * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, size * S - 1, size * S - 1), radius * S, fill=fill)
    return im.resize((size, size), Image.LANCZOS)

tile = rounded(N, 230, ORANGE)
inner = rounded(N - 2 * 56, 180, DARK)
tile.alpha_composite(inner, (56, 56))

p = Image.open(SRC).convert("RGB")
s = min(p.size)
p = p.crop(((p.width - s) // 2, (p.height - s) // 2, (p.width + s) // 2, (p.height + s) // 2))
pw = 600
p = p.resize((pw, pw), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
mask = Image.new("L", (pw * S, pw * S), 0)
ImageDraw.Draw(mask).ellipse((0, 0, pw * S - 1, pw * S - 1), fill=255)
mask = mask.resize((pw, pw), Image.LANCZOS)
tile.paste(p, (170, 150), mask)

# globe badge, bottom-right
g = 400
badge = Image.new("RGBA", (g * S, g * S), (0, 0, 0, 0))
d = ImageDraw.Draw(badge)
d.ellipse((0, 0, g * S - 1, g * S - 1), fill=DARK)
m = 26 * S
d.ellipse((m, m, g * S - 1 - m, g * S - 1 - m), fill=ORANGE)
c, w = g * S // 2, 18 * S
lo, hi = m + 14 * S, g * S - 1 - m - 14 * S
d.ellipse((lo, lo, hi, hi), outline=DARK, width=w)                       # globe outline
d.ellipse((c - 95 * S, lo, c + 95 * S, hi), outline=DARK, width=w)       # meridian
d.line((c, lo, c, hi), fill=DARK, width=w)
d.line((lo, c, hi, c), fill=DARK, width=w)
badge = badge.resize((g, g), Image.LANCZOS)
tile.alpha_composite(badge, (N - g - 40, N - g - 40))

OUT.mkdir(parents=True, exist_ok=True)
tile.resize((256, 256), Image.LANCZOS).save(OUT / "site.png")
OUT.joinpath("site.rgba").write_bytes(tile.resize((256, 256), Image.LANCZOS).convert("RGBA").tobytes())   # raw 256x256 RGBA, embedded by windows.rs (no image-decoder feature needed)
tile.save(OUT / "site.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", OUT / "site.png", OUT / "site.ico")
