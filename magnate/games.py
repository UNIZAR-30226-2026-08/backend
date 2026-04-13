"""
Core Game Logic Module.

This module handles the rules, state transitions, and actions of the game.
It provides helper functions to calculate net worth, rent, building/demolishing
rules, and a GameManager class that acts as a state machine for the different phases
of a player's turn.
"""

from asyncio import Server
import random 
from tokenize import group
from django.db import transaction
from django.db.models import Max
from .serializers import *
from .models import *
from .fantasy import *
from .game_utils import (
    _calculate_passed_go, _apply_square_arrival, _compute_dice_combinations, 
    _move_player_logic, _build_square, _demolish_square, _get_jail_square,_set_mortgage,  
    _unset_mortgage, _get_relationship, _calculate_net_worth, _calculate_rent_price, 
    _get_user_square, _get_possible_destinations_ids, _get_square_by_custom_id,
    _add_basic_response_data
)
from channels.db import database_sync_to_async

from .exceptions import *

from typing import Optional
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist

from celery import shared_task
from .celery import app

class GameManager:
    """
    State machine and core processor for Game Actions.

    The GameManager encapsulates the logic for each specific phase of a 
    player's turn, processing polymorphic Action objects and mutating the 
    database state accordingly.
    """
    ###########################################################################
    # Phase logic
    ###########################################################################

    ROLL_THE_DICES = Game.GamePhase.roll_the_dices
    CHOOSE_SQUARE = Game.GamePhase.choose_square
    MANAGEMENT = Game.GamePhase.management
    BUSINESS = Game.GamePhase.business
    ANSWER_TRADE_PROPOSAL = Game.GamePhase.proposal_acceptance
    LIQUIDATION = Game.GamePhase.liquidation
    AUCTION = Game.GamePhase.auction
    PROPOSAL_ACCEPTANCE = Game.GamePhase.proposal_acceptance
    CHOOSE_FANTASY = Game.GamePhase.choose_fantasy
    END_GAME = Game.GamePhase.end_game


    @classmethod
    @database_sync_to_async
    def process_action(cls, game: Game, user: CustomUser, action: Action) -> Response:
        """
        The only public method exposed in the API. It processes each action
        in dedicated functions depending on the current phase and returns
        a Response.

        Args:
            game (Game): The current active game instance.
            user (CustomUser): The user performing the action.
            action (Action): The deserialized action payload.

        Returns:
            Response: A response object representing the outcome.

        Raises:
            MaliciousUserInput: If the user acts out of turn or phase.
            GameLogicError: If an unrecognized phase is encountered.
        """
       

        if isinstance(action, ActionSurrender):
            # TODO
            cls._bankrupt_player(game, user)
            response = Response()
            return _add_basic_response_data(game, response)

        if user != game.active_phase_player and not isinstance(action, ActionBid): # if aucction there are no turns
            raise MaliciousUserInput(user, "is not the active player")



        if game.phase == cls.ROLL_THE_DICES:
            if isinstance(action, ActionPayBail):
                response = cls._pay_bail_logic(game, user, action)
            elif isinstance(action, ActionThrowDices):
                response = cls._roll_dices_logic(game, user, action)
            else:
                raise MaliciousUserInputAction(game, user, action)
        elif game.phase == cls.CHOOSE_SQUARE:
            if not isinstance(action, ActionMoveTo):
                raise MaliciousUserInputAction(game, user, action)
            response = cls._square_chosen_logic(game, user, action)
        elif game.phase == cls.CHOOSE_FANTASY:
            if not isinstance(action, ActionChooseCard):
                raise MaliciousUserInputAction(game, user, action)
            response = cls._choose_fantasy_logic(game, user, action)
        elif game.phase == cls.MANAGEMENT:
            if not isinstance(action, (ActionBuySquare, ActionDropPurchase, ActionTakeTram, ActionNextPhase)):
                raise MaliciousUserInputAction(game, user, action)
            response = cls._management_logic(game, user, action)
        elif game.phase == cls.BUSINESS or game.phase == cls.LIQUIDATION:
            if not isinstance(action, (ActionBuild, ActionDemolish, ActionTradeProposal, ActionMortgageSet, ActionMortgageUnset, ActionNextPhase)):
                raise MaliciousUserInputAction(game, user, action)
            response = cls._business_logic(game, user, action)
        elif game.phase == cls.ANSWER_TRADE_PROPOSAL:
            if not isinstance(action, ActionTradeAnswer):
                raise MaliciousUserInputAction(game, user, action)
            response = cls._answer_trade_proposal_logic(game, user, action)
        elif game.phase == cls.AUCTION:
            if not isinstance(action, ActionBid):
                raise MaliciousUserInputAction(game, user, action)
            response = cls._bid_property_auction_logic(game, user, action)
        elif game.phase == cls.END_GAME:
            # TODO: check instance???
            # response = cls._end_game_logic(game,user,action)
            return cls._end_game_logic(game,user,action)
        else: 
            raise GameLogicError(f"Fase no reconocida o no manejada: {game.phase}")

        return _add_basic_response_data(game, response)

    @staticmethod
    def _pay_bail_logic(game: Game, user: CustomUser, action: ActionPayBail) -> Response:
        """
        Processes the action to pay the jail bail.

        Args:
            game (Game): The current game instance.
            user (CustomUser): The jailed user.
            action (ActionPayBail): The bail action payload.

        Returns:
            Response: The standard response.

        Raises:
            MaliciousUserInput: If the user is not actually in jail.
            GameLogicError: If the user does not have enough money.
        """

        GameManager._cancel_all_timers(game)

        square = _get_user_square(game, user).get_real_instance()

        if not isinstance(square, JailSquare):
            raise MaliciousUserInput(user, "is not in jail")
        
        remaining = game.jail_remaining_turns.get(str(user.pk), 0)
        if remaining == 0:
            raise MaliciousUserInput(user, "is not in jail (no turns remaining)")

        bail_price = square.bail_price

        if game.money[str(user.pk)] < bail_price:
            raise GameLogicError("not enough money to pay bail")

        game.money[str(user.pk)] -= bail_price
        game.jail_remaining_turns[str(user.pk)] = 0
        game.save()

        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.lost_money += bail_price
        stats.save()
        # roll the dices -> continue normally
        GameManager._set_next_phase_timer(game, user)

        game.save()
        return Response()

    @staticmethod
    def _roll_dices_logic(game: Game, user: CustomUser, action: ActionThrowDices) -> Response: 
        """
        Handles rolling the dice, checking for doubles/triples, and resolving jail mechanics.

        Args:
            game (Game): The current game instance.
            user (CustomUser): The user throwing the dice.
            action (ActionThrowDices): The dice throw action payload.

        Returns:
            Response: Standard response.
        """

        GameManager._cancel_all_timers(game)

        response: ResponseThrowDices = ResponseThrowDices()

        d1 = random.randint(1,6)
        d2 = random.randint(1,6)
        d3 = random.randint(1,6) # 4-6 are the bus faces

        response.dice1, response.dice2, response.dice_bus = d1, d2, d3

        triples = d3 <= 3 and (d1 == d2 == d3)
        doubles = (d1 == d2) and not triples

        response.triple = triples

        current_pos_square = _get_user_square(game, user).get_real_instance()
        current_pos_id = current_pos_square.custom_id

        # jail logic
        remaining_jail_turns = game.jail_remaining_turns.get(str(user.pk), 0)
        is_jailed = remaining_jail_turns > 0
        
        if is_jailed:
            jail_sq = current_pos_square
            if isinstance(jail_sq, JailSquare):
                if remaining_jail_turns == 1: #obligado a salir
                    game.money[str(user.pk)] -= jail_sq.bail_price
                    game.jail_remaining_turns[str(user.pk)] = 0
                    stats = PlayerGameStatistic.objects.get(user=user,game=game)
                    stats.turns_in_jail += 1
                    stats.lost_money += jail_sq.bail_price
                    stats.save()
                elif doubles: #sale gratis
                    game.jail_remaining_turns[str(user.pk)] = 0
                    game.streak = 0
                else:
                    # stays in jail
                    game.jail_remaining_turns[str(user.pk)] -= 1
                    game.phase = GameManager.BUSINESS
                    game.save()
                    stats = PlayerGameStatistic.objects.get(user=user,game=game)
                    stats.turns_in_jail += 1
                    stats.save()
                    response.path = [current_pos_id]
                    GameManager._set_next_phase_timer(game, user)
                    return response
            else:
                raise GameLogicError(f"Cannot be in jail status and not in jail square")

        # Not jailed
        if triples:
            # path current -> decided in chosen
            response.triple = True
            square = current_pos_square
            all_squares = BaseSquare.objects.filter(board=square.board)
            # All squares are suitable destinations
            possible_destinations = [s.custom_id for s in all_squares]
            possible_destinations.remove(_get_jail_square().custom_id)
            game.possible_destinations = {c_id: 0 for c_id in possible_destinations}
            response.destinations = possible_destinations
            game.phase = GameManager.CHOOSE_SQUARE
            response.path = [current_pos_id]
            game.save()
            GameManager._set_next_phase_timer(game, user)
            return response
        elif doubles: # doubles streak only if not getting out of jail via doubles
            if game.streak >= 2:
                # path -> current and jail
                jail_square = _get_jail_square()
                response.destinations = [jail_square.custom_id]
                game.streak = 0
                response.streak = game.streak
                
                game.positions[str(user.pk)] = jail_square.custom_id
                game.jail_remaining_turns[str(user.pk)] = 3
                response.path = [current_pos_id, jail_square.custom_id]

                stats = PlayerGameStatistic.objects.get(user=user,game=game)
                stats.times_in_jail += 1
                stats.save()

                game.phase = GameManager.LIQUIDATION

                game.save()
                GameManager._set_next_phase_timer(game, user)
                return response
            elif not is_jailed:
                game.streak = game.streak + 1
        else:
            game.streak = 0

        response.streak = game.streak

        # Hasn't gone to jail
        dice_combinations = _compute_dice_combinations(d1, d2, d3)
        game.possible_destinations, passed_go_map = _get_possible_destinations_ids(game, user, dice_combinations)

        response.destinations = list(game.possible_destinations.keys())
        if len(game.possible_destinations) > 1:
            # path in square chosen logic
            game.phase = GameManager.CHOOSE_SQUARE
            response.path = [current_pos_id]
        else:
            stats = PlayerGameStatistic.objects.get(user=user,game=game)
            stats.walked_squares += dice_combinations[0]
            stats.save()
            dest_square_id = next(iter(game.possible_destinations))
            steps = game.possible_destinations[dest_square_id]
            
            # Use _move_player_logic to get the traversed path and check for "Go to Jail" or "Passing Go".
            move_result = _move_player_logic(current_pos_square, steps)
            response.path = move_result["path"]

            if move_result["jailed"]:
                # landing in go to jail; update state to jail the player.
                jail = JailSquare.objects.first()
                if jail is None:
                    raise GameDesignError('no jail in game')
                
                game.positions[str(user.pk)] = jail.custom_id
                game.jail_remaining_turns[str(user.pk)] = 3
                game.phase = GameManager.LIQUIDATION
                stats = PlayerGameStatistic.objects.get(user=user, game=game)
                stats.times_in_jail += 1
                stats.save()
            else:
                game.positions[str(user.pk)] = dest_square_id
                square = _get_square_by_custom_id(dest_square_id)
                _apply_square_arrival(game, user, response, square, move_result["passed_go"])
                

        game.save()
        GameManager._set_next_phase_timer(game, user)
        return response

    @staticmethod
    def _square_chosen_logic(game: Game, user: CustomUser, action: Action) -> Response:
        """
        Handles the logic when a user selects their final destination (if multiple choices were given).

        Args:
            game (Game): The current game instance.
            user (CustomUser): The current user.
            action (ActionMoveTo): Action indicating the chosen square.

        Returns:
            Response: Standard response.

        Raises:
            MaliciousUserInput: If the chosen square is not in `possible_destinations`.
        """

        GameManager._cancel_all_timers(game)
        response: ResponseChooseSquare = ResponseChooseSquare()

        if not isinstance(action, ActionMoveTo):
            raise MaliciousUserInputAction(game, user, action)

        square = action.square

        if str(square.custom_id) not in game.possible_destinations:
            raise MaliciousUserInput(user, "tried to move to an illegal square")

        current_pos_id = game.positions[str(user.pk)]
        current_pos_square = _get_square_by_custom_id(current_pos_id).get_real_instance()

        steps = game.possible_destinations.get(str(square.custom_id))
        
        move_result = _move_player_logic(current_pos_square, steps)
        
        response.path = move_result["path"]

        if move_result["jailed"]:
            # landing in go to jail; update state to jail the player.
            jail = JailSquare.objects.first()
            if jail is None:
                raise GameDesignError('no jail in game')
            
            game.positions[str(user.pk)] = jail.custom_id
            game.jail_remaining_turns[str(user.pk)] = 3
            game.phase = GameManager.LIQUIDATION
            stats = PlayerGameStatistic.objects.get(user=user, game=game)
            stats.times_in_jail += 1
            stats.save()
        else:
            game.positions[str(user.pk)] = square.custom_id
            square = _get_square_by_custom_id(square.custom_id)
            _apply_square_arrival(game, user, response, square, move_result["passed_go"])

        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.walked_squares += steps
        stats.save()

        game.possible_destinations = dict()
        game.save()

        GameManager._set_next_phase_timer(game, user)
        return response
    
    @staticmethod
    def _choose_fantasy_logic(game: Game, user: CustomUser, action: ActionChooseCard) -> Response:
        GameManager._cancel_all_timers(game)

        response = ResponseChooseFantasy()
        fantasy_event = game.fantasy_event
        generate = not action.chosen_revealed_card
        new_fantasy = None

        if not generate:
            fantasy_result = apply_fantasy_event(game, user, fantasy_event)
            fantasy_result.save()
            response.fantasy_result = fantasy_result
            game.fantasy_event = None
            
        else:
            new_fantasy = FantasyEventFactory.generate()
            new_fantasy.save()
            fantasy_result = apply_fantasy_event(game, user, new_fantasy)
            fantasy_result.save()
            response.fantasy_result = fantasy_result
            game.fantasy_event = None
        
        if game.streak == 0:
            game.phase = GameManager.BUSINESS
        else:
            game.phase = GameManager.ROLL_THE_DICES

        if game.phase == GameManager.BUSINESS:
            GameManager._set_next_phase_timer(game, user)
        elif game.phase == GameManager.ROLL_THE_DICES:
            #GameManager._set_kick_out_timer(game, user)
            pass
            
        game.save()     
        return response
       
    @staticmethod
    def _management_logic(game: Game, user: CustomUser, action: Action) -> Response:
        """
        Logic of management phase, where the user can buy properties, pay bills etc.

        It checks the user's action against the current square they are on to update 
        the game state and transition to the next phase.

        Args:
            game (Game): The current game instance.
            user (CustomUser): The acting user.
            action (Action): The payload of the action taken (e.g., ActionBuySquare).

        Returns:
            Response: Standard response.

        Raises:
            MaliciousUserInputAction: If the action does not fit the phase/context.
        """
        GameManager._cancel_all_timers(game)

        current_square = _get_user_square(game, user).get_real_instance()
        prop_rel = _get_relationship(game, current_square)

        if isinstance(action, ActionBuySquare):
            if isinstance(current_square, PropertySquare):
                # TODO: Check money
                game.money[str(user.pk)] -= current_square.buy_price
                stats = PlayerGameStatistic.objects.get(user=user,game=game)
                stats.lost_money += current_square.buy_price
                stats.save()
                new_property = PropertyRelationship(game=game, square=current_square, owner=user)
                user_properties = PropertyRelationship.objects.filter(game=game, owner=user)
                user_same_group_properties = user_properties.filter(square__propertysquare__group=current_square.group)

                group_squares = PropertySquare.objects.filter(group=current_square.group, board = current_square.board)

                if user_same_group_properties.count() == group_squares.count() - 1:
                    new_property.houses = 0
                    user_same_group_properties.update(houses=0)
                else: 
                    new_property.houses = -1
                new_property.save()

            elif isinstance(current_square, ServerSquare):
                game.money[str(user.pk)] -= current_square.buy_price
                stats = PlayerGameStatistic.objects.get(user=user,game=game)
                stats.lost_money += current_square.buy_price
                stats.save()
                new_property = PropertyRelationship(game=game, square=current_square, owner=user)
                new_property.save()
            
            elif isinstance(current_square, BridgeSquare):
                game.money[str(user.pk)] -= current_square.buy_price
                stats = PlayerGameStatistic.objects.get(user=user, game=game)
                stats.lost_money += current_square.buy_price
                stats.save()
                new_property = PropertyRelationship(game=game, square=current_square, owner=user)
                new_property.save()

            else:
                raise MaliciousUserInputAction(game, user, action)
        elif isinstance(action, ActionDropPurchase):
            if isinstance(action.square, (PropertySquare, ServerSquare, BridgeSquare)):
                return GameManager._initiate_auction(game, action.square)
            else:
                raise MaliciousUserInputAction(game, user, action)
        elif isinstance(action, ActionTakeTram):
            if isinstance(current_square, TramSquare):
                square = action.square
                tram_squares = TramSquare.objects.filter()
                tram_square_actual_id = game.positions[str(user.pk)]
                tram_squares_extern_ids = [s.custom_id for s in tram_squares]

                if square.custom_id == tram_square_actual_id: # case stay in the same square, free
                    pass
                elif square.custom_id in tram_squares_extern_ids: # Move to another square
                    if game.money[str(user.pk)] < square.buy_price:
                        raise MaliciousUserInput(user, "does not have enough money to take tram")
                    game.money[str(user.pk)] -= square.buy_price
                    stats = PlayerGameStatistic.objects.get(user=user,game=game)
                    stats.lost_money += square.buy_price
                    stats.save()
                    game.positions[str(user.pk)] = square.custom_id
                else:
                    raise MaliciousUserInput(user, "tried to take a tram to a non tram square")
            else:
                raise MaliciousUserInputAction(game, user, action)
        elif isinstance(action, ActionNextPhase):
            # TODO: Remove?
            pass
        else:
            raise MaliciousUserInputAction(game, user, action)

        if game.phase == GameManager.MANAGEMENT:
            if game.streak == 0:
                game.phase = GameManager.BUSINESS
            else:
                game.phase = GameManager.ROLL_THE_DICES

        if game.phase == GameManager.BUSINESS:
            GameManager._set_next_phase_timer(game, user)
        elif game.phase == GameManager.ROLL_THE_DICES:
            #GameManager._set_kick_out_timer(game, user)
            pass 

        game.save()
        return Response()

    @staticmethod
    def _business_logic(game: Game, user: CustomUser, action: Action) -> Response:
        """
        Unifies the business and liquidation phases. Handles building, demolishing, 
        trading, mortgaging, and proceeding to the next turn.

        Args:
            game (Game): The current game instance.
            user (CustomUser): The active user.
            action (Action): The payload of the action taken.

        Returns:
            Response: Standard response.

        Raises:
            MaliciousUserInput: If restrictions (e.g., negative balance on next turn) are unmet.
        """

        GameManager._cancel_all_timers(game)
        # Logic for the business phase where players can build houses, trade, etc.
        if isinstance(action, ActionBuild):
            # Check owner 
            building_square = action.square
            relationship = _build_square(game, user, building_square, action.houses, False)

        elif isinstance(action, ActionDemolish):
            # Similiar to build
            demolition_square = action.square
            relationship = _demolish_square(game, user, demolition_square, action.houses, False)

        elif isinstance(action, ActionTradeProposal):
            relationship = GameManager._propose_trade(game, user, action)
            return Response()

        elif isinstance(action, ActionMortgageSet):
            relationship = _set_mortgage(game, user, action.square, False)

        elif isinstance(action, ActionMortgageUnset):
            relationship = _unset_mortgage(game, user, action.square, False)        
        elif isinstance(action, ActionNextPhase):
            current_money = game.money[str(user.pk)]
            
        
            if game.phase == GameManager.BUSINESS:
                if current_money >= 0:
                    GameManager._next_turn(game, user)
                else:
                    game.phase = GameManager.LIQUIDATION
                    game.save()

            elif game.phase == GameManager.LIQUIDATION:
                if current_money >= 0:
                    GameManager._next_turn(game, user)
                else:
                    raise MaliciousUserInput(user, "Cannot end in NEGATIVE")
            return Response() # timers set in next turn

        GameManager._set_next_phase_timer(game, user)
        return Response()
                   
    @staticmethod
    def _answer_trade_proposal_logic(game: Game, user: CustomUser, action: Action) -> Response:
        """
        Processes a user's answer (accept/reject) to an active trade proposal.

        Args:
            game (Game): The current game instance.
            user (CustomUser): The targeted user responding to the offer.
            action (ActionTradeAnswer): The user's response payload.

        Returns:
            Response: Standard response.

        Raises:
            MaliciousUserInput: If an unauthorized user attempts to answer, 
                or references an invalid proposal.
        """
        if isinstance(action, ActionTradeAnswer):
            offer = game.proposal

            if offer is None:
                raise GameLogicError("there should be an active trade proposal")

            if user != offer.destination_user:
                raise MaliciousUserInput(user, f"cannot accept proposal {offer}")

            offering = offer.player

            offered_money = offer.offered_money
            asked_money = offer.asked_money
            offered_properties = offer.offered_properties
            asked_properties = offer.asked_properties

            if action.choose:
                # Money logic (ensure no player goes to negative)
                money_diff = offered_money - asked_money
                accepter_money = game.money[str(user.pk)] + money_diff
                offering_money = game.money[str(offering.pk)] - money_diff

                if accepter_money < 0:
                    raise MaliciousUserInput(user, f"cannot go to negative in trade")
                if offering_money < 0:
                    raise MaliciousUserInput(offering, f"cannot go to negative in trade")

                for relationship in offered_properties.all():
                    relationship.owner = user
                    relationship.houses = -1 # reset houses
                    relationship.save()
                    
                for relationship in asked_properties.all():
                    relationship.owner = offering
                    relationship.houses = -1
                    relationship.save()

                game.money[str(offering.pk)] = offering_money
                stats = PlayerGameStatistic.objects.get(user=offering, game=game)
                if money_diff > 0:
                    stats.lost_money += abs(money_diff)
                else:
                    stats.won_money += abs(money_diff)
                stats.num_trades += 1
                stats.save()
                
                game.money[str(user.pk)] = accepter_money
                stats = PlayerGameStatistic.objects.get(user=user, game=game)
                if money_diff > 0:
                    stats.won_money += abs(money_diff)
                else:
                    stats.lost_money += abs(money_diff)
                stats.num_trades += 1
                stats.save()

                game.save()

            game.phase = GameManager.BUSINESS
            game.active_phase_player = offering
            game.proposal = None
            game.save()
            GameManager._set_next_phase_timer(game, offering)

            return Response()
        else:
            raise MaliciousUserInputAction(game, user, action)
        
    @staticmethod
    def _initiate_auction(game: Game, square: BaseSquare) -> Response:
        """
        Transitions the game into an AUCTION phase for a dropped property.

        Args:
            game (Game): The current game instance.
            square (BaseSquare): The property square going up for auction.

        Returns:
            Response: Standard response.
        """
        GameManager._cancel_all_timers(game)

        game.next_phase_task_id = None
        game.phase = GameManager.AUCTION

        auction = Auction.objects.create(game=game, square=square, is_active=True, bids = {})
        game.current_auction = auction
        game.save()

        # TODO: Remove magic number
        GameManager._set_auction_timer(game)
        # TODO: Remove in production
        game.refresh_from_db()

        return Response()
        
    @staticmethod
    def _bid_property_auction_logic(game: Game, user: CustomUser, action: Action) -> Response:
        """
        Registers a player's bid during an active auction phase.

        Args:
            game (Game): The current game instance.
            user (CustomUser): The user placing the bid.
            action (ActionBid): The action carrying the bid amount.

        Returns:
            Response: Standard response.

        Raises:
            GameLogicError: If auction state is corrupted.
            MaliciousUserInput: If the user bids twice or exceeds their balance.
        """
        if not isinstance(action, ActionBid):
            raise MaliciousUserInputAction(game, user, action)

        auction = game.current_auction
        if not auction:
            raise GameLogicError("No active auction")


        bids = auction.bids
        # user has not bid yet
        if bids.get(str(user.pk)):
            raise MaliciousUserInput(user, "User already placed a bid in this auction")
        
        # user who started the bid cant bid
        dropped = ActionDropPurchase.objects.filter(game=game, player=user, square=auction.square).exists()
        if dropped:
            raise MaliciousUserInput(user, "cannot bid in an auction they triggered")

        # user has enough money -> compulsory for auctions
        amount = action.amount
        if amount > game.money[str(user.pk)]:
            raise MaliciousUserInput(user, "Bid amount exceeds current balance")

      
        bids[str(user.pk)] = amount
        auction.bids = bids
        auction.save()

        game.save()

        eligible_players_count = game.players.exclude(
            pk__in=ActionDropPurchase.objects.filter(game=game, square=auction.square).values('player')
        ).count()

        if len(bids) >= eligible_players_count:
            # all bidded
            GameManager._cancel_auction_timer(game)
            return GameManager._end_auction(game) #type:ignore

        return Response()
    
    @staticmethod
    def _end_auction(game: Game) -> Response | None:
        """
        Ends an active auction, resolves the winner based on the highest bid, 
        handles ties, and transitions the game state back to BUSINESS.

        Args:
            game (Game): The current game instance.

        Returns:
            Auction: The finalized auction object.

        Raises:
            GameLogicError: If not in AUCTION phase or state is missing square ID.
        """
        ## call this with a timer -> end of the auction

        if game.phase == GameManager.END_GAME:
            return None # Inevitable if the auction callback is triggered after the game has ended, just ignore it
        
        if game.phase != GameManager.AUCTION:
            raise GameLogicError("Tried to end auction but game is not in auction phase")

        auction = game.current_auction
        if not auction:
            raise GameLogicError("Game is in AUCTION phase but no auction object found")

        square = auction.square.get_real_instance()
        bids = auction.bids


        # no one bid
        if not bids:
            if game.streak == 0:
                game.phase = GameManager.BUSINESS
            else:
                game.phase = GameManager.ROLL_THE_DICES
            
            auction.is_active = False
            auction.winner = None
            auction.final_amount = 0
            auction.is_tie = False
            auction.save()

            game.current_auction = None
            game.save()

            if game.phase == GameManager.BUSINESS:
                GameManager._set_next_phase_timer(game, game.active_turn_player)
            elif game.phase == GameManager.ROLL_THE_DICES:
                #GameManager._set_kick_out_timer(game, game.active_turn_player)
                pass
            
            game.save()
            return ResponseAuction(auction=auction)

        max_bid_amount = max(bids.values())
        winners = [int(uid) for uid, amt in bids.items() if amt == max_bid_amount]
            
        if len(winners)> 1:
            if game.streak == 0:
                game.phase = GameManager.BUSINESS
            else:
                game.phase = GameManager.ROLL_THE_DICES
            
            auction.is_active = False
            auction.winner = None
            auction.final_amount = max_bid_amount
            auction.is_tie = True
            auction.save()

            game.current_auction = None
            game.save()

            if game.phase == GameManager.BUSINESS:
                GameManager._set_next_phase_timer(game, game.active_turn_player)
            elif game.phase == GameManager.ROLL_THE_DICES:
                #GameManager._set_kick_out_timer(game, game.active_turn_player)
                pass

            game.save()
            return ResponseAuction(auction=auction)

        winner_id = winners[0]
        if str(winner_id) not in game.money: # surrends mid auction -> no winner
            game.phase = GameManager.BUSINESS if game.streak == 0 else GameManager.ROLL_THE_DICES
            auction.is_active = False
            auction.save()
            
            game.current_auction = None
            game.save()
            
            if game.phase == GameManager.BUSINESS:
                GameManager._set_next_phase_timer(game, game.active_turn_player)
            elif game.phase == GameManager.ROLL_THE_DICES:
                #GameManager._set_kick_out_timer(game, game.active_turn_player)
                pass
            
            game.save()
            return ResponseAuction(auction=auction)
        
        winner = CustomUser.objects.get(pk=winner_id)
        highest_bid = max_bid_amount
        
        game.money[str(winner.pk)] -= highest_bid
        stats = PlayerGameStatistic.objects.get(user=winner,game=game)
        stats.lost_money += highest_bid
        stats.save()
        
        new_property = PropertyRelationship(game=game, square=square, owner=winner)
        
        # groups n houses
        if isinstance(square, PropertySquare):
            user_properties = PropertyRelationship.objects.filter(game=game, owner=winner)
            user_same_group_properties = user_properties.filter(square__propertysquare__group=square.group)
            group_squares = PropertySquare.objects.filter(group=square.group, board = square.board)

            if user_same_group_properties.count() == group_squares.count() - 1:
                new_property.houses = 0
                user_same_group_properties.update(houses=0)
            else: 
                new_property.houses = -1
        else:
            new_property.houses = -1
            
        new_property.save()

        auction.winner = winner
        auction.final_amount = highest_bid
        auction.is_active = False
        auction.is_tie = False
        auction.save()

        if game.streak == 0:
            game.phase = GameManager.BUSINESS
        else:
            game.phase = GameManager.ROLL_THE_DICES
        
        game.current_auction = None
        game.save()

        if game.phase == GameManager.BUSINESS:
            GameManager._set_next_phase_timer(game, game.active_turn_player)
        elif game.phase == GameManager.ROLL_THE_DICES:
            #GameManager._set_kick_out_timer(game, game.active_turn_player)
            pass
        
        game.save()

        return ResponseAuction(auction=auction)

    @classmethod
    def _next_turn(cls, game: Game, user: CustomUser) -> None:
        players_list = list(game.players.all()) 
        num_players = len(players_list)
        current_index = -1
        current_player_id = -1
        for p in players_list:
            if p == game.active_turn_player:
                current_player_id = p.pk
                current_index = game.ordered_players.index(current_player_id)
                break
            
        if current_index == -1:
            raise GameLogicError('current player not found')
        
        next_index = (current_index + 1) % num_players
        # The next active user is for both: phase and turn
        next_player = game.players.filter(pk=game.ordered_players[next_index]).first()
        if next_player is None:
            raise GameLogicError('next player is None')

        game.active_phase_player = next_player
        game.active_turn_player = next_player
        game.phase = GameManager.ROLL_THE_DICES
        game.current_turn += 1
        game.save()

        bot_next = Bot.objects.filter(pk=next_player.pk).first()
        if bot_next:
            bot_next.has_proposed_trade = False
            bot_next.save()

        GameManager._cancel_all_timers(game)

        #GameManager._set_kick_out_timer(game, next_player)
        pass

        game.save()
 
    @classmethod
    def _propose_trade(cls, game: Game, user: CustomUser, action: ActionTradeProposal) -> None:
        if action.player.pk != user.pk or action.offered_money < 0 or action.asked_money < 0:
            raise MaliciousUserInput(user, "cannot do operation")
        if action.destination_user not in game.players.all():
            # FIXME: Change to internal order so that it handles player change to AI
            raise MaliciousUserInput(user, "referenced a player that is not in game")

        asked_properties_list = action.asked_properties.all()
        asked_count = PropertyRelationship.objects.filter(
            game=game, 
            owner=action.destination_user,
            id__in=action.asked_properties.all()
        ).count()

        if asked_count != asked_properties_list.count():
            raise MaliciousUserInput(user, "destination does not have enough properties")

        offered_properties_list = action.offered_properties.all()
        offered_count = PropertyRelationship.objects.filter(
            game=game, 
            owner=action.player,
            id__in=offered_properties_list
        ).count()

        if offered_count != offered_properties_list.count():
            raise MaliciousUserInput(user, "offer does not have enough properties")

        all_trade_properties = list(asked_properties_list) + list(offered_properties_list)
        for rel in all_trade_properties:
            real_sq = rel.square.get_real_instance()
            if isinstance(real_sq, PropertySquare):
                group_has_houses = PropertyRelationship.objects.filter(
                    game=game, 
                    square__propertysquare__group=real_sq.group,
                    houses__gt=0
                ).exists()
                if group_has_houses:
                    raise MaliciousUserInput(user, "cannot trade properties from a group with constructions")

        bot = Bot.objects.filter(pk=user.pk).first()
        if bot:
            bot.has_proposed_trade = True
            bot.save()


        game.phase = GameManager.PROPOSAL_ACCEPTANCE
        game.active_phase_player = action.destination_user
        game.proposal = action # type: ignore
        game.save()
        GameManager._set_next_phase_timer(game, action.destination_user)

    @classmethod
    def _bankrupt_player(cls, game: Game, user: CustomUser):
        try:
            current_idx = game.ordered_players.index(user.pk)
            next_pk = game.ordered_players[(current_idx + 1) % len(game.ordered_players)]
            next_player = CustomUser.objects.get(pk=next_pk)
        except ValueError:
            next_player = None

        if user.pk in game.ordered_players:
            game.ordered_players.remove(user.pk)
            
        game.players.remove(user)
        game.money.pop(str(user.pk), None)
        game.positions.pop(str(user.pk), None)
        game.jail_remaining_turns.pop(str(user.pk), None)
        

        PropertyRelationship.objects.filter(game=game, owner=user).delete()
        user.active_game = None
        user.save()


        if game.players.count() == 1:          
            game.phase = GameManager.END_GAME
            GameManager._cancel_all_timers(game)

            if game.current_auction:
                auction = game.current_auction
                auction.is_active = False
                auction.save()
                game.current_auction = None

            game.save()   
            return #TODO: endgame logic

        if game.active_turn_player.pk == user.pk and next_player:
            game.active_turn_player = next_player
            game.active_phase_player = next_player
            game.phase = GameManager.ROLL_THE_DICES
            game.streak = 0
            
            GameManager._cancel_all_timers(game)
                
            # new task
            #GameManager._set_kick_out_timer(game, next_player)
                
        game.save()

    #TODO: llegar a fase final donde se reparte esto
    @classmethod
    def _apply_end_bonuses(cls, game: Game, num_bonuses: int = 3) -> ResponseBonus:
        all_categories = list(BonusCategory.objects.all())
        chosen = random.sample(all_categories, min(num_bonuses, len(all_categories)))

        response = ResponseBonus()
        bonuses = {}

        for category in chosen:
            field = category.stat_field
            stats = PlayerGameStatistic.objects.filter(game=game)

            max_value = stats.aggregate(Max(field))[f'{field}__max']
            if max_value and max_value > 0:
                winners = list(stats.filter(**{field: max_value}).values_list('user__pk', flat=True))
                for pk in winners:
                    game.money[str(pk)] = game.money.get(str(pk), 0) + category.bonus_amount
            else:
                winners = []

            bonuses[str(category.pk)] = {
                'bonus_amount': category.bonus_amount,
                'winners': winners
            }

        response.bonuses = bonuses
        game.save()
        return response

    @classmethod
    def _end_game_logic(cls, game: Game, user: CustomUser, action: Action) -> Response:
        GameManager._cancel_all_timers(game)

        if not game.finished:
            game.finished = True
            response = cls._apply_end_bonuses(game, num_bonuses=3)
            
            from django.utils import timezone
            
            # include eliminated users
            all_participants = PlayerGameStatistic.objects.filter(game=game).select_related('user')
            active_players = game.players.all()
            
            final_money_dict = {}
            
            for stat in all_participants:
                participant = stat.user
                if participant in active_players:
                    # not eliminated
                    final_money_dict[str(participant.pk)] = _calculate_net_worth(game, participant)
                else:
                    final_money_dict[str(participant.pk)] = 0
            
            GameSummary.objects.create(
                game=game,
                start_date=game.datetime,
                end_date=timezone.now(),
                final_money=final_money_dict
            )

            response.save()
            game.bonus_response = response
            game.save()
            
            from .models import Bot
            bots_in_game = Bot.objects.filter(id__in=game.players.values_list('id', flat=True))
            bots_in_game.delete()

            return response
        else:
            raise GameLogicError('game was already ended')

            


    @staticmethod
    def _set_next_phase_timer(game: Game, user: CustomUser):
        from .tasks import next_phase_callback, bot_play_callback
        from .celery import app
        
        GameManager._cancel_all_timers(game)
        
        task = next_phase_callback.apply_async(args=[game.pk, user.pk], countdown=50000)
        game.next_phase_task_id = task.id
        game.save()

        if Bot.objects.filter(pk=user.pk).exists():
            bot_play_callback.apply_async(args=[game.pk, user.pk], countdown=2)

    #@staticmethod
    #def _set_kick_out_timer(game: Game, user: CustomUser):
    #    from .tasks import kick_out_callback, bot_play_callback
    #    from .celery import app
    #    
    #    if game.kick_out_task_id:
    #        app.control.revoke(game.kick_out_task_id, terminate=True)
    #        
    #    task = kick_out_callback.apply_async(args=[game.pk, user.pk], countdown=20)
    #    game.kick_out_task_id = task.id
    #    game.save()
#
    #    if Bot.objects.filter(pk=user.pk).exists():
    #        bot_play_callback.apply_async(args=[game.pk, user.pk], countdown=2)

    @staticmethod
    def _cancel_all_timers(game: Game):
        from .celery import app
        from celery import current_task
        
        current_task_id = None
        if current_task and hasattr(current_task, 'request'):
            current_task_id = getattr(current_task.request, 'id', None)

        if game.next_phase_task_id:
            if game.next_phase_task_id != current_task_id:
                app.control.revoke(game.next_phase_task_id, terminate=True)
            game.next_phase_task_id = None
            
        if game.kick_out_task_id:
            if game.kick_out_task_id != current_task_id:
                app.control.revoke(game.kick_out_task_id, terminate=True)
            game.kick_out_task_id = None
            
        game.save()




    @staticmethod
    def _set_auction_timer(game: Game):
        import random
        from .tasks import auction_callback, bot_play_callback
        
        GameManager._cancel_auction_timer(game)
        task = auction_callback.apply_async(args=[game.pk], countdown=20)
        game.auction_task_id = task.id
        game.save()
        
        for player in game.players.all():
            if Bot.objects.filter(pk=player.pk).exists():
                bot_play_callback.apply_async(args=[game.pk, player.pk], countdown=random.randint(2, 6))

    @staticmethod
    def _cancel_auction_timer(game: Game):
        from .celery import app
        from celery import current_task
        
        current_task_id = None
        if current_task and hasattr(current_task, 'request'):
            current_task_id = getattr(current_task.request, 'id', None)

        if game.auction_task_id:
            if game.auction_task_id != current_task_id:
                app.control.revoke(game.auction_task_id, terminate=True)
            game.auction_task_id = None
            game.save()


    ############################################################
