"""Makes the picture files in assets/ from raw_art/. Run this on your computer:

    python make_assets.py

It only uses Pillow. main.py never imports this file or Pillow: it just loads
the finished PNG files from assets/.
"""

import json
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw_art")
OUT = os.path.join(HERE, "assets")


def load_config():
    with open(os.path.join(HERE, "data", "game.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)


def enlarge(image, scale):
    """Bigger, but sharp: every source pixel becomes a square of pixels."""
    return image.resize((image.width * scale, image.height * scale), Image.NEAREST)


def copy_sprite(name, scale):
    image = Image.open(os.path.join(RAW, name)).convert("RGBA")
    return enlarge(image, scale)


def tinted_gem(scale, dark, bright):
    """Recolour gem.png into a bright crystal: dark body, light facets, white sparkle."""
    image = Image.open(os.path.join(RAW, "gem.png")).convert("RGBA")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            light = max(r, g, b) / 255.0
            out = []
            for channel in range(3):
                base = dark[channel]
                top = bright[channel]
                if light > 0.8:
                    value = base + (top - base) * 0.8 + (255 - (base + (top - base) * 0.8)) * ((light - 0.8) / 0.2)
                else:
                    value = base + (top - base) * (light / 0.8)
                out.append(int(max(0, min(255, value))))
            pixels[x, y] = (out[0], out[1], out[2], a)
    return enlarge(image, scale)


def main():
    config = load_config()["pictures"]
    scale = config["scale"]
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    made = []
    for name in sorted(os.listdir(RAW)):
        if name.endswith(".png") and name != "gem.png":
            copy_sprite(name, scale).save(os.path.join(OUT, name))
            made.append(name)
    for gem in config["gems"]:
        tinted_gem(scale, gem["dark"], gem["bright"]).save(os.path.join(OUT, gem["file"]))
        made.append(gem["file"])
    size = scale * 16
    print("wrote %d files to assets/ (%d x %d pixels):" % (len(made), size, size))
    for name in made:
        print("  " + name)


if __name__ == "__main__":
    main()
