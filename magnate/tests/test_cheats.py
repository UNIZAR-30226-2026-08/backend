from django.test import TestCase, override_settings
from django.conf import settings

from django.utils import timezone
from django.core.management import call_command

from magnate.models import (
    Game, CustomUser, BaseSquare, PropertySquare, 
    PropertyRelationship, JailSquare, PlayerGameStatistic
)
from magnate.exceptions import CheatException, MaliciousUserInput, MaliciousUserInputAction
from magnate.cheats import (
    _apply_cheat, _cheat_mock_dice, _cheat_teleport, 
    _cheat_set_money, _cheat_create_property, _cheat_delete_property,
)

from magnate.games import GameManager
from magnate.serializers import ActionMoveTo, ActionThrowDices, ActionPayBail

class GameCheatTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        call_command('init_boards')
        call_command('loaddata', 'items.json')
    def setUp(self):
        self.user = CustomUser.objects.create(username="test_player_1")
        
        self.game = Game.objects.create(
            active_phase_player=self.user,
            phase=Game.GamePhase.roll_the_dices,
            positions={str(self.user.pk): 1},
            money={str(self.user.pk): 1500},
            jail_remaining_turns={},
            possible_destinations={},
            datetime=timezone.now()
        )


        self.square_start = BaseSquare.objects.first()
        self.property_square = PropertySquare.objects.filter(buy_price__gt=0).first()
        self.jail_square = JailSquare.objects.first()

    @override_settings(DEBUG=False)
    def test_apply_cheat_fails_when_not_in_debug(self):
        """Ensure cheats are completely disabled in production/when DEBUG=False."""
        with self.assertRaisesMessage(CheatException, "Cheat commands are only available in DEBUG mode."):
            # We must use async_to_sync or mock if _apply_cheat remains decorated, 
            # assuming we test the synchronous inner logic or un-decorated function directly.
            _apply_cheat.__wrapped__(self.game, {"cheat": "SetMoney"})

    def test_mock_dice_success(self):
        """Test setting exact dice rolls stores them in the possible_destinations field."""
        data = {"dice1": 3, "dice2": 4, "dice_bus": 5}
        _cheat_mock_dice(self.game, data)
        
        self.game.refresh_from_db()
        self.assertIn('__mock_dice__', self.game.possible_destinations)
        self.assertEqual(self.game.possible_destinations['__mock_dice__'], [3, 4, 5])

    def test_mock_dice_out_of_bounds(self):
        """Ensure the cheat rejects invalid dice numbers."""
        data = {"dice1": 7, "dice2": 0, "dice_bus": 3}
        with self.assertRaises(CheatException):
            _cheat_mock_dice(self.game, data)

    def test_teleport_success(self):
        """Ensure the player's position is updated correctly."""
        data = {"player_id": self.user.pk, "square_id": 2}
        _cheat_teleport(self.game, data)
        
        self.game.refresh_from_db()
        self.assertEqual(self.game.positions[str(self.user.pk)], 2)

    def test_teleport_invalid_square(self):
        """Prevent teleporting to a square that doesn't exist."""
        data = {"player_id": self.user.pk, "square_id": 999}
        with self.assertRaisesMessage(CheatException, "Square with custom_id 999 does not exist."):
            _cheat_teleport(self.game, data)

    def test_set_money(self):
        """Check if a player's money can be overwritten."""
        data = {"player_id": self.user.pk, "amount": -500}
        _cheat_set_money(self.game, data)
        
        self.game.refresh_from_db()
        self.assertEqual(self.game.money[str(self.user.pk)], -500)

    def test_create_and_delete_property(self):
        """Test granting and stripping property ownership via cheats."""
        # Create Property
        create_data = {"player_id": self.user.pk, "square_id": 3, "houses": 2, "mortgage": True}
        _cheat_create_property(self.game, create_data)
        
        rel = PropertyRelationship.objects.get(game=self.game, square__custom_id=3)
        self.assertEqual(rel.owner, self.user)
        self.assertEqual(rel.houses, 2)
        self.assertTrue(rel.mortgage)

        # Delete Property
        delete_data = {"square_id": 3}
        _cheat_delete_property(self.game, delete_data)
        
        self.assertFalse(PropertyRelationship.objects.filter(game=self.game, square__custom_id=2).exists())

