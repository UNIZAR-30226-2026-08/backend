from asyncio import Server
import random 
import json
from tokenize import group
from django.db import transaction


from magnate.serializers import *
from .models import *
from channels.db import database_sync_to_async

from magnate.exceptions import *

from typing import Optional
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist

def _get_square_by_custom_id(custom_id: int) -> BaseSquare:
    square = BaseSquare.objects.filter(custom_id=custom_id).first()
    if square is None:
        raise GameLogicError(f"no square with id {custom_id}")

    return square

def _get_user_square(game: Game, user: CustomUser) -> BaseSquare:
    user_key = str(user.pk) if str(user.pk) in game.positions else user.pk
    
    if user_key not in game.positions:
        raise GameLogicError(f"user {user} not in the game")
        
    return _get_square_by_custom_id(game.positions[user_key])

def _get_relationship(game: Game, square: BaseSquare) -> Optional[PropertyRelationship]:
    try:
        return PropertyRelationship.objects.get(game=game, square=square)
    except PropertyRelationship.DoesNotExist:
        return None
    except MultipleObjectsReturned:
        raise GameLogicError("more than one owners for the same square")

def _get_jail_square() -> BaseSquare:
    try:
        return JailSquare.objects.get()
    except JailSquare.DoesNotExist:
        raise GameDesignError("there are no jail squares in the game")
    except MultipleObjectsReturned:
        raise GameDesignError("there are too many jail squares")

def _calculate_rent_price(game: Game, user: CustomUser, square: BaseSquare) -> int:
    # If it is not owned or is owned by the same user, no rent is paid
    prop_rel = _get_relationship(game, square)
    if not prop_rel or prop_rel.owner == user:
        return 0

    houses = prop_rel.houses

    if isinstance(square, PropertySquare):
        if not square.rent_prices or len(square.rent_prices) < 6:
            raise GameDesignError(f"Incorrect rent prices for square {square.custom_id}")
        if houses == -1:
            return square.rent_prices[0]
        elif houses == 0:
            return square.rent_prices[1]
        elif houses == 1:
            return square.rent_prices[2]
        elif houses == 2:
            return square.rent_prices[3]
        elif houses == 3:
            return square.rent_prices[4]
        elif houses == 4:
            return square.rent_prices[5]
        elif houses == 5:
            return square.rent_prices[6]
    
        return 0

    elif isinstance(square, TramSquare):
        # TODO
        return 0
    
    elif isinstance(square, BridgeSquare):
        property_owner = prop_rel.owner
        bridges_owned = PropertyRelationship.objects.filter(game=game, square__bridgesquare__isnull=False, owner=property_owner).count()
        if not square.rent_prices or len(square.rent_prices) < bridges_owned:
            raise GameDesignError(f"Incorrect rent prices for bridge {square.custom_id}")
        return square.rent_prices[bridges_owned - 1]

    elif isinstance(square, ServerSquare):
        property_owner = prop_rel.owner

        if not square.rent_prices or len(square.rent_prices) < 2:
            raise GameDesignError(f"Incorrect rent prices for square {square.custom_id}")

        squares = PropertyRelationship.objects.filter(game=game, square__serversquare__isnull=False, owner=property_owner)

        if squares.count() == 2:
            return square.rent_prices[1]
        elif squares.count() == 1:
            return square.rent_prices[0]
        else:
            # TODO: Write something
            raise GameLogicError()
    else:
        return 0


def _demolish_square(game: Game, 
                     user: CustomUser, 
                     demolition_square: BaseSquare, 
                     number_demolished: int,
                     free_demolish: bool) -> PropertyRelationship:
    # Check if it's a property
    demolition_square = demolition_square.get_real_instance()
    if not isinstance(demolition_square, PropertySquare):
        raise MaliciousUserInput(user, "tried to demolish a non property square")
    
    relationship = _get_relationship(game, demolition_square)

    if relationship is None:
        raise MaliciousUserInput(user, "no user owns this square")
    
    if relationship.owner != user:
        raise MaliciousUserInput(user, "tried to demolish an unowned property")

    actual_houses = relationship.houses

    if actual_houses < number_demolished:
        raise MaliciousUserInput(user, "tried to demolish more houses than are built")

    square_group = demolition_square.group

    group_relationships = PropertyRelationship.objects.filter(
        game=game, 
        owner=user, 
        square__propertysquare__group=square_group
    ).select_related('square')

    # Check if we can demolish -> respect rule 
    for rel in group_relationships:
        if (actual_houses - number_demolished) < (rel.houses - 1):
            raise MaliciousUserInput(user, "unable to demolish so many houses: violates the uniform building rule")

    # demolish
    relationship.houses -= number_demolished
    relationship.save()
    
    if not free_demolish:
        coste = demolition_square.build_price
        
        game.money[str(user.pk)] += coste // 2 * number_demolished
        game.save()

    return relationship


def _build_square(game: Game, 
                  user: CustomUser, 
                  building_square: BaseSquare, 
                  number_built: int,
                  free_build: bool) -> PropertyRelationship:
    # Check if it's  a property and take its group
    building_square = building_square.get_real_instance()

    if not isinstance(building_square, PropertySquare):
        raise MaliciousUserInput(user, "tried to build in a non property square")

    relationship = _get_relationship(game, building_square)

    if relationship is None:
        raise MaliciousUserInput(user, "no user owns this square")

    if relationship.owner != user:
        raise MaliciousUserInput(user, "tried to build in an unowned property")

    square_group = building_square.group
    actual_houses = relationship.houses
    
    # Check if user has every square in the group and if its a property
    total_squares_in_group = PropertySquare.objects.filter(
        board=building_square.board, 
        group=square_group
    ).count()

    group_relationships = PropertyRelationship.objects.filter(
        game=game, 
        owner=user, 
        square__propertysquare__group=square_group
    ).select_related('square')

    if group_relationships.count() != total_squares_in_group:
        raise MaliciousUserInput(user, "does not own the group")

    for rel in group_relationships:
        if rel.houses < 0: 
            raise GameLogicError(f"negative house value")
        elif actual_houses + number_built - 1 > rel.houses:
            raise MaliciousUserInput(user, "already owns more than other")

    if actual_houses == 5:
        raise MaliciousUserInput(user, "nothing more to build")

    relationship.houses += number_built
    relationship.save()
    
    if not free_build:
        coste = building_square.build_price * number_built
        

        game.money[str(user.pk)] -= coste
        game.save()

    return relationship  #ack


#TODO: si hay hipotecada no se cuenta grupo completo?

def _set_mortgage( game: Game, user: CustomUser,target_square: BaseSquare, free_mortgage: bool) -> PropertyRelationship:
    target_square = target_square.get_real_instance()
    if not (isinstance(target_square, PropertySquare) or
            isinstance(target_square, BridgeSquare) or
            isinstance(target_square, ServerSquare)):
        raise MaliciousUserInput(user, "tried to mortgage a non property/bridge/server square")

    relationship = _get_relationship(game=game, square=target_square)

    if relationship is None:
        raise MaliciousUserInput(user, "no user owns this square")

    if relationship.owner != user:
        raise MaliciousUserInput(user, "tried to mortgage an unowned property")

    if relationship.mortgage:
        raise MaliciousUserInput(user, "tried to mortgage an already mortgaged property")

    

    if isinstance(target_square, PropertySquare):
        if relationship.houses > 0:
            raise GameLogicError("tried to mortgage a property with houses")
    
    relationship.mortgage = True
    relationship.save()

    if not free_mortgage:
        mortgage_value = target_square.buy_price // 2
        game.money[str(user.pk)] += mortgage_value
        game.save()

    return relationship

#TODO: si hay hipotecada no se cuenta grupo completo?

def _unset_mortgage( game: Game, user: CustomUser,target_square: BaseSquare, free_unset_mortgage: bool) -> PropertyRelationship:
    target_square = target_square.get_real_instance()
    if not (isinstance(target_square, PropertySquare) or
            isinstance(target_square, BridgeSquare) or
            isinstance(target_square, ServerSquare)):
        raise MaliciousUserInput(user, "tried to unset mortgage a non property/bridge/server square")
    
    relationship = _get_relationship(game=game, square=target_square)

    if relationship is None:
        raise MaliciousUserInput(user, "no user owns this square")

    if relationship.owner != user:
        raise MaliciousUserInput(user, "tried to unset mortgage an unowned property")

    if not relationship.mortgage:
        raise MaliciousUserInput(user, "tried to unset mortgage a not mortgaged property")

    relationship.mortgage = False
    relationship.save()
    target_square = target_square.get_real_instance()
    
    if not free_unset_mortgage:
        mortgage_value = target_square.buy_price // 2
        game.money[str(user.pk)] -= mortgage_value
        game.save()

    return relationship


def _move_player_logic(curr, total_steps) -> dict:
    path_log = [curr]
    passed_go = False

    for i in range(total_steps):
        next_id = None
        
        # TODO: dinero al pasar por la casilla de salida
        if isinstance(curr, BridgeSquare):
            # depending on steps 
            if total_steps % 2 == 0:
                curr = curr.out_successor
            else:
                curr = curr.in_successor
        elif isinstance(curr, ExitSquare):
            passed_go = True
            curr = curr.in_successor
        else:
            curr = curr.in_successor
        
        if curr is None:
            raise GameDesignError(f"no succesor found")
        
        path_log.append(curr.custom_id)

    if isinstance(curr, GoToJailSquare):
        curr = JailSquare.objects.first()
        if curr is None:
            raise GameDesignError(f"no jail square")
        return {"final_id": curr.custom_id, 
            "path": path_log, "passed_go": passed_go, "jailed": True}

    return {"final_id": curr.custom_id, 
            "path": path_log, "passed_go": passed_go, "jailed": False}

def _get_possible_destinations_ids(game: Game, user: CustomUser, dice_combinations: list[int]):
    destination_ids = []
    current_pos_id = game.positions[str(user.pk)]
    current_pos_square = _get_square_by_custom_id(current_pos_id).get_real_instance()

    for steps in dice_combinations:
        result = _move_player_logic(current_pos_square, steps)
        # We need a way to pass the jailed flag if there's only one destination
        # For now, let's just return the ids. _update_game_state_dices will have to re-check
        destination_ids.append(result["final_id"])

    return sorted(list(set(destination_ids)))


def _get_max_liquidation_value(game: Game, user: CustomUser) -> int:
    total_value = game.money[str(user.pk)] 
    
    properties = PropertyRelationship.objects.filter(
        game=game, 
        owner=user
    ).select_related('square')

    for rel in properties:
        square = rel.square.get_real_instance()
        
        if hasattr(square, 'build_price') and rel.houses > 0:
            total_value += rel.houses * (square.build_price // 2)
   
        if not rel.mortgage and hasattr(square, 'buy_price'):
            total_value += square.buy_price // 2

    return total_value

def calculate_net_worth(game: Game, user: CustomUser) -> int:
    total_value = game.money.get(str(user.pk), 0)
    
    properties = PropertyRelationship.objects.filter(game=game, owner=user).select_related('square')
    
    for rel in properties:
        square = rel.square.get_real_instance()
        
        # value of properties
        if not rel.mortgage and hasattr(square, 'buy_price'):
            total_value += square.buy_price
            
        # value of constructions
        if hasattr(square, 'build_price') and rel.houses > 0:
            total_value += rel.houses * square.build_price
            
    return total_value



class GameManager:
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

    @classmethod
    @database_sync_to_async
    def process_action(cls, game: Game, user: CustomUser, action: Action) -> Response:
        """
        The only public method exposed in the API. It processes each action
        in dedicated functions depending on the current phase and returns
        another action
        """
        if isinstance(action, ActionSurrender):
            # TODO
            pass

        if user != game.active_phase_player and not isinstance(action, ActionBid): # if aucction there are no turns
            raise MaliciousUserInput(user, "is not the active player")

        if game.phase == cls.ROLL_THE_DICES:
            if isinstance(action, ActionPayBail):
                return cls._pay_bail_logic(game, user, action)
            if not isinstance(action, ActionThrowDices):
                raise MaliciousUserInputAction(game, user, action)
            return cls._roll_dices_logic(game, user, action)
        elif game.phase == cls.CHOOSE_SQUARE:
            if not isinstance(action, ActionMoveTo):
                raise MaliciousUserInputAction(game, user, action)
            return cls._square_chosen_logic(game, user, action)
        elif game.phase == cls.MANAGEMENT:
            if not isinstance(action, (ActionBuySquare, ActionDropPurchase, ActionTakeTram, ActionDoNotTakeTram, ActionNextPhase)):
                raise MaliciousUserInputAction(game, user, action)
            return cls._management_logic(game, user, action)
        elif game.phase == cls.BUSINESS or game.phase == cls.LIQUIDATION:
            if not isinstance(action, (ActionBuild, ActionDemolish, ActionTradeProposal, ActionMortgageSet, ActionMortgageUnset, ActionNextPhase)):
                raise MaliciousUserInputAction(game, user, action)
            return cls._business_logic(game, user, action)
        elif game.phase == cls.ANSWER_TRADE_PROPOSAL:
            if not isinstance(action, ActionTradeAnswer):
                raise MaliciousUserInputAction(game, user, action)
            return cls._answer_trade_proposal_logic(game, user, action)
        elif game.phase == cls.AUCTION:
            if not isinstance(action, ActionBid):
                raise MaliciousUserInputAction(game, user, action)
            return cls._bid_property_auction_logic(game, user, action)
        
        raise GameLogicError(f"Fase no reconocida o no manejada: {game.phase}")

    @staticmethod
    def _pay_bail_logic(game: Game, user: CustomUser, action: ActionPayBail) -> Response:
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
        # roll the dices -> continue normally

        return Response()

    @staticmethod
    def _roll_dices_logic(game: Game, user: CustomUser, action: ActionThrowDices) -> Response: 
        d1 = random.randint(1,6)
        d2 = random.randint(1,6)
        d3 = random.randint(1,6) # 4-6 are the bus faces

        bus_is_numeric = d3 <= 3

        action.dice1 = d1
        action.dice2 = d2
        action.dice_bus = d3

        triples = bus_is_numeric and (d1 == d2 == d3)
        doubles = (d1 == d2) and not triples

        # jail logic
        remaining_jail_turns = game.jail_remaining_turns.get(str(user.pk), 0)
        is_jailed = remaining_jail_turns > 0
        
        if is_jailed:
            jail_sq = _get_user_square(game, user).get_real_instance()
            if isinstance(jail_sq, JailSquare):
                if remaining_jail_turns == 1:
                    game.money[str(user.pk)] -= jail_sq.bail_price
                    game.jail_remaining_turns[str(user.pk)] = 0
                    game.save()

                else:
                    if doubles:
                        # get out, moves out
                        game.jail_remaining_turns[str(user.pk)] = 0
                        action.streak = 0
                        game.streak = 0
                        game.save()
                    else:
                        # stays in jail
                        game.jail_remaining_turns[str(user.pk)] -= 1
                        game.phase = GameManager.BUSINESS
                        game.save()
                        
                        GameManager._update_game_state_dices(game, user, action)
                        return Response()

        if triples:
            action.triple = True
            square = _get_user_square(game, user)
            all_squares = BaseSquare.objects.filter(board=square.board)
            action.destinations = [s.custom_id for s in all_squares] #TODO: quitar carcel real
            
            GameManager._update_game_state_dices(game, user, action)
            return Response()

        elif doubles and not is_jailed: # doubles streak only if not getting out of jail via doubles
            if game.streak >= 2:
                jail_square = _get_jail_square()
                action.destinations = [jail_square.custom_id]
                game.streak = 0
                action.streak = 0
                
                # directly to jail 
                game.positions[str(user.pk)] = jail_square.custom_id
                game.jail_remaining_turns[str(user.pk)] = 3
                game.save()
                
                GameManager._update_game_state_dices(game, user, action)
                return Response()
            else:
                action.streak = game.streak + 1
        else:
            action.streak = 0
            game.streak = 0

        if bus_is_numeric:
            dice_combinations = [d1 + d2 + d3]
        else: 
            dice_combinations = [d1, d2, d1 + d2]

        dice_combinations = list(set(dice_combinations))

        action.destinations = _get_possible_destinations_ids(game, user, dice_combinations)
        
        GameManager._update_game_state_dices(game, user, action) 
        return Response()


    @staticmethod
    def _square_chosen_logic(game: Game, user: CustomUser, action: Action) -> Response:
        if not isinstance(action, ActionMoveTo):
            raise MaliciousUserInputAction(game, user, action)

        square = action.square

        if square.custom_id not in game.possible_destinations:
            raise MaliciousUserInput(user, "tried to move to an illegal square")

        GameManager._update_game_state_square_chosen(game, user, action)
        # FIXME
        return Response()
       
    @staticmethod
    def _management_logic(game: Game, user: CustomUser, action: Action) -> Response:
        """
        Logic of management phase, where the user can buy properties, pay bills etc

        first -> what is the action? -> check internally its current square and data associated ->
            Then check user info to update the game state accordingly and return next state
        TODO: Ir a business si no hay dobles y a dados si no
        """
        current_square = _get_user_square(game, user).get_real_instance()
        prop_rel = _get_relationship(game, current_square)

        if isinstance(action, ActionBuySquare):
            if isinstance(current_square, PropertySquare):
                # TODO: Check money
                game.money[str(user.pk)] -= current_square.buy_price
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

                game.phase = GameManager.BUSINESS
            elif isinstance(current_square, ServerSquare):
                game.money[str(user.pk)] -= current_square.buy_price
                new_property = PropertyRelationship(game=game, square=current_square, owner=user)
                new_property.save()

                game.phase = GameManager.BUSINESS
            else:
                raise MaliciousUserInputAction(game, user, action)
        elif isinstance(action, ActionDropPurchase):
            if isinstance(action.square, (PropertySquare, ServerSquare)):
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
                    game.positions[str(user.pk)] = square.custom_id
                else:
                    raise MaliciousUserInput(user, "tried to take a tram to a non tram square")

                game.phase = GameManager.BUSINESS
            else:
                raise MaliciousUserInputAction(game, user, action)
        elif isinstance(action, ActionDoNotTakeTram):
            game.phase = GameManager.BUSINESS
        elif isinstance(action, ActionNextPhase): # TODO: remove
            game.phase = GameManager.BUSINESS
        else:
            raise MaliciousUserInputAction(game, user, action)

        game.save()

        # FIXME
        return Response()

    @staticmethod
    
    def _business_logic(game: Game, user: CustomUser, action: Action) -> Response:
        """
        Unifies the business and liquidation phases
        TODO: Check that users money does not go to negative after:
            - ActionBuild
            - ActionTradeProposal
            - etc.
        """

        # Logic for the business phase where players can build houses, trade, etc.
        if isinstance(action, ActionBuild):
            """
            Check if squares are from user and if he has the complete group -> check limitations
            Check if there's no difference of 2 built houeses between group squares
            """

            # Check owner 
            building_square = action.square

            relationship = _build_square(game, user, building_square, action.houses, False)

        elif isinstance(action, ActionDemolish):
            # Similiar to build
            demolition_square = action.square

            relationship = _demolish_square(game, user, demolition_square, action.houses, False)

        elif isinstance(action, ActionTradeProposal):
            """
            Check if every number /property makes sense, then sned to frond a
            waiting message and to all players the action The destination
            players must decide whether or not to accept -> think of a way to
            do that -> front messages 
            """
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
                
                game.money[str(user.pk)] -= asked_money
                game.money[str(user.pk)] += offered_money

                game.save()

            game.phase = GameManager.BUSINESS
            game.active_phase_player = offering
            game.save()

            return Response()
        else:
            raise MaliciousUserInputAction(game, user, action)
        
    @staticmethod
    
    def _initiate_auction(game: Game, square: BaseSquare) -> Response:
        
        game.phase = GameManager.AUCTION

        game.auction_state = {
            "square_id": square.custom_id,
            "bids": {} 
        }
        game.save()
        

        return Response()
        
    @staticmethod
    
    def _bid_property_auction_logic(game: Game, user: CustomUser, action: Action) -> Response:

        if not isinstance(action, ActionBid):
            raise MaliciousUserInputAction(game, user, action)

        if not game.auction_state or "bids" not in game.auction_state:
            raise GameLogicError("Auction state is missing or corrupted")

        # user has not bid yet
        if user.pk in game.auction_state["bids"]:
            raise MaliciousUserInput(user, "User already placed a bid in this auction")

        # user has enough money -> compulsory for auctions
        amount = action.amount
        if amount > game.money[str(user.pk)]:
            raise MaliciousUserInput(user, "Bid amount exceeds current balance")

        # resgister bid
        game.auction_state["bids"][str(user.pk)] = amount
        game.save()

        return Response()
    
    @staticmethod
    @database_sync_to_async
    def _end_auction(game: Game) -> dict:
        ## call this with a timer -> end of the auction

        if game.phase != GameManager.AUCTION:
            raise GameLogicError("Tried to end auction but game is not in auction phase")

        auction_state = game.auction_state
        bids = auction_state.get("bids", {})
        square_id = auction_state.get("square_id")

        if not square_id:
            raise GameLogicError("Auction state missing square_id")

        square = _get_square_by_custom_id(square_id).get_real_instance()

        # no one bid
        if not bids:
            game.phase = GameManager.BUSINESS
            game.auction_state = {}
            game.save()

            return {"winner": None, "square_id": square_id, "amount": 0}

        max_bid = max(bids.values())
        winners = [k for k, v in bids.items() if v == max_bid]
        
        if len(winners) > 1:
            game.phase = GameManager.BUSINESS
            game.auction_state = {}
            game.save()
            return {"winner": None, "square_id": square_id, "amount": 0, "tie": True}

        highest_bidder_id = winners[0]
        highest_bid = max_bid
        
        winner = CustomUser.objects.get(pk=highest_bidder_id)
        
        game.money[str(winner.pk)] -= highest_bid
        
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

        game.phase = GameManager.BUSINESS
        game.auction_state = {}
        game.save()

        return {
            "winner": winner.pk,
            "winner_username": winner.username,
            "square_id": square_id,
            "amount": highest_bid
        }
    

    ###########################################################################
    # Updaters
    ###########################################################################

    @classmethod
    
    def _update_game_state_dices(cls, game: Game, user: CustomUser, action: ActionThrowDices) -> None:
        """
        Persiste la ActionThrowDices en BD usando su serializer y actualiza el
        estado de la partida (destinos posibles almacenados en el JSON del
        juego).
        """

        game.possible_destinations = action.destinations if len(action.destinations) > 1 else []
        game.streak = action.streak

        if len(action.destinations) > 1:
            game.phase = GameManager.CHOOSE_SQUARE
        elif len(action.destinations) == 1:
            dest_square_id = action.destinations[0]
            game.positions[str(user.pk)] = dest_square_id
            square = _get_square_by_custom_id(dest_square_id).get_real_instance()
            if isinstance(square, JailSquare):
                if game.money[str(user.pk)] < 0:
                    game.phase = GameManager.LIQUIDATION
                else:
                    GameManager._next_turn(game, user)
            else:
                if isinstance(square, ParkingSquare):
                    game.money[str(user.pk)] += game.parking_money # recently added
                    game.parking_money = 0
                game.phase = GameManager.MANAGEMENT
            # TODO: Casilla inicial

        game.save()

    @classmethod
    def _update_game_state_square_chosen(cls, game: Game, user: CustomUser, action: ActionMoveTo) -> None:
        """
        Persiste la ActionMoveTo en BD usando su serializer y actualiza
        la posición del jugador en la partida.
        """

        game.positions[str(user.pk)] = action.square.custom_id
        game.possible_destinations = []

        pay_price = _calculate_rent_price(game, user, action.square)
        if pay_price > 0:
            rel = _get_relationship(game, action.square)
            if rel is None:
                raise GameLogicError(f"no user owns this square")

            game.money[str(user.pk)] -= pay_price
            game.money[str(rel.owner.pk)] += pay_price

        # TODO: Check rules for this

        if isinstance(action.square, JailSquare):
            if game.money[str(user.pk)] < 0:
                game.phase = GameManager.LIQUIDATION
            else:
                GameManager._next_turn(game, user)
        elif isinstance(action.square, ParkingSquare):
            game.money[str(user.pk)] += game.parking_money
            game.parking_money = 0
        elif game.money[str(user.pk)] < 0:
            game.phase = GameManager.LIQUIDATION
        elif game.streak > 0:
            game.phase = GameManager.ROLL_THE_DICES
        else:
            game.phase = GameManager.MANAGEMENT

        game.save()

    @classmethod
    def _next_turn(cls, game, user) -> None:
        # TODO: cambiar el order, meter json de jugadores ordenados
        players_list = list(game.players.all().order_by('id')) 
        num_players = len(players_list)
        current_index = -1
        for i, p in enumerate(players_list):
            if p == game.active_turn_player:
                current_index = i
                break
        
        next_index = (current_index + 1) % num_players
        # The next active user is for both: phase and turn
        game.active_phase_player = players_list[next_index]
        game.active_turn_player = players_list[next_index]
        game.phase = GameManager.ROLL_THE_DICES

        game.save()
 
    @classmethod
    def _propose_trade(cls, game: Game,  user: CustomUser,action: ActionTradeProposal) -> None:
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
        if game.active_turn_player == user:
            cls._next_turn(game, user)

        game.players.remove(user)
        #TODO: quitar de la lista de jugadores ordenados
        game.save()
        
        # TODO: if only one left -> he wins
