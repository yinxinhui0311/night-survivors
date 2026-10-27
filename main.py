"""Night Survivors: window, camera, drawing and input.

Run make_assets.py once to create assets/, then:  python main.py
"""

import asyncio
import math
import os
import random

import pygame as pg

import rules

FPS = 60
STEP = 1.0 / FPS
MAX_STEPS_PER_FRAME = 5
HERE = os.path.dirname(os.path.abspath(__file__))

COLOR_BG = (24, 28, 40)
COLOR_SPARK = (255, 224, 120)
COLOR_HP_BACK = (70, 70, 80)
COLOR_HP = (220, 70, 80)
COLOR_XP = (90, 160, 255)
COLOR_RING = (255, 240, 170)
COLOR_TEXT = (235, 235, 240)
COLOR_CARD = (44, 50, 70)
COLOR_CARD_EDGE = (120, 140, 190)
COLOR_FLASH = (255, 255, 255)
COLOR_DAMAGE = (255, 240, 200)


class Input:
    """Keeps where the hero should walk, in screen pixels."""

    def __init__(self):
        self.touch = None      # (x, y) while a finger is down
        self.mouse = (0.0, 0.0)
        self.using_touch = False

    def pointer(self):
        """None means: nothing points anywhere, so the hero stands still."""
        if self.using_touch:
            return self.touch
        return self.mouse


def make_font(size):
    return pg.font.Font(None, size)


def load_pictures(config):
    """Load the finished PNG files made by make_assets.py."""
    folder = os.path.join(HERE, config["pictures"]["folder"])
    names = [entry["picture"] for entry in config.values() if isinstance(entry, dict) and "picture" in entry]
    names += list(config["gems"]["picture_by_xp"].values())
    pictures = {}
    for name in names:
        if name in pictures:
            continue
        path = os.path.join(folder, name)
        try:
            pictures[name] = pg.image.load(path).convert_alpha()
        except pg.error:
            raise SystemExit("missing %s - run:  python make_assets.py" % path)
    return pictures


def load_sounds(config):
    """Load the finished .wav files made by make_sounds.py. Empty if there is no audio."""
    conf = config["sounds"]
    folder = os.path.join(HERE, conf["folder"])
    paths = {name: os.path.join(folder, filename) for name, filename in conf["files"].items()}
    if not pg.mixer.get_init():
        try:
            pg.mixer.init()
        except pg.error:
            print("no sound device: playing without sound")
            return {}
    try:
        sounds = {name: pg.mixer.Sound(path) for name, path in paths.items()}
    except (pg.error, FileNotFoundError):
        print("sounds did not load - run:  python make_sounds.py")
        return {}
    for sound in sounds.values():
        sound.set_volume(conf["volume"])
    return sounds


def play_events(sounds, state, last_play, now):
    """Play each sound that happened this frame, but not twice in a row too fast."""
    cooldown = state["config"]["sounds"]["cooldown"]
    for name in rules.take_events(state):
        sound = sounds.get(name)
        if sound is None:
            continue
        if now - last_play.get(name, -1e9) < cooldown.get(name, 0.0) * 1000.0:
            continue
        last_play[name] = now
        sound.play()


def draw_effects(screen, state, fonts, cam_x, cam_y):
    """A white flash where an enemy died, and the damage numbers floating up."""
    feel = state["config"]["feel"]
    total = feel["death_flash_seconds"]
    for flash in state["flashes"]:
        grow = 1.0 - flash["life"] / total
        radius = int(feel["death_flash_radius"] * (0.4 + grow))
        pg.draw.circle(screen, COLOR_FLASH, (int(flash["x"] - cam_x), int(flash["y"] - cam_y)), radius, 3)
    for floater in state["floaters"]:
        img = fonts["small"].render(str(floater["amount"]), True, COLOR_DAMAGE)
        screen.blit(img, (int(floater["x"] - cam_x) - img.get_width() // 2,
                          int(floater["y"] - cam_y) - img.get_height()))


def draw_floor(screen, pictures, config, cam_x, cam_y, width, height):
    """One floor tile repeated forever, so the map looks endless."""
    tile = pictures[config["floor"]["picture"]]
    size = tile.get_width()
    start_x = int(cam_x // size) * size
    start_y = int(cam_y // size) * size
    y = start_y
    while y < cam_y + height:
        x = start_x
        while x < cam_x + width:
            screen.blit(tile, (int(x - cam_x), int(y - cam_y)))
            x += size
        y += size


def draw_centered(screen, picture, x, y, scale=1):
    """Draw a picture with its middle at (x, y), bigger when the design says so."""
    if scale != 1:
        side = picture.get_width() * scale
        picture = pg.transform.scale(picture, (side, side))
    rect = picture.get_rect(center=(int(x), int(y)))
    screen.blit(picture, rect)


def draw_world(screen, state, pictures, cam_x, cam_y):
    config = state["config"]
    gem_pictures = config["gems"]["picture_by_xp"]
    for gem in state["gems"]:
        draw_centered(screen, pictures[gem_pictures[str(gem["xp"])]], gem["x"] - cam_x, gem["y"] - cam_y)
    ring = rules.ring_stats(state)
    if ring:
        hero = state["hero"]
        pg.draw.circle(screen, COLOR_RING, (int(hero["x"] - cam_x), int(hero["y"] - cam_y)),
                       int(ring["radius"]), 3)
    for enemy in state["enemies"]:
        conf = config[enemy["type"]]
        draw_centered(screen, pictures[conf["picture"]], enemy["x"] - cam_x, enemy["y"] - cam_y,
                      conf.get("picture_scale", 1))
    for spark in state["sparks"]:
        r = config["spark_wand"]["spark_radius"]
        pg.draw.circle(screen, COLOR_SPARK, (int(spark["x"] - cam_x), int(spark["y"] - cam_y)), r)
    blades = rules.blade_stats(state)
    if blades:
        hero = state["hero"]
        sword = pictures[config["spin_blades"]["picture"]]
        for bx, by in rules.blade_positions(state):
            point = -math.degrees(math.atan2(by - hero["y"], bx - hero["x"])) - 90
            draw_centered(screen, pg.transform.rotate(sword, point), bx - cam_x, by - cam_y)
    hero = state["hero"]
    conf = config["hero"]
    draw_centered(screen, pictures[conf["picture"]], hero["x"] - cam_x, hero["y"] - cam_y)


def clock_text(seconds):
    return "%d:%02d" % (int(seconds) // 60, int(seconds) % 60)


def draw_hud(screen, state, fonts, size):
    hero = state["hero"]
    hp_bar = pg.Rect(12, 12, 150, 14)
    pg.draw.rect(screen, COLOR_HP_BACK, hp_bar)
    ratio = max(0.0, hero["hp"] / rules.max_hp(state))
    if ratio > 0:
        pg.draw.rect(screen, COLOR_HP, (hp_bar.x, hp_bar.y, int(hp_bar.width * ratio), hp_bar.height))
    hp_text = fonts["small"].render("%d HP" % max(0, int(round(hero["hp"]))), True, COLOR_TEXT)
    screen.blit(hp_text, (hp_bar.right + 8, hp_bar.y))

    xp_bar = pg.Rect(12, hp_bar.bottom + 6, 150, 10)
    pg.draw.rect(screen, COLOR_HP_BACK, xp_bar)
    xp_ratio = max(0.0, min(1.0, state["xp"] / rules.xp_next(state)))
    if xp_ratio > 0:
        pg.draw.rect(screen, COLOR_XP, (xp_bar.x, xp_bar.y, int(xp_bar.width * xp_ratio), xp_bar.height))
    level_text = fonts["small"].render("Lv %d" % state["level"], True, COLOR_TEXT)
    screen.blit(level_text, (xp_bar.right + 8, xp_bar.y - 3))

    time_text = fonts["small"].render(
        "%s / %s" % (clock_text(state["elapsed"]), clock_text(state["config"]["length"])),
        True, COLOR_TEXT)
    screen.blit(time_text, (size[0] - time_text.get_width() - 12, 12))

    items = fonts["small"].render(rules.inventory_text(state), True, COLOR_TEXT)
    screen.blit(items, (size[0] // 2 - items.get_width() // 2, size[1] - 30))


def card_rects(size, count):
    """Three big cards, stacked in the middle of a portrait screen."""
    margin = 20
    height = 150
    gap = 16
    top = (size[1] - (count * height + (count - 1) * gap)) // 2
    return [pg.Rect(margin, top + i * (height + gap), size[0] - 2 * margin, height)
            for i in range(count)]


def draw_cards(screen, state, fonts, size):
    """The level-up choice: name, the new level and one line about it."""
    overlay = pg.Surface(size)
    overlay.set_alpha(150)
    overlay.fill((0, 0, 0))
    screen.blit(overlay, (0, 0))
    title = fonts["medium"].render("Level %d - choose one" % state["level"], True, COLOR_TEXT)
    screen.blit(title, (size[0] // 2 - title.get_width() // 2, 60))
    rects = card_rects(size, len(state["cards"]))
    for rect, card in zip(rects, state["cards"]):
        pg.draw.rect(screen, COLOR_CARD, rect)
        pg.draw.rect(screen, COLOR_CARD_EDGE, rect, 3)
        name = fonts["big"].render(rules.card_name(state["config"], card), True, COLOR_TEXT)
        screen.blit(name, (rect.x + 16, rect.y + 16))
        level = rules.card_level_text(card)
        if level:
            tag = fonts["medium"].render(level, True, COLOR_XP)
            screen.blit(tag, (rect.right - tag.get_width() - 16, rect.y + 20))
        line = fonts["small"].render(rules.card_text(state["config"], card), True, COLOR_TEXT)
        screen.blit(line, (rect.x + 16, rect.y + 78))
    return rects


def draw_end(screen, state, fonts, size):
    overlay = pg.Surface(size)
    overlay.set_alpha(170)
    overlay.fill((0, 0, 0))
    screen.blit(overlay, (0, 0))
    title = fonts["big"].render("VICTORY" if state["won"] else "GAME OVER", True, COLOR_TEXT)
    cx = size[0] // 2
    screen.blit(title, (cx - title.get_width() // 2, size[1] // 2 - 70))
    lines = [
        "time %s" % clock_text(state["elapsed"]),
        "kills %d" % state["kills"],
        "level %d" % state["level"],
        "",
        "click or tap to play again",
    ]
    y = size[1] // 2 - 20
    for line in lines:
        img = fonts["small"].render(line, True, COLOR_TEXT)
        screen.blit(img, (cx - img.get_width() // 2, y))
        y += 24


async def main():
    config = rules.load_config()
    size = (config["screen"]["width"], config["screen"]["height"])

    pg.init()
    pg.display.set_mode(size)
    pg.display.set_caption("Night Survivors")
    clock = pg.time.Clock()
    screen = pg.display.get_surface()
    fonts = {"big": make_font(48), "medium": make_font(30), "small": make_font(22)}
    pictures = load_pictures(config)
    sounds = load_sounds(config)
    last_play = {}           # sound name -> last time it played, in milliseconds

    center_x, center_y = size[0] // 2, size[1] // 2
    state = rules.new_game(config)
    rules.start(state)
    inp = Input()
    inp.mouse = (float(center_x), float(center_y))   # the hero stands still until you move the pointer
    accumulator = 0.0
    paused = False
    running = True
    tap = None               # one click or tap since the last frame, in screen pixels

    while running:
        tap = None
        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False
            elif event.type == pg.KEYDOWN and event.key == pg.K_p:
                paused = not paused
            elif event.type == pg.MOUSEMOTION:
                inp.mouse = (float(event.pos[0]), float(event.pos[1]))
                inp.using_touch = False
            elif event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                inp.mouse = (float(event.pos[0]), float(event.pos[1]))
                inp.using_touch = False
                tap = inp.mouse
            elif event.type in (pg.FINGERDOWN, pg.FINGERMOTION):
                inp.touch = (event.x * size[0], event.y * size[1])
                inp.using_touch = True
                if event.type == pg.FINGERDOWN:
                    tap = inp.touch
            elif event.type == pg.FINGERUP:
                inp.touch = None

        if not state["alive"]:
            if tap is not None:
                state = rules.new_game(config)
                rules.start(state)
                accumulator = 0.0
        elif state["cards"] is not None:
            if tap is not None:
                rects = card_rects(size, len(state["cards"]))
                for index, rect in enumerate(rects):
                    if rect.collidepoint(int(tap[0]), int(tap[1])):
                        rules.choose_card(state, index)
                        break
        elif not paused:
            # the pointer on screen becomes a point in the world to walk to
            pointer = inp.pointer()
            if pointer is None:
                rules.clear_aim(state)
            else:
                rules.set_aim(state, state["hero"]["x"] + (pointer[0] - center_x),
                              state["hero"]["y"] + (pointer[1] - center_y))

        dt = clock.tick(FPS) / 1000.0
        if dt > 0.25:
            dt = 0.25
        accumulator += dt
        if paused:
            # P stops the world, so the time does not pile up while nothing runs
            accumulator = 0.0
        steps = 0
        while not paused and accumulator >= STEP and steps < MAX_STEPS_PER_FRAME:
            rules.step(state, STEP)
            accumulator -= STEP
            steps += 1
        if steps == MAX_STEPS_PER_FRAME:
            accumulator = 0.0
        play_events(sounds, state, last_play, pg.time.get_ticks())

        hero = state["hero"]
        cam_x, cam_y = hero["x"] - center_x, hero["y"] - center_y
        if state["shake"] > 0.0:
            strength = state["shake"] / config["feel"]["shake_seconds"]
            pixels = config["feel"]["shake_pixels"] * strength
            cam_x += random.uniform(-pixels, pixels)
            cam_y += random.uniform(-pixels, pixels)
        screen.fill(COLOR_BG)
        draw_floor(screen, pictures, config, cam_x, cam_y, size[0], size[1])
        draw_world(screen, state, pictures, cam_x, cam_y)
        draw_effects(screen, state, fonts, cam_x, cam_y)
        draw_hud(screen, state, fonts, size)
        if state["cards"] is not None:
            draw_cards(screen, state, fonts, size)
        if not state["alive"]:
            draw_end(screen, state, fonts, size)
        if paused and state["cards"] is None:
            img = fonts["big"].render("PAUSED", True, COLOR_TEXT)
            screen.blit(img, (center_x - img.get_width() // 2, center_y - img.get_height() // 2))
        pg.display.flip()
        await asyncio.sleep(0)

    pg.quit()


if __name__ == "__main__":
    asyncio.run(main())
