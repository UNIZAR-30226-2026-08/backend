from celery import shared_task
from .models import *

from .games import GameManager
from .game_utils import _get_user_square, _get_relationship, _get_square_by_custom_id
import random


@shared_task
def auction_callback(game_pk: int):
    game = Game.objects.get(pk=game_pk)
    GameManager._end_auction(game)

# kick_out_callback:
#   triggered in _next_turn, after setting phase to ROLL_THE_DICES and saving -> DONE
# TODO: also scheduled before first turn -> ¿consumers?
#   cancel at the start of _roll_dices_logic and _pay_bail_logic
@shared_task
def kick_out_callback(game_pk: int, user_pk: int):
    game = Game.objects.get(pk=game_pk)
    user = CustomUser.objects.get(pk=user_pk)

    # remove user things from game
    game.money.pop(str(user.pk), None)
    game.positions.pop(str(user.pk), None)
    game.jail_remaining_turns.pop(str(user.pk), None)
    game.ordered_players = [pk for pk in game.ordered_players if pk != user.pk]
    game.players.remove(user)
    game.save()

    # remove properties, houses, mortgages
    PropertyRelationship.objects.filter(game=game, owner=user).delete()
    user.active_game = None
    user.save()

    remaining = game.players.count()
    if remaining == 1:
        game.phase = GameManager.END_GAME
        game.save()
        return

    was_active = game.active_turn_player.pk == user.pk
    if was_active:
        GameManager._next_turn(game, game.active_turn_player)



#   triggered at the end of _roll_dices_logic, after saving (phase is now CHOOSE_SQUARE, MANAGEMENT or LIQUIDATION)
#   triggered at the end of _square_chosen_logic, after saving (phase is now MANAGEMENT or LIQUIDATION)
#   triggered at the end of _choose_fantasy_logic, after saving (phase is now BUSINESS or ROLL_THE_DICES)
#   triggered at the end of _management_logic, after saving (phase is now BUSINESS or ROLL_THE_DICES)
#   triggered at the end of _answer_trade_proposal_logic, after saving (phase is now BUSINESS)
#   - Cancel at the start of every action handler that is not _roll_dices_logic or _pay_bail_logic
@shared_task
def next_phase_callback(game_pk: int, user_pk: int):

    game = Game.objects.get(pk=game_pk)
    user = CustomUser.objects.get(pk=user_pk)

    # we only act if it's user turn
    if game.active_phase_player.pk != user_pk:
        return

    if game.phase == GameManager.CHOOSE_SQUARE:
        # random
        possible = list(game.possible_destinations.keys())
        random_square_id = random.choice(possible)
        random_square = _get_square_by_custom_id(random_square_id)
        action = ActionMoveTo.objects.create(game=game, player=user, square=random_square)
        GameManager._square_chosen_logic(game, user, action)

    elif game.phase == GameManager.MANAGEMENT:
        current_square = _get_user_square(game, user).get_real_instance()
        if isinstance(current_square, (PropertySquare, ServerSquare, BridgeSquare)):
            # auction if it's unowned
            rel = _get_relationship(game, current_square)
            if rel is None:
                action = ActionDropPurchase.objects.create(game=game, player=user, square=current_square)
                GameManager._management_logic(game, user, action)
            else:
                # owned, already payed if had to do that -> next turn
                GameManager._next_turn(game, user)
        else:
            GameManager._next_turn(game, user)

    elif game.phase == GameManager.BUSINESS or game.phase == GameManager.LIQUIDATION:
        current_money = game.money[str(user.pk)]
        if current_money >= 0:
            GameManager._next_turn(game, user)
        else:
            kick_out_callback(game_pk, user_pk)

    elif game.phase == GameManager.PROPOSAL_ACCEPTANCE:
        # reject
        proposal = game.proposal
        game.phase = GameManager.BUSINESS
        game.active_phase_player = proposal.player
        game.proposal = None
        game.save()

    elif game.phase == GameManager.CHOOSE_FANTASY:
        # choose the random one
        action = ActionChooseCard.objects.create(game=game, player=user, chosen_card=False)
        GameManager._choose_fantasy_logic(game, user, action)

