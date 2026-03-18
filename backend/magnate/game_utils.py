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
