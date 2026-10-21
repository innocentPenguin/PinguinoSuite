"""Build the PinguinoSuite logo: the channel profile picture, cropped to a circle with an orange ring.
Writes App/src-tauri/icons/source.png (1024) and App/src/assets/logo.png (256). Then run, from App/:
    npx tauri icon src-tauri/icons/source.png
to regenerate icon.ico / icon.icns / the PNG sizes. Run with Suite/.venv/Scripts/python.exe (Pillow)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "PinguinoSite" / "assets" / "channel" / "profile.png"
OUT_ICON = ROOT / "App" / "src-tauri" / "icons" / "source.png"
OUT_LOGO = ROOT / "App" / "src" / "assets" / "logo.png"
ORANGE, DEEP = (255, 138, 31, 255), (214, 92, 0, 255)
N = 1024
RING = int(N * 0.075)

im = Image.open(SRC).convert("RGB")
s = min(im.size)
im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
inner = N - 2 * RING
im = im.resize((inner, inner), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))

big = Image.new("RGBA", (N * 2, N * 2), (0, 0, 0, 0))                     # draw at 2x, shrink for smooth edges
d = ImageDraw.Draw(big)
d.ellipse((0, 0, N * 2 - 1, N * 2 - 1), fill=DEEP)                          # darker outer edge
e = int(N * 0.012) * 2
d.ellipse((e, e, N * 2 - 1 - e, N * 2 - 1 - e), fill=ORANGE)
ring = big.resize((N, N), Image.LANCZOS)

mask = Image.new("L", (inner * 2, inner * 2), 0)
ImageDraw.Draw(mask).ellipse((0, 0, inner * 2 - 1, inner * 2 - 1), fill=255)
mask = mask.resize((inner, inner), Image.LANCZOS)
ring.paste(im, (RING, RING), mask)

OUT_ICON.parent.mkdir(parents=True, exist_ok=True)
OUT_LOGO.parent.mkdir(parents=True, exist_ok=True)
ring.save(OUT_ICON)
ring.resize((256, 256), Image.LANCZOS).save(OUT_LOGO)
print("wrote", OUT_ICON, OUT_LOGO)
