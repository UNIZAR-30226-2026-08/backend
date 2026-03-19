from .models import *
from magnate.exceptions import *
from typing import Optional
from django.core.exceptions import MultipleObjectsReturned


def _build_square(game: Game, 
                  user: CustomUser, 
                  building_square: BaseSquare, 
                  number_built: int,
                  free_build: bool) -> PropertyRelationship:
    """
    Builds houses or hotels on a property.

    Validates that the user owns the complete color group and respects 
    the uniform building rule.

    Args:
        game (Game): The current game instance.
        user (CustomUser): The user attempting to build.
        building_square (BaseSquare): The target property square.
        number_built (int): Number of buildings to construct.
        free_build (bool): If True, the user is not charged for the construction.

    Returns:
        PropertyRelationship: The updated ownership relationship.

    Raises:
        MaliciousUserInput: If the user does not own the full group, violates 
            uniform building rules, or tries to build beyond the max limit.
        GameLogicError: If negative house values are encountered.
    """
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

    stats = PlayerGameStatistic.objects.get(user=user,game=game)
    stats.built_houses += number_built

    if not free_build:
        coste = building_square.build_price * number_built

        game.money[str(user.pk)] -= coste
        game.save()
        stats.lost_money += coste

    stats.save()

    return relationship  #ack



def _demolish_square(game: Game, 
                     user: CustomUser, 
                     demolition_square: BaseSquare, 
                     number_demolished: int,
                     free_demolish: bool) -> PropertyRelationship:
    """
    Demolishes houses/hotels on a property and returns money to the user.

    Ensures that uniform building rules are respected during demolition.

    Args:
        game (Game): The current game instance.
        user (CustomUser): The user attempting to demolish.
        demolition_square (BaseSquare): The square where buildings will be demolished.
        number_demolished (int): The amount of houses to demolish.
        free_demolish (bool): If True, no money is refunded to the user.

    Returns:
        PropertyRelationship: The updated ownership relationship.

    Raises:
        MaliciousUserInput: If the property is unowned, owned by someone else, 
            is not a property square, or violates uniform building rules.
    """
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

    stats = PlayerGameStatistic.objects.get(user=user,game=game)
    stats.demolished_houses += number_demolished
    
    if not free_demolish:
        coste = demolition_square.build_price
        
        game.money[str(user.pk)] += coste // 2 * number_demolished
        game.save()
        stats.won_money += coste // 2 * number_demolished

    stats.save()

    return relationship


def _get_jail_square() -> BaseSquare:
    """
    Retrieves the designated Jail square for the board.

    Returns:
        BaseSquare: The JailSquare instance.

    Raises:
        GameDesignError: If there are no jail squares or too many jail squares.
    """
    try:
        return JailSquare.objects.get()
    except JailSquare.DoesNotExist:
        raise GameDesignError("there are no jail squares in the game")
    except MultipleObjectsReturned:
        raise GameDesignError("there are too many jail squares")


#TODO: si hay hipotecada no se cuenta grupo completo?
def _unset_mortgage(game: Game, user: CustomUser, target_square: BaseSquare, free_unset_mortgage: bool) -> PropertyRelationship:
    """
    Lifts the mortgage from a property by paying the required fee.

    Args:
        game (Game): The current game instance.
        user (CustomUser): The user lifting the mortgage.
        target_square (BaseSquare): The property to unmortgage.
        free_unset_mortgage (bool): If True, the user is not charged.

    Returns:
        PropertyRelationship: The updated relationship.

    Raises:
        MaliciousUserInput: If not owned, not mortgaged, or wrong type of square.
    """
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
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.lost_money += mortgage_value
        

    return relationship


def _get_relationship(game: Game, square: BaseSquare) -> Optional[PropertyRelationship]:
    """
    Gets the ownership relationship between a game and a specific square.

    Args:
        game (Game): The current game instance.
        square (BaseSquare): The property square to check.

    Returns:
        Optional[PropertyRelationship]: The relationship object if owned, None otherwise.

    Raises:
        GameLogicError: If more than one owner is found for the same square.
    """
    try:
        return PropertyRelationship.objects.get(game=game, square=square)
    except PropertyRelationship.DoesNotExist:
        return None
    except MultipleObjectsReturned:
        raise GameLogicError("more than one owners for the same square")



def _get_square_by_custom_id(custom_id: int) -> BaseSquare:
    """
    Retrieves a BaseSquare instance by its custom_id.

    Args:
        custom_id (int): The custom identifier of the square.

    Returns:
        BaseSquare: The square instance.

    Raises:
        GameLogicError: If no square with the given custom_id exists.
    """
    square = BaseSquare.objects.filter(custom_id=custom_id).first()
    if square is None:
        raise GameLogicError(f"no square with id {custom_id}")

    return square

def _get_user_square(game: Game, user: CustomUser) -> BaseSquare:
    """
    Retrieves the square where a specific user is currently located.

    Args:
        game (Game): The current game instance.
        user (CustomUser): The user whose position is being queried.

    Returns:
        BaseSquare: The square where the user is currently standing.

    Raises:
        GameLogicError: If the user is not part of the game.
    """
    user_key = str(user.pk) if str(user.pk) in game.positions else user.pk
    
    if user_key not in game.positions:
        raise GameLogicError(f"user {user} not in the game")
        
    return _get_square_by_custom_id(game.positions[user_key])

def _calculate_rent_price(game: Game, user: CustomUser, square: BaseSquare) -> int:
    """
    Calculates the rent price a user must pay when landing on a square.

    Handles different logic for PropertySquares (houses), TramSquares, 
    BridgeSquares, and ServerSquares based on ownership and multipliers.

    Args:
        game (Game): The current game instance.
        user (CustomUser): The user landing on the square.
        square (BaseSquare): The square being landed on.

    Returns:
        int: The calculated rent amount to pay. Returns 0 if unowned or owned by the user.

    Raises:
        GameDesignError: If the rent arrays on the square are incorrectly configured.
        GameLogicError: If an unexpected condition occurs during calculation.
    """
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
            return square.rent_prices[0] * 2  # grupo completo = doble del alquiler base
        elif houses == 1:
            return square.rent_prices[1]
        elif houses == 2:
            return square.rent_prices[2]
        elif houses == 3:
            return square.rent_prices[3]
        elif houses == 4:
            return square.rent_prices[4]
        elif houses == 5:  # hotel
            return square.rent_prices[5]
    
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



#TODO: si hay hipotecada no se cuenta grupo completo?
def _set_mortgage(game: Game, user: CustomUser, target_square: BaseSquare, free_mortgage: bool) -> PropertyRelationship:
    """
    Mortgages a property to receive immediate funds.

    Args:
        game (Game): The current game instance.
        user (CustomUser): The user attempting the mortgage.
        target_square (BaseSquare): The property to be mortgaged.
        free_mortgage (bool): If True, no money is added to the user's balance.

    Returns:
        PropertyRelationship: The updated relationship.

    Raises:
        MaliciousUserInput: If not owned, already mortgaged, or wrong type of square.
        GameLogicError: If trying to mortgage a property that still has houses built on it.
    """
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
    stats = PlayerGameStatistic.objects.get(user=user,game=game)
    stats.num_mortgages += 1

    if not free_mortgage:
        mortgage_value = target_square.buy_price // 2
        game.money[str(user.pk)] += mortgage_value
        
        stats.won_money += mortgage_value
        game.save()

    stats.save()

    return relationship


def _move_player_logic(curr: BaseSquare, total_steps: int) -> dict:
    """
    Calculates the final destination and path of a player moving a set number of steps.

    Handles specific movement mechanics such as passing Go, taking bridges, 
    and landing on the "Go to Jail" square.

    Args:
        curr (BaseSquare): The starting square instance.
        total_steps (int): The number of squares to move forward.

    Returns:
        dict: A dictionary containing:
            - final_id (int): Custom ID of the final square.
            - path (list[int]): List of custom IDs traversed.
            - passed_go (bool): True if the player passed the Go square.
            - jailed (bool): True if the player landed on Go to Jail.

    Raises:
        GameDesignError: If a successor square cannot be found or the jail doesn't exist.
    """
    if curr is None:
        raise GameLogicError('current square is None')
        return None
    
    path_log = [curr.custom_id]
    passed_go = False

    for i in range(total_steps):
        if isinstance(curr, BridgeSquare):
            if curr.out_successor is None:
                raise GameDesignError('bridge without out successor')
            if curr.in_successor is None:
                raise GameDesignError('bridge without in successor')
            # depending on steps 
            if total_steps % 2 == 0:
                curr = curr.out_successor
            else:
                curr = curr.in_successor
        else:
            if curr.in_successor is None:
                raise GameDesignError(f'square {curr.custom_id} without in successor')
            curr = curr.in_successor
        
        if isinstance(curr, ExitSquare):
            passed_go = True
        
        path_log.append(curr.custom_id)

    if isinstance(curr, GoToJailSquare):
        jail = JailSquare.objects.first()
        if jail is None:
            raise GameDesignError('no jail in game')
        curr = jail
        if curr is None:
            raise GameDesignError(f"no jail square")
        return {"final_id": curr.custom_id, 
            "path": path_log, "passed_go": passed_go, "jailed": True}

    return {"final_id": curr.custom_id, 
            "path": path_log, "passed_go": passed_go, "jailed": False}

def _get_possible_destinations_ids(game: Game, user: CustomUser, dice_combinations: list[int]) ->tuple[list[int], dict[int, bool]]:
    """
    Calculates all possible destination square IDs based on dice combinations.

    Args:
        game (Game): The current game instance.
        user (CustomUser): The user whose possible moves are calculated.
        dice_combinations (list[int]): Possible total steps generated by the dice roll.

    Returns:
        list[int]: A sorted list of unique destination custom_ids.
    """
    destination_ids = []
    current_pos_id = game.positions[str(user.pk)]
    passed_go_map: dict[int, bool] = {}
    current_pos_square = _get_square_by_custom_id(current_pos_id).get_real_instance()

    for steps in dice_combinations:
        result = _move_player_logic(current_pos_square, steps)
        # We need a way to pass the jailed flag if there's only one destination
        # For now, let's just return the ids. _update_game_state_dices will have to re-check
        dest_id = result["final_id"]
        destination_ids.append(result["final_id"])
        passed_go_map[dest_id] = passed_go_map.get(dest_id, False) or result["passed_go"]


    return sorted(list(set(destination_ids))), passed_go_map



def _get_max_liquidation_value(game: Game, user: CustomUser) -> int:
    """
    Calculates the absolute maximum money a user can raise by liquidating all assets.

    This includes selling all houses and mortgaging all unmortgaged properties.

    Args:
        game (Game): The current game instance.
        user (CustomUser): The target user.

    Returns:
        int: The maximum liquidation value in cash.
    """
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

def _calculate_net_worth(game: Game, user: CustomUser) -> int:
    """
    Calculates the total net worth of a user (Cash + Property Value + Building Value).

    Args:
        game (Game): The current game instance.
        user (CustomUser): The user to calculate for.

    Returns:
        int: The total calculated net worth.
    """
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


def _handle_square_arrival(game: Game, user: CustomUser, square: BaseSquare, passed_go: bool) -> Optional[FantasyEvent]:
    """
    Centralizes the logic for landing on squares: awarding money (Go/Parking), 
    generating Fantasy events, and managing Jail landings.

    Args:
        game (Game): The current game instance.
        user (CustomUser): The acting user.
        square (BaseSquare): The square where the user arrived.
        passed_go (bool): Whether the move path included the ExitSquare.

    Returns:
        Optional[FantasyEvent]: A generated fantasy event if the user landed on a FantasySquare.
    """
    # 1. Handle passing/landing on Exit (Go)
    if passed_go:
        exit_square = ExitSquare.objects.first()
        if exit_square is not None:
            game.money[str(user.pk)] += exit_square.init_money
            stats = PlayerGameStatistic.objects.get(user=user, game=game)
            stats.won_money += exit_square.init_money
            stats.save()

    # 2. Handle landing effects
    real_square = square.get_real_instance()

    # Parking logic
    if isinstance(real_square, ParkingSquare):
        game.money[str(user.pk)] += game.parking_money
        stats = PlayerGameStatistic.objects.get(user=user, game=game)
        stats.won_money += game.parking_money
        stats.save()
        game.parking_money = 0
    
    # Fantasy logic
    elif isinstance(real_square, FantasySquare):
        from .fantasy import FantasyEventFactory
        fantasy_event = FantasyEventFactory.generate()
        fantasy_event.save()
        game.phase = Game.GamePhase.choose_fantasy
        game.fantasy_event = fantasy_event
        return fantasy_event

    # Jail logic (landing on it, not being sent to it)
    elif isinstance(real_square, JailSquare):
        if game.money[str(user.pk)] < 0:
            game.phase = Game.GamePhase.liquidation
        # Note: Turn transition is handled by the caller to avoid circular imports
    
    return None
