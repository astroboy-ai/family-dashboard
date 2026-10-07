"""Generate the FamilyOS PWA icons.

Matches the in-app brand mark: a green rounded square with a white "F". Drawn
with Pillow rather than a converter so it is reproducible and needs no extra
tooling; re-run this script to regenerate after a palette change.

Run:  /tmp/iconvenv/bin/python make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ACCENT = (23, 101, 76, 255)       # --accent  #17654c
ON_ACCENT = (255, 255, 255, 255)  # --on-accent
OUT = Path(__file__).resolve().parent.parent / "public"


def find_font(size: int) -> ImageFont.FreeTypeFont:
    """A heavy sans face, wherever this machine keeps one."""
    candidates = [
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("no bold sans font found; install dejavu or liberation")


def rounded_mark(size: int, radius_ratio: float = 0.22, inset_ratio: float = 0.0,
                 background=ACCENT, glyph_ratio: float = 0.60) -> Image.Image:
    """A green rounded square with a centred white F.

    ``inset_ratio`` shrinks the square inside the canvas, which is what a
    maskable icon needs: Android crops maskable icons to a circle, so the mark
    must stay well inside the safe zone.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    inset = int(size * inset_ratio)
    box = (inset, inset, size - inset, size - inset)
    side = box[2] - box[0]
    draw.rounded_rectangle(box, radius=int(side * radius_ratio), fill=background)

    font = find_font(int(side * glyph_ratio))
    # Anchor "mm" centres on the glyph's optical middle, which looks better than
    # centring the text box (the F has no descender).
    draw.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), "F",
              font=font, fill=ON_ACCENT, anchor="mm")
    return img


def main() -> None:
    # Standard icons: the mark fills the canvas.
    rounded_mark(192).save(OUT / "icon-192.png")
    rounded_mark(512).save(OUT / "icon-512.png")
    # Maskable: Android crops to a circle, so keep the mark inside the safe zone.
    rounded_mark(512, inset_ratio=0.12, radius_ratio=0.26, glyph_ratio=0.46).save(
        OUT / "icon-maskable-512.png"
    )
    # iOS ignores the manifest icons and uses this one; it adds its own corners.
    rounded_mark(180, radius_ratio=0.0).save(OUT / "apple-touch-icon.png")
    # A 32px favicon keeps the browser tab consistent with the installed app.
    rounded_mark(32, radius_ratio=0.18, glyph_ratio=0.66).save(OUT / "favicon-32.png")

    for name in ("icon-192.png", "icon-512.png", "icon-maskable-512.png",
                 "apple-touch-icon.png", "favicon-32.png"):
        path = OUT / name
        with Image.open(path) as im:
            print(f"{name:26} {im.size[0]}x{im.size[1]}  {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
