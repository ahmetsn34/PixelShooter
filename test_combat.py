import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location(
    "pixel_shooter", Path(__file__).with_name("cs2çakması.py")
)
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)


class KnifeHitTests(unittest.TestCase):
    def setUp(self):
        self.world = game.Game.__new__(game.Game)
        self.world.player = game.Player(None)
        self.world.player.give("knife")
        self.world.player.x, self.world.player.y = 2.5, 2.5
        self.world.player.ang = -0.3
        self.world.phase = "live"
        self.world.audio = SimpleNamespace(play=Mock())
        self.world.hurt_bot = Mock()
        self.blocked = SimpleNamespace(x=4.1, y=2.5, team="T", alive=True)
        self.visible = SimpleNamespace(x=3.55, y=1.2, team="T", alive=True)
        cells = [[" "] * 6 for _ in range(6)]
        cells[2][3] = "c"
        patcher = patch.multiple(game, MAP=cells, MW=6, MH=6)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_knife_cannot_hit_through_crate(self):
        self.world.bots = [self.blocked]
        self.world.try_fire(click=True)
        self.world.hurt_bot.assert_not_called()

    def test_knife_still_hits_visible_enemy(self):
        self.world.bots = [self.visible]
        self.world.try_fire(click=True)
        self.world.hurt_bot.assert_called_once_with(
            self.visible, game.WEAPONS["knife"].dmg, self.world.player
        )

    def test_blocked_enemy_does_not_hide_visible_target(self):
        self.assertLess(
            math.hypot(self.blocked.x - 2.5, self.blocked.y - 2.5),
            math.hypot(self.visible.x - 2.5, self.visible.y - 2.5),
        )
        self.world.bots = [self.blocked, self.visible]
        self.world.try_fire(click=True)
        self.world.hurt_bot.assert_called_once_with(
            self.visible, game.WEAPONS["knife"].dmg, self.world.player
        )


if __name__ == "__main__":
    unittest.main()
