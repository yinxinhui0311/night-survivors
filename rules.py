"""Game rules for Night Survivors. No pygame in this file.

One call to `step(state, dt)` advances the world by one fixed time step.
All numbers come from data/game.json.
"""

import json
import math
import os
import random

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "game.json")


def load_config(path=DATA_PATH):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def new_game(config, rng=None):
    """A fresh world: one hero with the Spark Wand, no enemies, level 1."""
    hero_conf = config["hero"]
    return {
        "config": config,
        "rng": rng or random.Random(),
        "hero": {
            "x": 0.0,
            "y": 0.0,
            "hp": hero_conf["hp"],
        },
        "enemies": [],
        "sparks": [],
        "gems": [],
        "weapons": {"spark_wand": 1},
        "passives": {},
        "level": 1,
        "xp": 0,
        "pending_levels": 0,
        "cards": None,
        "boss_spawned": False,
        "blade_angle": 0.0,
        "ring_timer": 0.0,
        "aim": None,
        "elapsed": 0.0,
        "spawn_timer": 0.0,
        "wand_timer": 0.0,
        "kills": 0,
        "alive": False,
        "won": False,
        "floaters": [],
        "flashes": [],
        "shake": 0.0,
        "events": [],
    }


def add_event(state, kind):
    state["events"].append(kind)


def take_events(state):
    """The sounds that happened since the last frame."""
    events = state["events"]
    state["events"] = []
    return events


def start(state):
    state["alive"] = True


def set_aim(state, x, y):
    """Point the hero at a world position. He walks there and stops when close."""
    state["aim"] = (float(x), float(y))


def clear_aim(state):
    state["aim"] = None


def distance(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


# --- numbers that grow with levels -----------------------------------------

def max_hp(state):
    conf = state["config"]["passive_items"]["big_heart"]
    return state["config"]["hero"]["hp"] + conf["max_hp"] * state["passives"].get("big_heart", 0)


def hero_speed(state):
    conf = state["config"]["passive_items"]["swift_boots"]
    percent = conf["speed_percent"] * state["passives"].get("swift_boots", 0)
    return state["config"]["hero"]["speed"] * (1.0 + percent / 100.0)


def magnet_radius(state):
    conf = state["config"]["passive_items"]["magnet"]
    base = state["config"]["hero"]["magnet_radius"]
    return base + conf["magnet_radius"] * state["passives"].get("magnet", 0)


def xp_next(state):
    xp = state["config"]["xp"]
    return xp["first"] + xp["more_each_level"] * (state["level"] - 1)


def spark_stats(state):
    conf = state["config"]["spark_wand"]
    level = state["weapons"].get("spark_wand", 1)
    sparks = conf["sparks"] + sum(1 for x in conf["extra_spark_levels"] if level >= x)
    return {
        "damage": conf["damage"] + conf["damage_per_level"] * (level - 1),
        "interval": conf["interval"] - conf["interval_shorter_per_level"] * (level - 1),
        "sparks": sparks,
    }


def blade_stats(state):
    conf = state["config"]["spin_blades"]
    level = state["weapons"].get("spin_blades")
    if not level:
        return None
    blades = conf["blades"] + sum(1 for x in conf["extra_blade_levels"] if level >= x)
    return {
        "blades": blades,
        "damage": conf["damage"] + conf["damage_per_level"] * (level - 1),
        "orbit_radius": conf["orbit_radius"],
        "blade_radius": conf["blade_radius"],
        "hit_every": conf["hit_every"],
    }


def ring_stats(state):
    conf = state["config"]["holy_ring"]
    level = state["weapons"].get("holy_ring")
    if not level:
        return None
    return {
        "damage": conf["damage"] + conf["damage_per_level"] * (level - 1),
        "radius": conf["radius"] + conf["radius_per_level"] * (level - 1),
        "every": conf["every"],
    }


# --- spawning and movement --------------------------------------------------

def current_wave(state):
    """The last wave row whose time has come."""
    wave = None
    for row in state["config"]["spawn"]["waves"]:
        if state["elapsed"] >= row["from"]:
            wave = row
    return wave


def spawn_enemy(state, type_name):
    """Put one enemy on a circle around the hero, just outside the screen."""
    spawn = state["config"]["spawn"]
    if len(state["enemies"]) >= spawn["max_enemies_alive"]:
        return None
    enemy_conf = state["config"][type_name]
    enemy = {
        "type": type_name,
        "x": 0.0,
        "y": 0.0,
        "hp": enemy_conf["hp"],
        "touch_timer": 0.0,
        "blade_timers": {},
    }
    state["enemies"].append(enemy)
    place_on_circle(state, enemy)
    return enemy


def is_boss(state, enemy):
    return bool(state["config"][enemy["type"]].get("boss"))


def place_on_circle(state, enemy):
    """Move an enemy to a random point on the spawn circle around the hero."""
    spawn = state["config"]["spawn"]
    hero = state["hero"]
    angle = state["rng"].uniform(0.0, 2.0 * math.pi)
    enemy["x"] = hero["x"] + spawn["circle_radius"] * math.cos(angle)
    enemy["y"] = hero["y"] + spawn["circle_radius"] * math.sin(angle)


def handle_spawning(state, dt):
    """Once a second, top the enemy count up to the minimum for this time."""
    spawn = state["config"]["spawn"]
    state["spawn_timer"] -= dt
    if state["spawn_timer"] > 0.0:
        return
    state["spawn_timer"] += spawn["interval"]
    wave = current_wave(state)
    if wave is None:
        return
    if wave.get("boss") and not state["boss_spawned"]:
        if spawn_enemy(state, wave["boss"]):
            state["boss_spawned"] = True
    need = min(wave["min_alive"] - len(state["enemies"]), spawn["max_per_second"])
    for _ in range(max(need, 0)):
        if not spawn_enemy(state, state["rng"].choice(wave["types"])):
            break


def move_hero(state, dt):
    hero = state["hero"]
    if state["aim"] is None:
        return
    hero_conf = state["config"]["hero"]
    ax, ay = state["aim"]
    dx, dy = ax - hero["x"], ay - hero["y"]
    dist = math.hypot(dx, dy)
    if dist <= hero_conf["stop_distance"]:
        return
    step = hero_speed(state) * dt
    hero["x"] += dx / dist * step
    hero["y"] += dy / dist * step


def move_enemies(state, dt):
    hero = state["hero"]
    for enemy in state["enemies"]:
        speed = state["config"][enemy["type"]]["speed"]
        dx, dy = hero["x"] - enemy["x"], hero["y"] - enemy["y"]
        dist = math.hypot(dx, dy)
        if dist == 0.0:
            continue
        step = speed * dt
        enemy["x"] += dx / dist * step
        enemy["y"] += dy / dist * step


def cull_far_enemies(state):
    """Normal enemies that got too far away are removed; the boss is only pulled back."""
    hero = state["hero"]
    keep = []
    for enemy in state["enemies"]:
        conf = state["config"][enemy["type"]]
        dist = distance(hero["x"], hero["y"], enemy["x"], enemy["y"])
        if is_boss(state, enemy):
            if dist > conf["keep_distance"]:
                place_on_circle(state, enemy)
            keep.append(enemy)
        elif dist <= conf["cull_distance"]:
            keep.append(enemy)
    state["enemies"] = keep


# --- damage to the hero -----------------------------------------------------

def apply_contact_damage(state, dt):
    hero = state["hero"]
    reach = state["config"]["hero"]["hit_radius"]
    for enemy in state["enemies"]:
        enemy["touch_timer"] -= dt
        if enemy["touch_timer"] > 0.0:
            continue
        enemy_conf = state["config"][enemy["type"]]
        if distance(hero["x"], hero["y"], enemy["x"], enemy["y"]) > reach + enemy_conf["hit_radius"]:
            continue
        hero["hp"] -= enemy_conf["damage"]
        enemy["touch_timer"] = enemy_conf["touch_every"]
        add_event(state, "hurt")
        state["shake"] = state["config"]["feel"]["shake_seconds"]
        if hero["hp"] <= 0:
            hero["hp"] = 0
            state["alive"] = False
            add_event(state, "end")
            return


# --- weapons ----------------------------------------------------------------

def fire_spark_wand(state, dt):
    """The wand shoots the nearest enemies by itself, once every interval."""
    state["wand_timer"] -= dt
    if state["wand_timer"] > 0.0 or not state["enemies"]:
        return
    stats = spark_stats(state)
    state["wand_timer"] = stats["interval"]
    hero = state["hero"]
    wand = state["config"]["spark_wand"]
    targets = sorted(
        state["enemies"],
        key=lambda e: distance(hero["x"], hero["y"], e["x"], e["y"]),
    )[: stats["sparks"]]
    for target in targets:
        dx, dy = target["x"] - hero["x"], target["y"] - hero["y"]
        dist = math.hypot(dx, dy) or 1.0
        state["sparks"].append({
            "x": hero["x"],
            "y": hero["y"],
            "vx": dx / dist * wand["spark_speed"],
            "vy": dy / dist * wand["spark_speed"],
            "damage": stats["damage"],
            "life": wand["spark_life"],
        })


def move_sparks(state, dt):
    for spark in state["sparks"]:
        spark["x"] += spark["vx"] * dt
        spark["y"] += spark["vy"] * dt
        spark["life"] -= dt
    state["sparks"] = [s for s in state["sparks"] if s["life"] > 0.0]


def blade_positions(state):
    stats = blade_stats(state)
    if not stats:
        return []
    hero = state["hero"]
    count = stats["blades"]
    out = []
    for index in range(count):
        angle = state["blade_angle"] + index * 2.0 * math.pi / count
        out.append((
            hero["x"] + stats["orbit_radius"] * math.cos(angle),
            hero["y"] + stats["orbit_radius"] * math.sin(angle),
        ))
    return out


def spin_blades_hit(state, dt):
    """Each blade can hurt the same enemy only once every hit_every seconds."""
    stats = blade_stats(state)
    if not stats:
        return
    state["blade_angle"] = (state["blade_angle"]
                            + 2.0 * math.pi / state["config"]["spin_blades"]["turn_seconds"] * dt)
    positions = blade_positions(state)
    for enemy in list(state["enemies"]):
        enemy_conf = state["config"][enemy["type"]]
        for index, (bx, by) in enumerate(positions):
            enemy["blade_timers"][index] = enemy["blade_timers"].get(index, 0.0) - dt
            if enemy["blade_timers"][index] > 0.0:
                continue
            if distance(bx, by, enemy["x"], enemy["y"]) > stats["blade_radius"] + enemy_conf["hit_radius"]:
                continue
            enemy["blade_timers"][index] = stats["hit_every"]
            hurt_enemy(state, enemy, stats["damage"])
            if enemy not in state["enemies"]:
                break


def holy_ring_hits(state, dt):
    stats = ring_stats(state)
    if not stats:
        return
    state["ring_timer"] -= dt
    if state["ring_timer"] > 0.0:
        return
    state["ring_timer"] = stats["every"]
    hero = state["hero"]
    for enemy in list(state["enemies"]):
        if distance(hero["x"], hero["y"], enemy["x"], enemy["y"]) <= stats["radius"]:
            hurt_enemy(state, enemy, stats["damage"])


def hurt_enemy(state, enemy, damage):
    feel = state["config"]["feel"]
    enemy["hp"] -= damage
    add_event(state, "hit")
    state["floaters"].append({
        "x": enemy["x"],
        "y": enemy["y"],
        "amount": int(damage),
        "life": feel["damage_number_seconds"],
    })
    if enemy["hp"] <= 0:
        kill_enemy(state, enemy)


def kill_enemy(state, enemy):
    if enemy not in state["enemies"]:
        return
    state["enemies"].remove(enemy)
    state["kills"] += 1
    state["flashes"].append({
        "x": enemy["x"],
        "y": enemy["y"],
        "life": state["config"]["feel"]["death_flash_seconds"],
    })
    drop_gem(state, enemy)


def update_effects(state, dt):
    """Damage numbers float up and fade, death flashes and the shake run out."""
    feel = state["config"]["feel"]
    rise = feel["damage_number_rise"] / feel["damage_number_seconds"]
    for floater in state["floaters"]:
        floater["y"] -= rise * dt
        floater["life"] -= dt
    state["floaters"] = [f for f in state["floaters"] if f["life"] > 0.0]
    for flash in state["flashes"]:
        flash["life"] -= dt
    state["flashes"] = [f for f in state["flashes"] if f["life"] > 0.0]
    state["shake"] = max(0.0, state["shake"] - dt)


def drop_gem(state, enemy):
    xp = state["config"][enemy["type"]]["xp"]
    if xp <= 0:
        return
    state["gems"].append({"x": enemy["x"], "y": enemy["y"], "xp": xp})


def resolve_spark_hits(state):
    """A spark that reaches an enemy hurts it and disappears."""
    wand = state["config"]["spark_wand"]
    for spark in list(state["sparks"]):
        for enemy in list(state["enemies"]):
            enemy_conf = state["config"][enemy["type"]]
            if distance(spark["x"], spark["y"], enemy["x"], enemy["y"]) > enemy_conf["hit_radius"] + wand["spark_radius"]:
                continue
            state["sparks"].remove(spark)
            hurt_enemy(state, enemy, spark["damage"])
            break


# --- gems, XP and level-up cards -------------------------------------------

def move_gems(state, dt):
    """Gems inside the magnet radius fly to the hero; touching one takes it."""
    gems = state["config"]["gems"]
    hero = state["hero"]
    pull = magnet_radius(state)
    reach = state["config"]["hero"]["hit_radius"]
    left = []
    for gem in state["gems"]:
        dist = distance(hero["x"], hero["y"], gem["x"], gem["y"])
        if dist <= reach:
            add_event(state, "gem")
            gain_xp(state, gem["xp"])
            continue
        if dist <= pull:
            dx, dy = hero["x"] - gem["x"], hero["y"] - gem["y"]
            step = gems["speed"] * dt
            gem["x"] += dx / dist * step
            gem["y"] += dy / dist * step
        left.append(gem)
    state["gems"] = left


def gain_xp(state, amount):
    state["xp"] += amount
    while state["xp"] >= xp_next(state):
        state["xp"] -= xp_next(state)
        state["level"] += 1
        state["pending_levels"] += 1
        add_event(state, "level")
    if state["pending_levels"] and state["cards"] is None:
        open_cards(state)


def card_name(config, card):
    if card["kind"] == "heal":
        return "Heal"
    if card["kind"] == "passive":
        return config["passive_items"][card["key"]]["name"]
    return config[card["key"]]["name"]


def card_level_text(card):
    if card["kind"] == "heal":
        return ""
    if card["kind"] == "new_weapon":
        return "Level 1"
    return "Level %d" % card["level"]


def card_text(config, card):
    """One short line about what the card gives."""
    if card["kind"] == "heal":
        return "Heal %d HP" % config["level_up"]["heal"]
    level = card["level"]
    if card["kind"] == "new_weapon":
        return config[card["key"]]["intro"]
    if card["key"] == "spark_wand":
        conf = config["spark_wand"]
        sparks = conf["sparks"] + sum(1 for x in conf["extra_spark_levels"] if level >= x)
        return "%d damage, every %.2f s, %d sparks" % (
            conf["damage"] + conf["damage_per_level"] * (level - 1),
            conf["interval"] - conf["interval_shorter_per_level"] * (level - 1),
            sparks,
        )
    if card["key"] == "spin_blades":
        conf = config["spin_blades"]
        blades = conf["blades"] + sum(1 for x in conf["extra_blade_levels"] if level >= x)
        return "%d blades, %d damage each" % (blades, conf["damage"] + conf["damage_per_level"] * (level - 1))
    if card["key"] == "holy_ring":
        conf = config["holy_ring"]
        return "%d damage in %d px, every %.1f s" % (
            conf["damage"] + conf["damage_per_level"] * (level - 1),
            conf["radius"] + conf["radius_per_level"] * (level - 1),
            conf["every"],
        )
    conf = config["passive_items"][card["key"]]
    if card["key"] == "swift_boots":
        return "+%d%% walking speed" % conf["speed_percent"]
    if card["key"] == "big_heart":
        return "+%d max HP and heal %d" % (conf["max_hp"], conf["heal"])
    return "+%d px gem magnet" % conf["magnet_radius"]


def card_choices(state):
    """Everything the hero could take right now."""
    config = state["config"]
    options = []
    for key in config["weapons"]:
        conf = config[key]
        level = state["weapons"].get(key)
        if level is None:
            if len(state["weapons"]) < config["max_weapons"]:
                options.append({"kind": "new_weapon", "key": key, "level": 1})
        elif level < conf["max_level"]:
            options.append({"kind": "weapon_level", "key": key, "level": level + 1})
    for key, conf in config["passive_items"].items():
        level = state["passives"].get(key, 0)
        if level < conf["max_level"]:
            options.append({"kind": "passive", "key": key, "level": level + 1})
    return options


def open_cards(state):
    """Show 3 random cards, or Heal 30 HP when nothing else is left."""
    options = card_choices(state)
    count = state["config"]["level_up"]["cards"]
    if not options:
        state["cards"] = [{"kind": "heal"}]
        return
    state["cards"] = state["rng"].sample(options, min(count, len(options)))


def choose_card(state, index):
    """Take one card and go back to the game (or show the next level-up)."""
    if state["cards"] is None or index >= len(state["cards"]):
        return
    apply_card(state, state["cards"][index])
    state["cards"] = None
    state["pending_levels"] = max(0, state["pending_levels"] - 1)
    if state["pending_levels"]:
        open_cards(state)


def apply_card(state, card):
    config = state["config"]
    kind = card["kind"]
    if kind == "heal":
        heal_hero(state, config["level_up"]["heal"])
    elif kind in ("new_weapon", "weapon_level"):
        state["weapons"][card["key"]] = card["level"]
    elif kind == "passive":
        state["passives"][card["key"]] = card["level"]
        if card["key"] == "big_heart":
            heal_hero(state, config["passive_items"]["big_heart"]["heal"])


def heal_hero(state, amount):
    hero = state["hero"]
    hero["hp"] = min(max_hp(state), hero["hp"] + amount)


def inventory_text(state):
    """What the hero has, for the bottom line: 'Spark 2  Blades 1  Boots 1'."""
    config = state["config"]
    parts = []
    for key, level in state["weapons"].items():
        parts.append("%s %d" % (config[key]["short"], level))
    for key, level in state["passives"].items():
        parts.append("%s %d" % (config["passive_items"][key]["short"], level))
    return "  ".join(parts)


def step(state, dt):
    """Advance the world by dt seconds (call it with 1/60)."""
    if not state["alive"] or state["cards"] is not None:
        return
    state["elapsed"] += dt
    if state["elapsed"] >= state["config"]["length"]:
        state["elapsed"] = state["config"]["length"]
        state["alive"] = False
        state["won"] = True
        add_event(state, "end")
        return
    move_hero(state, dt)
    move_enemies(state, dt)
    apply_contact_damage(state, dt)
    handle_spawning(state, dt)
    fire_spark_wand(state, dt)
    move_sparks(state, dt)
    resolve_spark_hits(state)
    spin_blades_hit(state, dt)
    holy_ring_hits(state, dt)
    move_gems(state, dt)
    cull_far_enemies(state)
    update_effects(state, dt)
