"""Render the app icon (assets/icon.ico for the .exe, assets/icon.png for the
window) - the same wireframe cube the app draws, with see-through faces.

Each icon size is drawn separately (4x supersampled) instead of being scaled
down from the big one, so the small sizes keep crisp, thick enough edges.
"""

import os

from PIL import Image, ImageDraw

import main

SIZES = [16, 24, 32, 48, 64, 128, 256]
SUPERSAMPLE = 4
BACKGROUND = (16, 20, 28, 255)
EDGE = (0, 255, 0)


def render(size):
    big = size * SUPERSAMPLE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 6, fill=BACKGROUND)

    cube = main.Cube()
    verts_3d = cube.transformed_vertices()
    xs = [x for x, _, _ in verts_3d]
    ys = [-y for _, y, _ in verts_3d]  # screen y points down
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    scale = big * 0.72 / span
    off_x = big / 2 - (max(xs) + min(xs)) / 2 * scale
    off_y = big / 2 - (max(ys) + min(ys)) / 2 * scale
    points = [(x * scale + off_x, y * scale + off_y) for x, y in zip(xs, ys)]

    line_width = max(1, round(size / 40)) * SUPERSAMPLE
    draw = ImageDraw.Draw(image)
    for a, b in main.CUBE_EDGES:
        draw.line([points[a], points[b]], fill=EDGE, width=line_width)
    return image.resize((size, size), Image.LANCZOS)


def build():
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    os.makedirs(out_dir, exist_ok=True)
    images = [render(size) for size in SIZES]
    images[-1].save(
        os.path.join(out_dir, "icon.ico"),
        sizes=[(s, s) for s in SIZES],
        append_images=images[:-1],
    )
    render(64).save(os.path.join(out_dir, "icon.png"))
    print("wrote assets/icon.ico and assets/icon.png")


if __name__ == "__main__":
    build()
