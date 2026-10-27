"""Tests for the rules in rules.py only (step 1: core)."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rules

CONFIG = rules.load_config()
STEP = 1.0 / 60.0


def fresh(alive=True):
    state = rules.new_game(CONFIG, rng=random.Random(1))
    rules.start(state)
    return state


def run(state, seconds):
    for _ in range(int(seconds / STEP)):
        rules.step(state, STEP)


class SpawnTests(unittest.TestCase):
    def test_each_second_adds_at_most_eight(self):
        state = fresh()
        rules.handle_spawning(state, CONFIG["spawn"]["interval"])
        self.assertLessEqual(len(state["enemies"]), CONFIG["spawn"]["max_per_second"])

    def test_the_world_fills_up_to_the_minimum(self):
        state = fresh()
        minimum = CONFIG["spawn"]["waves"][0]["min_alive"]
        cap = CONFIG["spawn"]["max_per_second"]
        for _ in range(int(minimum / cap) + 2):
            rules.handle_spawning(state, CONFIG["spawn"]["interval"])
        self.assertEqual(len(state["enemies"]), minimum)

    def test_no_spawning_above_the_minimum(self):
        state = fresh()
        for _ in range(4):
            rules.handle_spawning(state, CONFIG["spawn"]["interval"])
        full = len(state["enemies"])
        rules.handle_spawning(state, CONFIG["spawn"]["interval"])
        self.assertEqual(len(state["enemies"]), full)

    def test_enemies_appear_on_a_circle_around_the_hero(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        d = rules.distance(state["hero"]["x"], state["hero"]["y"], enemy["x"], enemy["y"])
        self.assertAlmostEqual(d, CONFIG["spawn"]["circle_radius"], places=6)

    def test_enemy_count_never_goes_over_the_limit(self):
        state = fresh()
        for _ in range(60 * 60):
            rules.spawn_enemy(state, "bat")
            rules.step(state, STEP)
        self.assertLessEqual(len(state["enemies"]), CONFIG["spawn"]["max_enemies_alive"])

    def test_far_enemies_are_removed(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        enemy["x"] = state["hero"]["x"] + CONFIG["bat"]["cull_distance"] + 10
        rules.step(state, STEP)
        self.assertNotIn(enemy, state["enemies"])


class SparkWandTests(unittest.TestCase):
    def test_no_spark_when_there_is_no_enemy(self):
        state = fresh()
        for _ in range(60):
            rules.fire_spark_wand(state, STEP)
        self.assertEqual(state["sparks"], [])

    def test_the_wand_waits_one_interval_between_shots(self):
        state = fresh()
        rules.spawn_enemy(state, "bat")
        wand = CONFIG["spark_wand"]
        rules.fire_spark_wand(state, STEP)
        self.assertEqual(len(state["sparks"]), 1)
        for _ in range(int((wand["interval"] - 0.1) / STEP)):
            rules.fire_spark_wand(state, STEP)
        self.assertEqual(len(state["sparks"]), 1)
        for _ in range(int(0.2 / STEP) + 1):
            rules.fire_spark_wand(state, STEP)
        self.assertEqual(len(state["sparks"]), 2)

    def test_a_spark_does_wand_damage_and_is_used_up(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        enemy["x"] = state["hero"]["x"] + 40.0
        wand = CONFIG["spark_wand"]
        state["sparks"].append({
            "x": enemy["x"], "y": enemy["y"], "vx": 0.0, "vy": 0.0,
            "damage": wand["damage"], "life": 1.0,
        })
        rules.resolve_spark_hits(state)
        self.assertEqual(enemy["hp"], CONFIG["bat"]["hp"] - wand["damage"])
        self.assertEqual(state["sparks"], [])

    def test_a_bat_dies_after_enough_sparks(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        enemy["x"] = state["hero"]["x"] + 40.0
        wand = CONFIG["spark_wand"]
        hits_needed = -(-CONFIG["bat"]["hp"] // wand["damage"])
        for i in range(hits_needed):
            state["sparks"].append({
                "x": enemy["x"], "y": enemy["y"], "vx": 0.0, "vy": 0.0,
                "damage": wand["damage"], "life": 1.0,
            })
            rules.resolve_spark_hits(state)
        self.assertEqual(state["kills"], 1)
        self.assertNotIn(enemy, state["enemies"])
        self.assertEqual(state["sparks"], [])


class ContactDamageTests(unittest.TestCase):
    def test_touching_the_hero_costs_hp_once_per_half_second(self):
        state = fresh()
        start_hp = state["hero"]["hp"]
        enemy = rules.spawn_enemy(state, "bat")
        enemy["x"] = state["hero"]["x"]
        enemy["y"] = state["hero"]["y"]
        enemy["touch_timer"] = 0.0
        rules.apply_contact_damage(state, STEP)
        self.assertEqual(state["hero"]["hp"], start_hp - CONFIG["bat"]["damage"])
        rules.apply_contact_damage(state, STEP)
        self.assertEqual(state["hero"]["hp"], start_hp - CONFIG["bat"]["damage"])

    def test_no_damage_when_the_enemy_is_out_of_reach(self):
        state = fresh()
        start_hp = state["hero"]["hp"]
        enemy = rules.spawn_enemy(state, "bat")
        away = CONFIG["hero"]["hit_radius"] + CONFIG["bat"]["hit_radius"] + 5
        enemy["x"] = state["hero"]["x"] + away
        rules.apply_contact_damage(state, STEP)
        self.assertEqual(state["hero"]["hp"], start_hp)


class HeroTests(unittest.TestCase):
    def test_hero_walks_toward_the_pointer(self):
        state = fresh()
        rules.set_aim(state, 1000.0, 0.0)
        run(state, 1.0)
        self.assertAlmostEqual(state["hero"]["x"], CONFIG["hero"]["speed"], places=1)

    def test_hero_stops_when_nothing_points_anywhere(self):
        state = fresh()
        rules.set_aim(state, 500.0, 0.0)
        run(state, 0.5)
        moved = state["hero"]["x"]
        rules.clear_aim(state)
        run(state, 0.5)
        self.assertGreater(moved, 0.0)
        self.assertAlmostEqual(state["hero"]["x"], moved, places=6)

    def test_hero_stops_at_the_pointer(self):
        state = fresh()
        near = CONFIG["hero"]["stop_distance"] - 1
        rules.set_aim(state, near, 0.0)
        run(state, 0.5)
        self.assertAlmostEqual(state["hero"]["x"], 0.0, places=6)


class GameOverTests(unittest.TestCase):
    def test_hp_zero_ends_the_game_and_freezes_the_world(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        state["hero"]["hp"] = CONFIG["bat"]["damage"]
        enemy["x"] = state["hero"]["x"]
        enemy["y"] = state["hero"]["y"]
        rules.step(state, STEP)
        self.assertEqual(state["hero"]["hp"], 0)
        self.assertFalse(state["alive"])
        enemies = list(state["enemies"])
        run(state, 1.0)
        self.assertEqual(state["enemies"], enemies)

    def test_a_new_game_starts_full_again(self):
        state = fresh()
        state["hero"]["hp"] = 0
        state["alive"] = False
        state = rules.new_game(CONFIG, rng=random.Random(2))
        rules.start(state)
        self.assertEqual(state["hero"]["hp"], CONFIG["hero"]["hp"])
        self.assertTrue(state["alive"])


class GemTests(unittest.TestCase):
    def test_a_dead_enemy_drops_a_gem_worth_its_xp(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        rules.kill_enemy(state, enemy)
        self.assertEqual(len(state["gems"]), 1)
        self.assertEqual(state["gems"][0]["xp"], CONFIG["bat"]["xp"])
        self.assertEqual(state["gems"][0]["x"], enemy["x"])

    def test_a_gem_inside_the_magnet_radius_flys_to_the_hero(self):
        state = fresh()
        pull = rules.magnet_radius(state)
        state["gems"].append({"x": pull * 0.5, "y": 0.0, "xp": 1})
        rules.move_gems(state, STEP)
        self.assertLess(state["gems"][0]["x"], pull * 0.5)

    def test_a_gem_outside_the_magnet_radius_stays(self):
        state = fresh()
        pull = rules.magnet_radius(state)
        state["gems"].append({"x": pull + 40.0, "y": 0.0, "xp": 1})
        rules.move_gems(state, STEP)
        self.assertAlmostEqual(state["gems"][0]["x"], pull + 40.0, places=6)

    def test_a_gem_at_the_hero_gives_xp(self):
        state = fresh()
        state["gems"].append({"x": 3.0, "y": 0.0, "xp": 2})
        rules.move_gems(state, STEP)
        self.assertEqual(state["gems"], [])
        self.assertEqual(state["xp"], 2)


class LevelTests(unittest.TestCase):
    def test_xp_for_the_next_level_grows_by_three(self):
        state = fresh()
        self.assertEqual(rules.xp_next(state), CONFIG["xp"]["first"])
        state["level"] = 3
        self.assertEqual(rules.xp_next(state), 11)

    def test_a_level_up_opens_three_cards_and_freezes_the_world(self):
        state = fresh()
        rules.gain_xp(state, CONFIG["xp"]["first"])
        self.assertEqual(state["level"], 2)
        self.assertEqual(len(state["cards"]), CONFIG["level_up"]["cards"])
        enemies = list(state["enemies"])
        run(state, 1.0)
        self.assertAlmostEqual(state["elapsed"], 0.0, places=6)
        self.assertEqual(state["enemies"], enemies)

    def test_two_level_ups_at_once_ask_for_a_card_twice(self):
        state = fresh()
        need = CONFIG["xp"]["first"] + CONFIG["xp"]["first"] + CONFIG["xp"]["more_each_level"]
        rules.gain_xp(state, need)
        self.assertEqual(state["level"], 3)
        rules.choose_card(state, 0)
        self.assertIsNotNone(state["cards"])
        rules.choose_card(state, 0)
        self.assertIsNone(state["cards"])

    def test_the_three_cards_are_different(self):
        state = fresh()
        for seed in range(20):
            state["rng"] = random.Random(seed)
            rules.open_cards(state)
            keys = [(c["kind"], c.get("key")) for c in state["cards"]]
            self.assertEqual(len(keys), len(set(keys)))


class CardChoiceTests(unittest.TestCase):
    def test_nothing_at_level_5_is_ever_offered(self):
        state = fresh()
        for key in CONFIG["weapons"]:
            state["weapons"][key] = CONFIG[key]["max_level"]
        for key in CONFIG["passive_items"]:
            state["passives"][key] = CONFIG["passive_items"][key]["max_level"]
        self.assertEqual(rules.card_choices(state), [])
        rules.open_cards(state)
        self.assertEqual(state["cards"], [{"kind": "heal"}])

    def test_heal_card_when_nothing_is_left(self):
        state = fresh()
        state["hero"]["hp"] = 10
        for key in CONFIG["weapons"]:
            state["weapons"][key] = CONFIG[key]["max_level"]
        for key in CONFIG["passive_items"]:
            state["passives"][key] = CONFIG["passive_items"][key]["max_level"]
        rules.open_cards(state)
        rules.choose_card(state, 0)
        self.assertEqual(state["hero"]["hp"], 10 + CONFIG["level_up"]["heal"])

    def test_no_new_weapon_card_when_three_are_owned(self):
        state = fresh()
        for key in CONFIG["weapons"]:
            state["weapons"][key] = 1
        kinds = [c["kind"] for c in rules.card_choices(state)]
        self.assertNotIn("new_weapon", kinds)

    def test_passive_cards_change_the_hero(self):
        state = fresh()
        rules.apply_card(state, {"kind": "passive", "key": "swift_boots", "level": 1})
        self.assertAlmostEqual(rules.hero_speed(state),
                               CONFIG["hero"]["speed"] * 1.1, places=6)
        rules.apply_card(state, {"kind": "passive", "key": "magnet", "level": 2})
        self.assertEqual(rules.magnet_radius(state),
                         CONFIG["hero"]["magnet_radius"] + 2 * CONFIG["passive_items"]["magnet"]["magnet_radius"])
        state["hero"]["hp"] = 50
        rules.apply_card(state, {"kind": "passive", "key": "big_heart", "level": 1})
        heart = CONFIG["passive_items"]["big_heart"]
        self.assertEqual(rules.max_hp(state), CONFIG["hero"]["hp"] + heart["max_hp"])
        self.assertEqual(state["hero"]["hp"], 50 + heart["heal"])

    def test_a_new_weapon_card_adds_the_weapon(self):
        state = fresh()
        rules.apply_card(state, {"kind": "new_weapon", "key": "holy_ring", "level": 1})
        self.assertEqual(state["weapons"]["holy_ring"], 1)
        self.assertIsNotNone(rules.ring_stats(state))


class GrowthWeaponTests(unittest.TestCase):
    def test_spark_wand_levels(self):
        state = fresh()
        state["weapons"]["spark_wand"] = 3
        stats = rules.spark_stats(state)
        self.assertEqual(stats["sparks"], 2)
        self.assertEqual(stats["damage"], 10 + 2 * CONFIG["spark_wand"]["damage_per_level"])
        state["weapons"]["spark_wand"] = 5
        self.assertEqual(rules.spark_stats(state)["sparks"], 3)

    def test_the_wand_shoots_one_spark_per_nearest_enemy(self):
        state = fresh()
        state["weapons"]["spark_wand"] = 3
        rules.spawn_enemy(state, "bat")
        rules.spawn_enemy(state, "bat")
        rules.fire_spark_wand(state, STEP)
        self.assertEqual(len(state["sparks"]), 2)

    def test_blade_count_grows_at_levels_2_and_4(self):
        state = fresh()
        for level, expected in [(1, 2), (2, 3), (3, 3), (4, 4), (5, 4)]:
            state["weapons"]["spin_blades"] = level
            self.assertEqual(rules.blade_stats(state)["blades"], expected)

    def test_one_blade_hits_the_same_enemy_once_per_half_second(self):
        state = fresh()
        state["weapons"]["spin_blades"] = 1
        enemy = rules.spawn_enemy(state, "bat")
        bx, by = rules.blade_positions(state)[0]
        enemy["x"], enemy["y"] = bx, by
        rules.spin_blades_hit(state, STEP)
        self.assertEqual(enemy["hp"], CONFIG["bat"]["hp"] - CONFIG["spin_blades"]["damage"])
        enemy["x"], enemy["y"] = rules.blade_positions(state)[0]
        rules.spin_blades_hit(state, STEP)
        self.assertEqual(enemy["hp"], CONFIG["bat"]["hp"] - CONFIG["spin_blades"]["damage"])

    def test_the_ring_hurts_every_enemy_inside_it(self):
        state = fresh()
        state["weapons"]["holy_ring"] = 1
        ring = CONFIG["holy_ring"]
        near = rules.spawn_enemy(state, "bat")
        near["x"], near["y"] = ring["radius"] - 5, 0.0
        far = rules.spawn_enemy(state, "bat")
        far["x"], far["y"] = ring["radius"] + 20, 0.0
        rules.holy_ring_hits(state, STEP)
        self.assertEqual(near["hp"], CONFIG["bat"]["hp"] - ring["damage"])
        self.assertEqual(far["hp"], CONFIG["bat"]["hp"])
        rules.holy_ring_hits(state, STEP)
        self.assertEqual(near["hp"], CONFIG["bat"]["hp"] - ring["damage"])

    def test_the_ring_grows_with_levels(self):
        state = fresh()
        state["weapons"]["holy_ring"] = 2
        stats = rules.ring_stats(state)
        self.assertEqual(stats["radius"], CONFIG["holy_ring"]["radius"] + CONFIG["holy_ring"]["radius_per_level"])
        self.assertEqual(stats["damage"], CONFIG["holy_ring"]["damage"] + CONFIG["holy_ring"]["damage_per_level"])


class WaveTests(unittest.TestCase):
    def fill(self, state, seconds=10):
        for _ in range(seconds):
            rules.handle_spawning(state, CONFIG["spawn"]["interval"])
        return state

    def types_alive(self, state):
        return {e["type"] for e in state["enemies"] if not rules.is_boss(state, e)}

    def test_only_bats_at_the_start(self):
        state = self.fill(fresh())
        state["elapsed"] = 20
        self.fill(state)
        self.assertEqual(self.types_alive(state), {"bat"})
        self.assertEqual(len(state["enemies"]), CONFIG["spawn"]["waves"][1]["min_alive"])

    def test_the_kinds_and_the_minimum_follow_the_table(self):
        for row in CONFIG["spawn"]["waves"]:
            state = rules.new_game(CONFIG, rng=random.Random(5))
            rules.start(state)
            state["elapsed"] = row["from"]
            self.fill(state, seconds=20)
            self.assertEqual(self.types_alive(state), set(row["types"]))
            self.assertEqual(len(state["enemies"]), row["min_alive"])

    def test_the_boss_appears_once(self):
        state = fresh()
        state["elapsed"] = 90
        self.fill(state, seconds=6)
        demons = [e for e in state["enemies"] if e["type"] == "demon"]
        self.assertEqual(len(demons), 1)
        self.assertEqual(demons[0]["hp"], CONFIG["demon"]["hp"])

    def test_the_boss_is_never_removed_but_is_pulled_back(self):
        state = fresh()
        boss = rules.spawn_enemy(state, "demon")
        boss["x"], boss["y"] = CONFIG["demon"]["keep_distance"] + 400, 0.0
        rules.cull_far_enemies(state)
        self.assertIn(boss, state["enemies"])
        dist = rules.distance(state["hero"]["x"], state["hero"]["y"], boss["x"], boss["y"])
        self.assertAlmostEqual(dist, CONFIG["spawn"]["circle_radius"], places=6)

    def test_the_boss_drops_no_gem(self):
        state = fresh()
        boss = rules.spawn_enemy(state, "demon")
        rules.kill_enemy(state, boss)
        self.assertEqual(state["gems"], [])

    def test_a_slime_drops_two_xp(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "slime")
        rules.kill_enemy(state, enemy)
        self.assertEqual(state["gems"][0]["xp"], CONFIG["slime"]["xp"])


class VictoryTests(unittest.TestCase):
    def test_surviving_to_the_goal_wins(self):
        import copy
        config = copy.deepcopy(CONFIG)
        config["length"] = 3
        state = rules.new_game(config, rng=random.Random(4))
        rules.start(state)
        state["hero"]["hp"] = 10 ** 6
        for _ in range(int(4 / STEP)):
            rules.step(state, STEP)
        self.assertTrue(state["won"])
        self.assertFalse(state["alive"])
        self.assertAlmostEqual(state["elapsed"], 3.0, places=6)

    def test_the_world_freezes_after_the_goal(self):
        import copy
        config = copy.deepcopy(CONFIG)
        config["length"] = 1
        state = rules.new_game(config, rng=random.Random(4))
        rules.start(state)
        state["hero"]["hp"] = 10 ** 6
        run(state, 2.0)
        enemies = list(state["enemies"])
        run(state, 1.0)
        self.assertEqual(state["enemies"], enemies)

    def test_hp_zero_is_a_loss_not_a_win(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        state["hero"]["hp"] = CONFIG["bat"]["damage"]
        enemy["x"], enemy["y"] = state["hero"]["x"], state["hero"]["y"]
        rules.step(state, STEP)
        self.assertFalse(state["alive"])
        self.assertFalse(state["won"])


class NumbersComeFromTheFileTests(unittest.TestCase):
    def test_config_has_the_numbers_from_the_design(self):
        self.assertEqual(CONFIG["hero"]["hp"], 100)
        self.assertEqual(CONFIG["hero"]["speed"], 120)
        self.assertEqual(CONFIG["spark_wand"]["damage"], 10)
        self.assertEqual(CONFIG["bat"]["hp"], 8)
        self.assertEqual(CONFIG["xp"]["first"], 5)
        self.assertEqual(CONFIG["level_up"]["heal"], 30)
        self.assertEqual(CONFIG["length"], 120)
        self.assertEqual(CONFIG["gems"]["speed"], 300)
        self.assertEqual(CONFIG["spawn"]["circle_radius"], 380)
        self.assertEqual(CONFIG["spawn"]["max_enemies_alive"], 120)
        self.assertEqual(CONFIG["bat"]["cull_distance"], 700)
        for key, hp, speed, damage, xp in [
            ("bat", 8, 100, 5, 1),
            ("slime", 30, 55, 8, 2),
            ("ghost", 15, 135, 6, 2),
            ("demon", 800, 85, 20, 0),
        ]:
            self.assertEqual(CONFIG[key]["hp"], hp, key)
            self.assertEqual(CONFIG[key]["speed"], speed, key)
            self.assertEqual(CONFIG[key]["damage"], damage, key)
            self.assertEqual(CONFIG[key]["xp"], xp, key)
        self.assertEqual([row["min_alive"] for row in CONFIG["spawn"]["waves"]],
                         [12, 20, 28, 36, 45, 55, 55, 75])

    def test_changed_numbers_are_used(self):
        import copy
        config = copy.deepcopy(CONFIG)
        config["hero"]["speed"] = 60
        state = rules.new_game(config, rng=random.Random(3))
        rules.start(state)
        rules.set_aim(state, 1000.0, 0.0)
        run(state, 1.0)
        self.assertAlmostEqual(state["hero"]["x"], 60.0, places=1)


class SoundAndFeelTests(unittest.TestCase):
    def feel(self):
        return CONFIG["feel"]

    def test_a_hit_gives_a_sound_and_a_damage_number(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        rules.hurt_enemy(state, enemy, 3)
        self.assertEqual(rules.take_events(state), ["hit"])
        self.assertEqual(len(state["floaters"]), 1)
        self.assertEqual(state["floaters"][0]["amount"], 3)
        self.assertAlmostEqual(state["floaters"][0]["life"], self.feel()["damage_number_seconds"])

    def test_the_numbers_are_only_delivered_once(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        rules.hurt_enemy(state, enemy, 1)
        rules.take_events(state)
        self.assertEqual(rules.take_events(state), [])

    def test_a_killed_enemy_leaves_a_flash(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        x, y = enemy["x"], enemy["y"]
        rules.hurt_enemy(state, enemy, CONFIG["bat"]["hp"])
        self.assertEqual(state["enemies"], [])
        self.assertEqual(len(state["flashes"]), 1)
        self.assertEqual((state["flashes"][0]["x"], state["flashes"][0]["y"]), (x, y))

    def test_the_damage_number_floats_up(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        rules.hurt_enemy(state, enemy, 1)
        feel = self.feel()
        start_y = state["floaters"][0]["y"]
        rules.update_effects(state, feel["damage_number_seconds"] / 2)
        self.assertAlmostEqual(state["floaters"][0]["y"], start_y - feel["damage_number_rise"] / 2, places=3)

    def test_effects_run_out(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        rules.hurt_enemy(state, enemy, 1)
        state["shake"] = self.feel()["shake_seconds"]
        for _ in range(int((self.feel()["damage_number_seconds"] + 0.1) / STEP)):
            rules.update_effects(state, STEP)
        self.assertEqual(state["floaters"], [])
        self.assertEqual(state["flashes"], [])
        self.assertEqual(state["shake"], 0.0)

    def test_being_touched_hurts_and_shakes(self):
        state = fresh()
        enemy = rules.spawn_enemy(state, "bat")
        enemy["x"], enemy["y"] = state["hero"]["x"], state["hero"]["y"]
        rules.step(state, STEP)
        self.assertEqual(state["hero"]["hp"], CONFIG["hero"]["hp"] - CONFIG["bat"]["damage"])
        self.assertAlmostEqual(state["shake"], self.feel()["shake_seconds"] - STEP, places=6)
        self.assertIn("hurt", rules.take_events(state))

    def test_a_gem_and_a_level_make_their_noises(self):
        state = fresh()
        state["gems"].append({"x": state["hero"]["x"], "y": state["hero"]["y"], "xp": 1})
        rules.move_gems(state, STEP)
        self.assertEqual(rules.take_events(state), ["gem"])
        rules.gain_xp(state, CONFIG["xp"]["first"])
        self.assertEqual(rules.take_events(state), ["level"])

    def test_losing_and_winning_both_play_the_end(self):
        state = fresh()
        state["hero"]["hp"] = 1
        enemy = rules.spawn_enemy(state, "bat")
        enemy["x"], enemy["y"] = state["hero"]["x"], state["hero"]["y"]
        rules.step(state, STEP)
        self.assertFalse(state["alive"])
        self.assertIn("end", rules.take_events(state))

        import copy
        config = copy.deepcopy(CONFIG)
        config["length"] = 0.5
        won = rules.new_game(config, rng=random.Random(2))
        rules.start(won)
        run(won, 0.6)
        self.assertTrue(won["won"])
        self.assertIn("end", rules.take_events(won))

    def test_the_sound_and_feel_numbers_come_from_the_file(self):
        for name in ("hit", "gem", "level", "hurt", "end"):
            self.assertIn(name, CONFIG["sounds"]["files"])
        import copy
        config = copy.deepcopy(CONFIG)
        config["feel"]["damage_number_seconds"] = 0.1
        state = rules.new_game(config, rng=random.Random(5))
        rules.start(state)
        enemy = rules.spawn_enemy(state, "bat")
        rules.hurt_enemy(state, enemy, 2)
        self.assertAlmostEqual(state["floaters"][0]["life"], 0.1)
        for _ in range(int(0.2 / STEP)):
            rules.update_effects(state, STEP)
        self.assertEqual(state["floaters"], [])


if __name__ == "__main__":
    unittest.main()
