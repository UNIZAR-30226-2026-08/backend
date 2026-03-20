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
    _get_user_square, _get_possible_destinations_ids, _get_square_by_custom_id
)
from channels.db import database_sync_to_async

from .exceptions import *

from typing import Optional
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist

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
            pass

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
            response=  cls._square_chosen_logic(game, user, action)
        elif game.phase == cls.CHOOSE_FANTASY:
            if not isinstance(action, ActionChooseCard):
                raise MaliciousUserInputAction(game, user, action)
            response = cls._choose_fantasy_logic(game, user, action)
        elif game.phase == cls.MANAGEMENT:
            if not isinstance(action, (ActionBuySquare, ActionDropPurchase, ActionTakeTram, ActionDoNotTakeTram, ActionNextPhase)):
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
        else: 
            raise GameLogicError(f"Fase no reconocida o no manejada: {game.phase}")

        response.money = game.money
        response.active_phase_player = game.active_phase_player
        response.active_turn_player = game.active_turn_player
        response.phase = game.phase

        return response

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
        response: ResponseThrowDices = ResponseThrowDices()

        d1 = random.randint(1,6)
        d2 = random.randint(1,6)
        d3 = random.randint(1,6) # 4-6 are the bus faces

        response.dice1, response.dice2, response.dice_bus = d1, d2, d3

        triples = d3 <= 3 and (d1 == d2 == d3)
        doubles = (d1 == d2) and not triples

        response.triple = triples

        # jail logic
        remaining_jail_turns = game.jail_remaining_turns.get(str(user.pk), 0)
        is_jailed = remaining_jail_turns > 0
        
        if is_jailed:
            jail_sq = _get_user_square(game, user).get_real_instance()
            if isinstance(jail_sq, JailSquare):
                if remaining_jail_turns == 1:
                    game.money[str(user.pk)] -= jail_sq.bail_price
                    game.jail_remaining_turns[str(user.pk)] = 0
                    stats = PlayerGameStatistic.objects.get(user=user,game=game)
                    stats.turns_in_jail += 1
                    stats.lost_money += jail_sq.bail_price
                elif doubles:
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
                    return response
            else:
                raise GameLogicError(f"Cannot be in jail status and not in jail square")

        # Not jailed
        if triples:
            response.triple = True
            square = _get_user_square(game, user)
            all_squares = BaseSquare.objects.filter(board=square.board)
            # All squares are suitable destinations
            possible_destinations = [s.custom_id for s in all_squares]
            possible_destinations.remove(_get_jail_square().custom_id)
            game.possible_destinations = possible_destinations
            response.destinations = possible_destinations
            game.phase = GameManager.CHOOSE_SQUARE
            game.save()
            return response
        elif doubles: # doubles streak only if not getting out of jail via doubles
            if game.streak >= 2:
                # Go to jail
                jail_square = _get_jail_square()
                response.destinations = [jail_square.custom_id]
                game.streak = 0
                response.streak = game.streak
                
                game.positions[str(user.pk)] = jail_square.custom_id
                game.jail_remaining_turns[str(user.pk)] = 3

                stats = PlayerGameStatistic.objects.get(user=user,game=game)
                stats.times_in_jail += 1
                stats.save()

                game.phase = GameManager.LIQUIDATION

                game.save()
                return response
            elif not is_jailed:
                game.streak = game.streak + 1
        else:
            game.streak = 0

        response.streak = game.streak

        # Hasn't gone to jail
        dice_combinations = _compute_dice_combinations(d1, d2, d3)

        game.possible_destinations, passed_go_map = _get_possible_destinations_ids(game, user, dice_combinations)
        response.destinations = game.possible_destinations
        if len(game.possible_destinations) > 1:
            game.phase = GameManager.CHOOSE_SQUARE
        else:
            dest_square_id = game.possible_destinations[0]
            game.positions[str(user.pk)] = dest_square_id
            square = _get_square_by_custom_id(dest_square_id)

            response = _apply_square_arrival(game, user, response, square, passed_go_map.get(dest_square_id, False))
            
            game.phase = GameManager.MANAGEMENT

        game.save()
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
        response: ResponseChooseSquare = ResponseChooseSquare()

        if not isinstance(action, ActionMoveTo):
            raise MaliciousUserInputAction(game, user, action)

        square = action.square

        if square.custom_id not in game.possible_destinations:
            raise MaliciousUserInput(user, "tried to move to an illegal square")

        current_pos_id = game.positions[str(user.pk)]
        current_pos_square = _get_square_by_custom_id(current_pos_id).get_real_instance()

        game.positions[str(user.pk)] = action.square.custom_id
        game.possible_destinations = []

        # FIXME
        # last_action = ActionThrowDices.objects.filter(game=game, player=user).order_by("-id").first()
        passed_go = False
        # 
        # if last_action:
        #     passed_go: bool = _calculate_passed_go(current_pos_square, action.square.custom_id,
        #                                          last_action.dice1, last_action.dice2,
        #                                          last_action.dice_bus)

        response = _apply_square_arrival(game, user, response, action.square, passed_go)

        real_sq = action.square.get_real_instance()
        if isinstance(real_sq, JailSquare):
            if game.phase != GameManager.LIQUIDATION:
                GameManager._next_turn(game, user)
        elif game.money[str(user.pk)] < 0:
            game.phase = GameManager.LIQUIDATION
        elif game.streak > 0:
            game.phase = GameManager.ROLL_THE_DICES
        else:
            game.phase = GameManager.MANAGEMENT

        game.save()
        return response
    
    @staticmethod
    def _choose_fantasy_logic(game: Game, user: CustomUser, action: ActionChooseCard) -> Response:
        response = ResponseChooseFantasy()
        fantasy_event = game.fantasy_event
        generate = not action.chosen_card
        new_fantasy = None

        if not generate:
            apply_fantasy_event(game, user, fantasy_event)
            game.fantasy_event = None
            response.fantasy_event = fantasy_event
        else:
            new_fantasy = FantasyEventFactory.generate()
            apply_fantasy_event(game, user, new_fantasy)
            game.fantasy_event = None
            response.fantasy_event = new_fantasy
        
        if game.streak == 0:
            game.phase = GameManager.BUSINESS
        else:
            game.phase = GameManager.ROLL_THE_DICES

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
                GameManager._initiate_auction(game, action.square)
            else:
                raise MaliciousUserInputAction(game, user, action)
        elif isinstance(action, ActionTakeTram):
            if isinstance(current_square, TramSquare):
                # TODO: Change for a take_tram function that verifies enough money
                square = action.square
                #check if user can afford it and if that square is a possible destination
                tram_squares = TramSquare.objects.filter()
                tram_squares_ids = [s.custom_id for s in tram_squares]

                if square.custom_id in tram_squares_ids: # confirms its valid
                    game.money[str(user.pk)] -= square.buy_price
                    stats = PlayerGameStatistic.objects.get(user=user,game=game)
                    stats.lost_money += square.buy_price
                    stats.save()
                    game.positions[str(user.pk)] = square.custom_id
                else:
                    raise MaliciousUserInput(user, "tried to take a tram to a non tram square")

            else:
                raise MaliciousUserInputAction(game, user, action)
        elif isinstance(action, ActionDoNotTakeTram):
            pass
        elif isinstance(action, ActionNextPhase):
            pass
        else:
            raise MaliciousUserInputAction(game, user, action)

        if game.phase == GameManager.MANAGEMENT:
            if game.streak == 0:
                game.phase = GameManager.BUSINESS
            else:
                game.phase = GameManager.ROLL_THE_DICES

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

        #TODO: elif with a timeout -> auto sell in case user can reach positive status or kick out in case
        
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
            offer = action.proposal

            offering = offer.player

            offered_money = offer.offered_money
            asked_money = offer.asked_money
            offered_properties = offer.offered_properties
            asked_properties = offer.asked_properties

            # TODO: Verify no player goes to negative (unless liquidation)

            if user != offer.destination_user:
                raise MaliciousUserInput(user, f"cannot accept proposal {offer}")

            if offer != game.proposal:
                raise MaliciousUserInput(user, f"tried to reference a non-existent proposal")
            
            if action.choose:
                for relationship in offered_properties.all():
                    relationship.owner = user
                    relationship.houses = -1 # reset houses
                    relationship.save()
                    
                for relationship in asked_properties.all():
                    relationship.owner = offering
                    relationship.houses = -1
                    relationship.save()

                game.money[str(offering.pk)] -= offered_money
                game.money[str(offering.pk)] += asked_money

                stats = PlayerGameStatistic.objects.get(user=offering,game=game)
                stats.lost_money += offered_money
                stats.won_money += asked_money
                stats.num_trades += 1
                stats.save()
                
                game.money[str(user.pk)] -= asked_money
                game.money[str(user.pk)] += offered_money

                stats = PlayerGameStatistic.objects.get(user=user,game=game)
                stats.lost_money += asked_money
                stats.won_money += offered_money
                stats.num_trades += 1
                stats.save()

                game.save()

            game.phase = GameManager.BUSINESS
            game.active_phase_player = offering
            game.save()

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
        game.phase = GameManager.AUCTION

        auction = Auction.objects.create(game=game, square=square)
        game.current_auction = auction
        game.save()

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

        # user has not bid yet
        if auction.bids.filter(player=user).exists():
            raise MaliciousUserInput(user, "User already placed a bid in this auction")
        
        # user who started the bid cant bid
        dropped = ActionDropPurchase.objects.filter(game=game, player=user, square=auction.square).exists()
        if dropped:
            raise MaliciousUserInput(user, "cannot bid in an auction they triggered")

        # user has enough money -> compulsory for auctions
        amount = action.amount
        if amount > game.money[str(user.pk)]:
            raise MaliciousUserInput(user, "Bid amount exceeds current balance")

        # resgister bid
        action.auction = auction
        action.save()

        return Response()
    
    @staticmethod
    @database_sync_to_async
    def _end_auction(game: Game) -> Response:
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

        if game.phase != GameManager.AUCTION:
            raise GameLogicError("Tried to end auction but game is not in auction phase")

        auction = game.current_auction
        if not auction:
            raise GameLogicError("Game is in AUCTION phase but no auction object found")

        square = auction.square.get_real_instance()
        bids = auction.bids.all()

        # no one bid
        if not bids.exists():
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

            return ResponseAuction(auction=auction)

        max_bid_amount = bids.aggregate(Max('amount'))['amount__max']
        winners = bids.filter(amount=max_bid_amount)
        
        if winners.count() > 1:
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
            return ResponseAuction(auction=auction)

        winner_action = winners.first()
        winner = winner_action.player
        highest_bid = winner_action.amount
        
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

        game.save()
 
    @classmethod
    def _propose_trade(cls, game: Game, user: CustomUser, action: ActionTradeProposal) -> None:
        if action.player != user or action.offered_money < 0 or action.asked_money < 0:
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

        game.phase = GameManager.PROPOSAL_ACCEPTANCE
        game.active_phase_player = action.destination_user
        game.proposal = action # type: ignore
        game.save()

    @classmethod
    def _bankrupt_player(cls, game: Game, user: CustomUser) -> None:
        properties = PropertyRelationship.objects.filter(game=game, owner=user)
        
        #reset all properties
        for rel in properties:
            rel.owner = None 
            rel.houses = -1  
            rel.mortgage = False
            rel.save()
            

        game.money[str(user.pk)] = 0

        # next_turns fails if we dont do this sh
        game.ordered_players = [pk for pk in game.ordered_players if pk != user.pk]
        game.save()

        if game.active_turn_player == user:
            cls._next_turn(game, user)

        game.players.remove(user)
        game.save()
        
        # TODO: if only one left -> he wins

    ############################################################
