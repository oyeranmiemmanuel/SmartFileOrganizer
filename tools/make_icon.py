"""Create assets/icon.ico (needs Pillow: python -m pip install -r requirements-build.txt)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
BLUE = (47, 111, 214, 255)
WHITE = (255, 255, 255, 255)
LIGHT = (214, 228, 252, 255)


def build_image() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=48, fill=BLUE)
    draw.rounded_rectangle((44, 78, 116, 112), radius=10, fill=LIGHT)  # folder tab
    draw.rounded_rectangle((44, 96, 212, 190), radius=14, fill=WHITE)  # folder body
    draw.line([(88, 142), (116, 168), (170, 116)], fill=BLUE, width=14, joint="curve")  # tick mark
    return image


def main() -> None:
    target = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    target.parent.mkdir(parents=True, exist_ok=True)
    build_image().save(
        target,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Created {target}")


if __name__ == "__main__":
    main()