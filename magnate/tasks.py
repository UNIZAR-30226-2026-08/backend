from celery import shared_task
from .models import *
from .serializers import GeneralResponseSerializer
from .exceptions import *

from .games import GameManager
from .game_utils import (
        _get_user_square, _get_relationship, _get_square_by_custom_id,
        _add_basic_response_data
)
import random

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .agent import Agent

def broadcast_to_game(game: Game, response: Response) -> None:
    channel_layer = get_channel_layer()
    group_name = f"game_{game.pk}"

    response = _add_basic_response_data(game, response)

    if channel_layer is None:
        return None # TODO: this should not happen, but if it does, we don't want to send an empty response to the clients
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'game_response_event',
            'data': GeneralResponseSerializer(response).data
        }
    )

@shared_task
def auction_callback(game_pk: int) -> None:
    game = Game.objects.get(pk=game_pk)
    response = GameManager._end_auction(game)
    if response:
        broadcast_to_game(game, response)


@shared_task
def kick_out_callback(game_pk: int, user_pk: int) -> None:
    game = Game.objects.get(pk=game_pk)
    user = CustomUser.objects.get(pk=user_pk)
    
    GameManager._bankrupt_player(game, user)

    response = Response()
    broadcast_to_game(game, response)

@shared_task
def next_phase_callback(game_pk: int, user_pk: int) -> None:
    """
    triggered at the end of _roll_dices_logic, after saving (phase is now CHOOSE_SQUARE, MANAGEMENT or LIQUIDATION)
    triggered at the end of _square_chosen_logic, after saving (phase is now MANAGEMENT or LIQUIDATION)
    triggered at the end of _choose_fantasy_logic, after saving (phase is now BUSINESS or ROLL_THE_DICES)
    triggered at the end of _management_logic, after saving (phase is now BUSINESS or ROLL_THE_DICES)
    triggered at the end of _answer_trade_proposal_logic, after saving (phase is now BUSINESS)
    - Cancel at the start of every action handler that is not _roll_dices_logic or _pay_bail_logic
    """

    response = None

    game = Game.objects.get(pk=game_pk)
    user = CustomUser.objects.get(pk=user_pk)

    # we only act if it's user turn
    if game.active_phase_player.pk != user_pk:
        raise GameLogicError("callback out of time")
    if game.phase == GameManager.CHOOSE_SQUARE:
        # random
        possible = list(game.possible_destinations.keys())
        random_square_id = random.choice(possible)
        random_square = _get_square_by_custom_id(random_square_id)
        action = ActionMoveTo.objects.create(game=game, player=user, square=random_square)
        response = GameManager._square_chosen_logic(game, user, action)
    elif game.phase == GameManager.MANAGEMENT:
        current_square = _get_user_square(game, user).get_real_instance()
        if isinstance(current_square, (PropertySquare, ServerSquare, BridgeSquare)):
            # auction if it's unowned
            rel = _get_relationship(game, current_square)
            if rel is None:
                action = ActionDropPurchase.objects.create(game=game, 
                                            player=user, square=current_square)
                response = GameManager._management_logic(game, user, action)
            else:
                # owned, already payed if had to do that -> next turn
                GameManager._next_turn(game, user)
        else:
            GameManager._next_turn(game, user)
    elif game.phase in (GameManager.BUSINESS, GameManager.LIQUIDATION):
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
        GameManager._set_next_phase_timer(game, proposal.player)
    elif game.phase == GameManager.CHOOSE_FANTASY:
        # choose the random one
        action = ActionChooseCard.objects.create(game=game, player=user, chosen_revealed_card=False)
        GameManager._choose_fantasy_logic(game, user, action)

    if not response:
        response = ResponseSkipPhase()
    broadcast_to_game(game, response)




@shared_task
def bot_play_callback(game_pk: int, user_pk: int) -> None:
    game = Game.objects.get(pk=game_pk)
    active_player = game.active_phase_player

    if not active_player or not active_player.is_bot or game.phase == GameManager.END_GAME:
        return

    from .celery import app

    if game.kick_out_task_id:
        app.control.revoke(game.kick_out_task_id, terminate=True)
    if game.next_phase_task_id:
        app.control.revoke(game.next_phase_task_id, terminate=True)
    # decision
    agent = Agent(game, active_player, active_player.bot_level)
    action = agent.choose_action(game)

    if action:
        response = async_to_sync(GameManager.process_action)(game, active_player, action)
        broadcast_to_game(game, response)