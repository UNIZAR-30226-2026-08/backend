from magnate.models import *
from channels.db import database_sync_to_async
from collections import defaultdict
import random

from magnate.exceptions import GameLogicError

from magnate.game_utils import _build_square, _demolish_square, _get_jail_square, _unset_mortgage

class FantasyEventFactory:
    @staticmethod
    def generate() -> FantasyEvent:
        """
        Generate a random FantasyEvent with a rolled type, card cost, and optional value.

        The fantasy type is chosen uniformly at random from all values defined in
        ``FantasyEvent.FantasyType``. Depending on the type, a ``card_cost`` (what the
        player pays to buy the card) and an optional ``value`` (monetary amount or
        multiplier used when the event is applied) are assigned.

        Cost / value summary by type:

        | Type                          | Cost | Value options             |
        | ----------------------------- | ---- | ------------------------- |
        | winPlainMoney                 | 130  | 20, 60, 120, 150, 200     |
        | winRatioMoney                 | 500  | 1, 2, 5, 10 (%)           |
        | losePlainMoney                | 80   | 40, 80, 120, 150, 200     |
        | loseRatioMoney                | 30   | 1, 2, 5, 10 (%)           |
        | shareMoneyAll                 | 5    | 20, 30, 50                |
        | everybodySendsYouMoney        | 120  | 20, 30, 50                |
        | doubleOrNothing               | 50   | —                         |
        | getParkingMoney               | 500  | —                         |
        | goToJail                      | 25   | —                         |
        | sendToJail                    | 80   | —                         |
        | everybodyToJail               | 50   | —                         |
        | shufflePositions              | 50   | —                         |
        | moveAnywhereRandom            | 50   | —                         |
        | moveOpponentAnywhereRandom    | 60   | —                         |
        | magnetism                     | 100  | —                         |
        | goToStart                     | 90   | —                         |
        | breakOpponentHouse            | 150  | —                         |
        | breakOwnHouse                 | 30   | —                         |
        | freeHouse                     | 80   | —                         |
        | reviveProperty                | 100  | —                         |
        | earthquake                    | 200  | —                         |

        Returns:
            FantasyEvent: A new, unsaved ``FantasyEvent`` instance with ``fantasy_type``,
                ``card_cost``, and ``value`` (``None`` when not applicable) populated.
        """
        fantasy_type = random.choice(FantasyEvent.FantasyType.values)

        value = None
        card_cost = None

        if fantasy_type == 'winPlainMoney':
            card_cost = 130
            rand = random.randrange(5)
            if(rand == 0):
                value = 20
            elif(rand == 1):
                value = 60
            elif(rand == 2):
                value = 120
            elif(rand == 3):
                value = 150
            elif(rand == 4):
                value = 200
                
            
        elif fantasy_type == 'winRatioMoney':
            card_cost = 500
            rand = random.randrange(4)
            if(rand == 0):
                value = 1
            elif(rand == 1):
                value = 2
            elif(rand == 2):
                value = 5
            elif(rand == 3):
                value = 10


        elif fantasy_type == 'losePlainMoney':
            card_cost = 80
            rand = random.randrange(5)
            if(rand == 0):
                value = 40
            elif(rand == 1):
                value = 80
            elif(rand == 2):
                value = 120
            elif(rand == 3):
                value = 150
            elif(rand == 4):
                value = 200


        elif fantasy_type == 'loseRatioMoney':
            card_cost = 30
            rand = random.randrange(4)
            if(rand == 0):
                value = 1
            elif(rand == 1):
                value = 2
            elif(rand == 2):
                value = 5
            elif(rand == 3):
                value = 10

        elif fantasy_type == 'breakOpponentHouse':
            card_cost = 150

        elif fantasy_type == 'breakOwnHouse':
            card_cost = 30

        elif fantasy_type == 'shufflePositions':
            card_cost = 50

        elif fantasy_type == 'moveAnywhereRandom':
            card_cost = 50

        elif fantasy_type == 'moveOpponentAnywhereRandom':
            card_cost = 60

        elif fantasy_type == 'shareMoneyAll':
            card_cost = 5
            rand = random.randrange(3)
            if(rand == 0):
                value = 20
            elif(rand == 1):
                value = 30
            elif(rand == 2):
                value = 50

        elif fantasy_type == 'freeHouse':
            card_cost = 80

        elif fantasy_type == 'goToJail':
            card_cost = 25
        
        elif fantasy_type == 'sendToJail':
            card_cost = 80

        elif fantasy_type == 'everybodyToJail':
            card_cost = 50
        
        elif fantasy_type == 'doubleOrNothing':
            card_cost = 50

        elif fantasy_type == 'getParkingMoney':
            card_cost = 500

        elif fantasy_type == 'reviveProperty':
            card_cost = 100

        elif fantasy_type == 'earthquake':
            card_cost = 200

        elif fantasy_type == 'everybodySendsYouMoney':
            card_cost = 120
            rand = random.randrange(3)
            if(rand == 0):
                value = 20
            elif(rand == 1):
                value = 30
            elif(rand == 2):
                value = 50

        elif fantasy_type == 'magnetism':
            card_cost = 100

        elif fantasy_type == 'goToStart':
            card_cost = 90

        return FantasyEvent(
                fantasy_type = fantasy_type,
                value = value,
                card_cost = card_cost
                )

#@database_sync_to_async
def apply_fantasy_event(game: Game, user: CustomUser , fantasy_event: FantasyEvent) -> FantasyResult:
    """
    Apply a FantasyEvent to the current game state and return the outcome.

    Executes the side-effects of ``fantasy_event`` on ``game`` — mutating money,
    positions, jail state, and/or property house counts — then saves all affected
    model instances and increments the triggering player's ``num_fantasy_events``
    statistic.

    The ``result`` field of the returned ``FantasyResult`` varies by event type:

    **Always** ``None``:
        ``winPlainMoney``, ``winRatioMoney``, ``losePlainMoney``, ``loseRatioMoney``,
        ``shareMoneyAll``, ``everybodySendsYouMoney``, ``getParkingMoney``,
        ``goToJail``, ``everybodyToJail``, ``shufflePositions``,
        ``moveAnywhereRandom``, ``magnetism``, ``goToStart``

        Also ``None`` for property events when no valid target exists at the time of
        the call (no houses, no mortgaged properties, etc.).

    **Single targeted square** — ``{"square": custom_id}``:
        ``breakOpponentHouse``, ``breakOwnHouse``, ``freeHouse``, ``reviveProperty``

    **Multiple targeted squares** — ``{"squares": [custom_id, ...]}``:
        ``earthquake`` — one entry per property that had a house removed.

    **Targeted player** — ``{"target_player": pk}``:
        ``moveOpponentAnywhereRandom``, ``sendToJail``

    **Outcome flag** — ``{"doubled": bool}``:
        ``doubleOrNothing`` — ``True`` if the player's money was doubled,
        ``False`` if it was zeroed.

    House-targeting logic for break/build events follows Monopoly-standard
    even-build rules: only properties in the group with the current maximum
    (for demolition) or minimum (for construction) house count are eligible,
    ensuring the house count within a colour group remains as even as possible.

    Args:
        game (Game): The active game instance. ``game.money``, ``game.positions``,
            ``game.jail_remaining_turns``, and ``game.parking_money`` may be
            mutated and saved.
        user (CustomUser): The player who triggered the event. Used as the default
            actor for all money and property operations; some events target a
            randomly selected opponent instead.
        fantasy_event (FantasyEvent): The event to apply. Must have a valid
            ``fantasy_type``; ``value`` must not be ``None`` for event types that
            require it (plain/ratio money, share events).

    Returns:
        FantasyResult: An unsaved result object linking the original ``fantasy_event``
            to a ``result`` dict (or ``None``) as described above.

    Raises:
        GameLogicError: If ``fantasy_event.fantasy_type`` is not a recognised value.
        Exception: If a money-based event is called with ``fantasy_event.value is None``.
        Exception: If internal targeting invariants are violated (e.g. no valid
            candidate found after filtering — indicates a logic bug, not a user error).
    """
    stats = PlayerGameStatistic.objects.get(user=user,game=game)
    stats.num_fantasy_events += 1
    stats.save()

    if fantasy_event.fantasy_type == 'winPlainMoney':
        if fantasy_event.value is None:
            raise Exception('FantasyEvent value is None')
        
        money_to_add = fantasy_event.value
        game.money[str(user.pk)] += money_to_add
        game.save()
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.won_money += money_to_add
        stats.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
        )
    
    elif fantasy_event.fantasy_type == 'winRatioMoney':
        if fantasy_event.value is None:
            raise Exception('FantasyEvent value is None')

        ratio_to_add = fantasy_event.value
        previous_money = game.money[str(user.pk)]
        game.money[str(user.pk)] = int(game.money[str(user.pk)] * (1 + ratio_to_add/100))
        game.save()
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.won_money += game.money[str(user.pk)] - previous_money
        stats.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
        )
    
    elif fantasy_event.fantasy_type == 'losePlainMoney':
        if fantasy_event.value is None:
            raise Exception('FantasyEvent value is None')
        
        money_to_sub = fantasy_event.value
        game.money[str(user.pk)] -= money_to_sub
        game.save()
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.lost_money += money_to_sub
        stats.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
        )
    
    elif fantasy_event.fantasy_type == 'loseRatioMoney':
        if fantasy_event.value is None:
            raise Exception('FantasyEvent value is None')

        ratio_to_sub = fantasy_event.value
        previous_money = game.money[str(user.pk)]
        game.money[str(user.pk)] = int(game.money[str(user.pk)] * (1 - ratio_to_sub/100))
        game.save()
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.lost_money += previous_money - game.money[str(user.pk)]
        stats.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
        )
    
    elif fantasy_event.fantasy_type == 'breakOpponentHouse': 
        #random opponent, random house
        properties = PropertyRelationship.objects.filter(
            game=game,
            houses__gte=1, # at least 1 house
            square__propertysquare__isnull=False # look for properties
                                                 # that support houses
        ).exclude(
            owner=user
        ).select_related('square__propertysquare','owner')

        if not properties.exists():
            return FantasyResult(
                fantasy_event = fantasy_event,
                result = None
            )
        
        groups = defaultdict(list)
        for prop in properties:
            key = (prop.owner, prop.square.get_real_instance().group)
            groups[key].append(prop)

        valid_candidates = []
        for (owner, color_group), props_in_group in groups.items():
            max_houses = max(prop.houses for prop in props_in_group)
            if max_houses > 0:
                for prop in props_in_group:
                    if prop.houses == max_houses:
                        valid_candidates.append(prop)

        if valid_candidates:
            target_prop : PropertyRelationship = random.choice(valid_candidates)
        else:
            raise Exception("esto no deberia pasar")
        
        result_property = _demolish_square(game=game, user=target_prop.owner, demolition_square=target_prop.square,
                         number_demolished=1, free_demolish=True)

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = {'square': result_property.square.custom_id}
            )
    
    elif fantasy_event.fantasy_type == 'breakOwnHouse':
        #fantasy maker user, random house
        properties = PropertyRelationship.objects.filter(
            game=game,
            houses__gte=1, # at least 1 house
            owner=user,
            square__propertysquare__isnull=False
        ).select_related('square')

        if not properties.exists():
            return FantasyResult(
                fantasy_event = fantasy_event,
                result = None # empty, no house broken
            )
        
        groups = defaultdict(list)
        for prop in properties:
            key = prop.square.get_real_instance().group
            groups[key].append(prop)

        valid_candidates = []
        for group, props_in_group in groups.items():
            max_houses = max(prop.houses for prop in props_in_group)
            if max_houses > 0:
                for prop in props_in_group:
                    if prop.houses == max_houses:
                        valid_candidates.append(prop)

        if valid_candidates:
            target_prop : PropertyRelationship = random.choice(valid_candidates)
        else:
            # FIXME
            raise Exception("esto no deberia pasar")
        
        result_property = _demolish_square(game=game, user=target_prop.owner, demolition_square=target_prop.square,
                         number_demolished=1, free_demolish=True)

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = {'square': result_property.square.custom_id}
            )

    elif fantasy_event.fantasy_type == 'shufflePositions':
        id_jail = _get_jail_square().custom_id
        #move everybody to random square
        ids = list(BaseSquare.objects.values_list('custom_id', flat=True))
        ids.remove(id_jail)
        for player in game.players.all():
            if game.positions[str(player.pk)] != id_jail:
                rand_square_id = random.choice([n for n in ids if n != game.positions[str(player.pk)]])
                game.positions[str(player.pk)] = rand_square_id

        game.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
            )
    
    elif fantasy_event.fantasy_type == 'moveAnywhereRandom':
        id_jail = _get_jail_square().custom_id
        if(game.positions[str(user.pk)] != id_jail):
            ids = list(BaseSquare.objects.values_list('custom_id', flat=True))
            ids.remove(id_jail)
            rand_square_id = random.choice([n for n in ids if n != game.positions[str(user.pk)]])
            game.positions[str(user.pk)] = rand_square_id
            game.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
            )

    elif fantasy_event.fantasy_type == 'moveOpponentAnywhereRandom':
        opponents = game.players.exclude(pk=user.pk)
        if not opponents.exists():
            raise Exception('Catatrofe no deberias estar aqui')
        target_player = random.choice(list(opponents)) #con un order by ? tambien rularia

        id_jail = _get_jail_square().custom_id
        if(game.positions[str(target_player.pk)] != id_jail):
            ids = list(BaseSquare.objects.values_list('custom_id', flat=True))
            ids.remove(id_jail)
            rand_square_id = random.choice([n for n in ids if n != game.positions[str(target_player.pk)]])
            game.positions[str(target_player.pk)] = rand_square_id
            game.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = {'target_player':target_player.pk}
            )
    
    elif fantasy_event.fantasy_type == 'shareMoneyAll':
        if fantasy_event.value is None:
            raise Exception('FantasyEvent value is None')
        
        money_to_share = fantasy_event.value

        opponents = game.players.exclude(pk=user.pk)
        opponents_list = list(opponents)
        opponents_count = len(opponents_list)

        for player in opponents_list:
            game.money[str(player.pk)] += money_to_share
            stats = PlayerGameStatistic.objects.get(user=player,game=game)
            stats.won_money += money_to_share
            stats.save()


        game.money[str(user.pk)] -= money_to_share*opponents_count
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.lost_money += money_to_share*opponents_count
        stats.save()

        game.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
            )
    
    elif fantasy_event.fantasy_type == 'freeHouse':
        properties = PropertyRelationship.objects.filter(
            game=game,
            houses__lt=5,
            houses__gte=0,
            owner=user,
        ).select_related('square')

        if not properties.exists():
            return FantasyResult(
                fantasy_event = fantasy_event,
                result = None
            )
        
        groups = defaultdict(list)
        for prop in properties:
            key = prop.square.get_real_instance().group
            groups[key].append(prop)

        valid_candidates = []
        for color_group, props_in_group in groups.items():
            min_houses = min(prop.houses for prop in props_in_group)
            for prop in props_in_group:
                if prop.houses == min_houses:
                    valid_candidates.append(prop)

        if valid_candidates:
            target_prop = random.choice(valid_candidates)
        else:
            raise Exception('creo que esto no puede ocurrir')
        
        result_property = _build_square(game=game, user=target_prop.owner, building_square=target_prop.square,
                         number_built=1, free_build=True)

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = {'square': result_property.square.custom_id}
        )
    
    elif fantasy_event.fantasy_type == 'goToJail':
        jail_id = _get_jail_square().custom_id
        game.positions[str(user.pk)] = jail_id
        game.jail_remaining_turns[str(user.pk)] = 3
        game.save()

        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.times_in_jail += 1
        stats.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
        )
    
    elif fantasy_event.fantasy_type == 'sendToJail':
        target_player = random.choice(game.players.exclude(pk=user.pk))
        jail_id = _get_jail_square().custom_id
        game.positions[str(target_player.pk)] = jail_id
        game.jail_remaining_turns[str(target_player.pk)] = 3
        game.save()

        stats = PlayerGameStatistic.objects.get(user=target_player,game=game)
        stats.times_in_jail += 1
        stats.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = {'target_player':target_player.pk}
        )
    
    elif fantasy_event.fantasy_type == 'everybodyToJail':
        jail_id = _get_jail_square().custom_id
        for player in game.players.all():
            game.positions[str(player.pk)] = jail_id
            game.jail_remaining_turns[str(player.pk)] = 3
            stats = PlayerGameStatistic.objects.get(user=player,game=game)
            stats.times_in_jail += 1
            stats.save()

        game.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
        )
    
    elif fantasy_event.fantasy_type == 'doubleOrNothing':
        r = random.choice([True,False])
        if r:
            stats = PlayerGameStatistic.objects.get(user=user,game=game)
            stats.won_money += game.money[str(user.pk)]
            stats.save()
            game.money[str(user.pk)] *= 2
        else:
            stats = PlayerGameStatistic.objects.get(user=user,game=game)
            stats.lost_money += game.money[str(user.pk)]
            stats.save()
            game.money[str(user.pk)] = 0
        game.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = {'doubled': r}
        )
        
    
    elif fantasy_event.fantasy_type == 'getParkingMoney':
        game.money[str(user.pk)] += game.parking_money
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.won_money += game.parking_money
        stats.save()
        game.parking_money = 0
        game.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
        )
    
    elif fantasy_event.fantasy_type == 'reviveProperty':
        properties = PropertyRelationship.objects.filter(
            game=game, owner=user, mortgage=True
        )

        if not properties.exists():
            return FantasyResult(
                fantasy_event = fantasy_event,
                result = None
            )

        target = random.choice(properties)

        result = _unset_mortgage(user=user,game=game,target_square=target.square,free_unset_mortgage=True)

        return FantasyResult(
                fantasy_event = fantasy_event,
                result = {'square': result.square.custom_id}
            )

    
    elif fantasy_event.fantasy_type == 'earthquake':
        properties = PropertyRelationship.objects.filter(
            game=game,
            houses__gte=1,
        ).select_related('square')

        if not properties.exists():
            return FantasyResult(
                fantasy_event = fantasy_event,
                result = None
                )

        demolished_houses = []

        for prop in properties:
            result_property = _demolish_square(game=game, user=prop.owner, demolition_square=prop.square,
                         number_demolished=1, free_demolish=True)
            demolished_houses.append(result_property.square.custom_id)

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = {'squares': demolished_houses}
        )
    
    elif fantasy_event.fantasy_type == 'everybodySendsYouMoney':
        if fantasy_event.value is None:
            raise Exception('FantasyEvent value is None')
        
        money_to_share = fantasy_event.value

        opponents = game.players.exclude(pk=user.pk)
        opponents_list = list(opponents)
        opponents_count = len(opponents_list)

        for player in opponents_list:
            game.money[str(player.pk)] -= money_to_share
            stats = PlayerGameStatistic.objects.get(user=player,game=game)
            stats.lost_money += money_to_share
            stats.save()

        game.money[str(user.pk)] += money_to_share*opponents_count
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.won_money += money_to_share*opponents_count
        stats.save()

        game.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
            )
    
    elif fantasy_event.fantasy_type == 'magnetism':
        id_jail = _get_jail_square().custom_id
        target_id = game.positions[str(user.pk)]
        for player in game.players.all(): #no caso especial para el que lanza, se moverá al mismo sitio
            if(game.positions[str(player.pk)] != id_jail):
                game.positions[str(player.pk)] = target_id

        game.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
            )

    elif fantasy_event.fantasy_type == 'goToStart':
        id_jail = _get_jail_square().custom_id
        start_square = ExitSquare.objects.first()
        if start_square is None:
            raise Exception('No encuentra casilla de salida')
        
        if(game.positions[str(user.pk)] != id_jail):
            game.positions[str(user.pk)] = start_square.custom_id
            game.money[str(user.pk)] += start_square.init_money
            stats = PlayerGameStatistic.objects.get(user=user,game=game)
            stats.won_money += start_square.init_money
            stats.save()
            game.save()

        return FantasyResult(
            fantasy_event = fantasy_event,
            result = None
            )
    else: 
        raise GameLogicError(f"undefined fantasy event: {fantasy_event.fantasy_type}")

