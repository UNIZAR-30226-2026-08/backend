from magnate.models import *
from magnate.exceptions import *
from channels.db import database_sync_to_async

async def handle_cheat(game: Game, data: dict) -> None:
    """
    Dispatches debug cheat commands. Only active when Django DEBUG=True.
    
    Expected message shape:
        { "type": "Cheat", "cheat": "<cheat_name>", ...cheat-specific fields }

    Supported cheats
    ----------------
    MockDice
        Force the next dice roll to specific values.
        { "cheat": "MockDice", "dice1": 3, "dice2": 4, "dice_bus": 5 }

    Teleport
        Move any player to any square immediately.
        { "cheat": "Teleport", "player_id": 7, "square_id": 12 }

    SetMoney
        Set a player's money to an exact amount (can be negative for testing liquidation).
        { "cheat": "SetMoney", "player_id": 7, "amount": 5000 }

    CreateProperty
        Create a PropertyRelationship — give a player ownership of any square.
        { "cheat": "CreateProperty", "player_id": 7, "square_id": 15, "houses": 0, "mortgage": false }

    DeleteProperty
        Delete a PropertyRelationship — strip ownership of a square from whoever holds it.
        { "cheat": "DeleteProperty", "square_id": 15 }
    """
    response_data = await self._apply_cheat(game, data)

@database_sync_to_async
def _apply_cheat(game: Game, data: dict) -> dict:
    from django.conf import settings
    if not settings.DEBUG:
        raise CheatException("Cheat commands are only available in DEBUG mode.")

    cheat = data.get('cheat')

    if cheat == 'MockDice':
        return _cheat_mock_dice(game, data)
    elif cheat == 'Teleport':
        return _cheat_teleport(game, data)
    elif cheat == 'SetMoney':
        return _cheat_set_money(game, data)
    elif cheat == 'CreateProperty':
        return _cheat_create_property(game, data)
    elif cheat == 'DeleteProperty':
        return _cheat_delete_property(game, data)
    else:
        raise CheatException(f"Unknown cheat '{cheat}'.")

def _cheat_mock_dice(game: Game, data: dict) -> dict:
    """
    Stores the forced dice values on the game object under a well-known key.
    _roll_dices_logic must read and clear this before generating its own random values.

    Expects: { "dice1": int 1-6, "dice2": int 1-6, "dice_bus": int 1-6 }
    """
    dice1   = int(data['dice1'])
    dice2   = int(data['dice2'])
    dice_bus = int(data['dice_bus'])

    for val in (dice1, dice2, dice_bus):
        if not (1 <= val <= 6):
            raise CheatException(f"Dice value {val} out of range 1-6.")

    # Piggyback on possible_destinations (unused between turns) to persist
    # the mock without touching the schema — use a reserved sentinel key.
    game.possible_destinations = {
        '__mock_dice__': [dice1, dice2, dice_bus]
    }
    game.save()

def _cheat_teleport(game: Game, data: dict) -> dict:
    """
    Moves a player to any square by custom_id, bypassing all movement logic.

    Expects: { "player_id": int, "square_id": int (custom_id) }
    """
    player_id = int(data['player_id'])
    square_id = int(data['square_id'])

    if str(player_id) not in game.positions:
        raise CheatException(f"Player {player_id} is not in this game.")
    if not BaseSquare.objects.filter(custom_id=square_id).exists():
        raise CheatException(f"Square with custom_id {square_id} does not exist.")

    game.positions[str(player_id)] = square_id
    game.save()

def _cheat_set_money(game: Game, data: dict) -> dict:
    """
    Sets a player's balance to an arbitrary integer (negative allowed for testing liquidation).

    Expects: { "player_id": int, "amount": int }
    """
    player_id = int(data['player_id'])
    amount    = int(data['amount'])

    if str(player_id) not in game.money:
        raise CheatException(f"Player {player_id} is not in this game.")

    game.money[str(player_id)] = amount
    game.save()

def _cheat_create_property(game: Game, data: dict) -> dict:
    """
    Grants a player ownership of a square, creating the PropertyRelationship.
    Existing ownership is overwritten silently.

    Expects:
        { "player_id": int, "square_id": int (custom_id),
          "houses": int (-1..5, default -1), "mortgage": bool (default false) }
    """
    player_id = int(data['player_id'])
    square_id = int(data['square_id'])
    houses    = int(data.get('houses', -1))
    mortgage  = bool(data.get('mortgage', False))

    if str(player_id) not in game.positions:
        raise CheatException(f"Player {player_id} is not in this game.")

    square = BaseSquare.objects.filter(custom_id=square_id).first()
    if square is None:
        raise CheatException(f"Square with custom_id {square_id} does not exist.")

    real_square = square.get_real_instance()
    if not isinstance(real_square, (PropertySquare, BridgeSquare, ServerSquare, TramSquare)):
        raise CheatException(f"Square {square_id} is not a purchasable square type.")

    if not (-1 <= houses <= 5):
        raise CheatException(f"houses must be between -1 and 5, got {houses}.")

    player = CustomUser.objects.get(pk=player_id)

    # Remove any pre-existing ownership so we can set the new one cleanly
    PropertyRelationship.objects.filter(game=game, square=square).delete()

    PropertyRelationship.objects.create(
        game=game,
        square=square,
        owner=player,
        houses=houses,
        mortgage=mortgage,
    )

def _cheat_delete_property(game: Game, data: dict) -> dict:
    """
    Deletes the PropertyRelationship for a square, returning it to the bank.

    Expects: { "square_id": int (custom_id) }
    """
    square_id = int(data['square_id'])

    square = BaseSquare.objects.filter(custom_id=square_id).first()
    if square is None:
        raise CheatException(f"Square with custom_id {square_id} does not exist.")

    deleted, _ = PropertyRelationship.objects.filter(game=game, square=square).delete()
    if deleted == 0:
        raise CheatException(f"Square {square_id} has no owner in this game.")

