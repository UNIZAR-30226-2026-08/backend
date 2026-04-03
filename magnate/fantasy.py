from magnate.models import *
from channels.db import database_sync_to_async
from collections import defaultdict
import random

from magnate.game_utils import _build_square, _demolish_square, _get_jail_square, _unset_mortgage

class FantasyEventFactory:
    @staticmethod
    def generate() -> FantasyEvent:
        """
        Generates a random FantasyEvent with an associated card cost and potential value.

        Returns:
            FantasyEvent: An instance of FantasyEvent configured with the rolled type, values, and cost.
        """
        fantasy_type = random.choice(FantasyEvent.FantasyType.values)

        values = None
        card_cost = None

        if fantasy_type == 'winPlainMoney':
            card_cost = 130
            rand = random.randrange(5)
            if(rand == 0):
                values = {'money': 20}
            elif(rand == 1):
                values = {'money': 60}
            elif(rand == 2):
                values = {'money': 120}
            elif(rand == 3):
                values = {'money': 150}
            elif(rand == 4):
                values = {'money': 200}
                
            
        elif fantasy_type == 'winRatioMoney':
            card_cost = 500 #TODO: carisimo, no?
            rand = random.randrange(4)
            if(rand == 0):
                values = {'money': 1}
            elif(rand == 1):
                values = {'money': 2}
            elif(rand == 2):
                values = {'money': 5}
            elif(rand == 3):
                values = {'money': 10}


        elif fantasy_type == 'losePlainMoney':
            card_cost = 80
            rand = random.randrange(5)
            if(rand == 0):
                values = {'money': 40}
            elif(rand == 1):
                values = {'money': 80}
            elif(rand == 2):
                values = {'money': 120}
            elif(rand == 3):
                values = {'money': 150}
            elif(rand == 4):
                values = {'money': 200}


        elif fantasy_type == 'loseRatioMoney':
            card_cost = 30
            rand = random.randrange(4)
            if(rand == 0):
                values = {'money': 1}
            elif(rand == 1):
                values = {'money': 2}
            elif(rand == 2):
                values = {'money': 5}
            elif(rand == 3):
                values = {'money': 10}

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
                values = {'money': 20}
            elif(rand == 1):
                values = {'money': 30}
            elif(rand == 2):
                values = {'money': 50}

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
                values = {'money': 20}
            elif(rand == 1):
                values = {'money': 30}
            elif(rand == 2):
                values = {'money': 50}

        elif fantasy_type == 'magnetism':
            card_cost = 100

        elif fantasy_type == 'goToStart':
            card_cost = 90

        return FantasyEvent(
                fantasy_type = fantasy_type,
                values = values,
                card_cost = card_cost
                )

#@database_sync_to_async
def apply_fantasy_event(game: Game, user: CustomUser , fantasy_event: FantasyEvent) -> FantasyResult:
    """
    Applies the effects of a given FantasyEvent to the game state and updates player statistics.

    This function handles the logic for all variations of fantasy events as defined in the rules:
    - Monetary transactions (win_plain_money, win_ratio_money, lose_plain_money, lose_ratio_money, 
      share_money_all, everybody_sends_you_money, double_or_nothing, get_parking_money).
    - Positional events (shuffle_positions, move_anywhere_random, move_opponent_anywhere_random, 
      go_to_start, magnetism - pulling everyone to you).
    - Jail events (go_to_jail, send_to_jail, everybody_to_jail).
    - Property interactions (break_opponent_house, break_own_house, free_house, 
      reviveProperty - unmortgages for free, earthquake - removes a house from all streets).

    Args:
        game (Game): The current game instance.
        user (CustomUser): The player who triggered the event.
        fantasy_event (FantasyEvent): The event details (type and specific values).

    Returns:
        FantasyResult: A result object containing the event type and any updated square/player data 
                       needed by the frontend.

    Raises:
        Exception: If an event requiring values has None, or if internal targeting logic fails.
    """
    stats = PlayerGameStatistic.objects.get(user=user,game=game)
    stats.num_fantasy_events += 1
    stats.save()

    if fantasy_event.fantasy_type == 'winPlainMoney':
        if fantasy_event.values is None:
            raise Exception('FantasyEvent values is None')
        
        money_to_add = fantasy_event.values['money']
        game.money[str(user.pk)] += money_to_add
        game.save()
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.won_money += money_to_add
        stats.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # vacio porque frontend ya sabe todo
        )
    
    elif fantasy_event.fantasy_type == 'winRatioMoney':
        if fantasy_event.values is None:
            raise Exception('FantasyEvent values is None')

        ratio_to_add = fantasy_event.values['money']
        previous_money = game.money[str(user.pk)]
        game.money[str(user.pk)] = int(game.money[str(user.pk)] * (1 + ratio_to_add/100))
        game.save()
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.won_money += game.money[str(user.pk)] - previous_money
        stats.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # vacio porque frontend ya sabe todo
        )
    
    elif fantasy_event.fantasy_type == 'losePlainMoney':
        if fantasy_event.values is None:
            raise Exception('FantasyEvent values is None')
        
        money_to_sub = fantasy_event.values['money']
        game.money[str(user.pk)] -= money_to_sub
        game.save()
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.lost_money += money_to_sub
        stats.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # vacio porque frontend ya sabe todo
        )
    
    elif fantasy_event.fantasy_type == 'loseRatioMoney':
        if fantasy_event.values is None:
            raise Exception('FantasyEvent values is None')

        ratio_to_sub = fantasy_event.values['money']
        previous_money = game.money[str(user.pk)]
        game.money[str(user.pk)] = int(game.money[str(user.pk)] * (1 - ratio_to_sub/100))
        game.save()
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.lost_money += previous_money - game.money[str(user.pk)]
        stats.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # vacio porque frontend ya sabe todo
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
            fantasy_type = fantasy_event.fantasy_type,
            values = None # empty, no house broken
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
            fantasy_type = fantasy_event.fantasy_type,
            values = {'square': result_property.square.custom_id}
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
            fantasy_type = fantasy_event.fantasy_type,
            values = None # empty, no house broken
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
            raise Exception("esto no deberia pasar")
        
        result_property = _demolish_square(game=game, user=target_prop.owner, demolition_square=target_prop.square,
                         number_demolished=1, free_demolish=True)

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = {'square': result_property.square.custom_id}
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
            fantasy_type = fantasy_event.fantasy_type,
            values = None # que mire otra vez el estado y ya
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
            fantasy_type = fantasy_event.fantasy_type,
            values = None # que mire otra vez el estado y ya
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
            fantasy_type = fantasy_event.fantasy_type,
            values = {'target_player_pk':target_player.pk}
            )
    
    elif fantasy_event.fantasy_type == 'shareMoneyAll':
        if fantasy_event.values is None:
            raise Exception('FantasyEvent values is None')
        
        money_to_share = fantasy_event.values['money']

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
            fantasy_type = fantasy_event.fantasy_type,
            values = None # que mire otra vez el estado y ya
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
                fantasy_type=fantasy_event.fantasy_type,
                values=None # No hay hueco para construir más casas
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
            fantasy_type=fantasy_event.fantasy_type,
            values={'square': result_property.square.custom_id}
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
            fantasy_type=fantasy_event.fantasy_type,
            values=None
        )
    
    elif fantasy_event.fantasy_type == 'sendToJail':
        target_user = random.choice(game.players.exclude(pk=user.pk))
        jail_id = _get_jail_square().custom_id
        game.positions[str(target_user.pk)] = jail_id
        game.jail_remaining_turns[str(target_user.pk)] = 3
        game.save()

        stats = PlayerGameStatistic.objects.get(user=target_user,game=game)
        stats.times_in_jail += 1
        stats.save()

        return FantasyResult(
            fantasy_type=fantasy_event.fantasy_type,
            values={'target_user':target_user.pk}
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
            fantasy_type=fantasy_event.fantasy_type,
            values=None
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
            fantasy_type=fantasy_event.fantasy_type,
            values={'doubled': r}
        )
        
    
    elif fantasy_event.fantasy_type == 'getParkingMoney':
        game.money[str(user.pk)] += game.parking_money
        stats = PlayerGameStatistic.objects.get(user=user,game=game)
        stats.won_money += game.parking_money
        stats.save()
        game.parking_money = 0
        game.save()

        return FantasyResult(
            fantasy_type=fantasy_event.fantasy_type,
            values=None
        )
    
    elif fantasy_event.fantasy_type == 'reviveProperty':
        properties = PropertyRelationship.objects.filter(
            game=game, owner=user, mortgage=True
        )

        if not properties.exists():
            return FantasyResult(
            fantasy_type=fantasy_event.fantasy_type,
            values=None
            )

        target = random.choice(properties)

        result = _unset_mortgage(user=user,game=game,target_square=target.square,free_unset_mortgage=True)

        return FantasyResult(
            fantasy_type=fantasy_event.fantasy_type,
            values={'square': result.square.custom_id}
            )

    
    elif fantasy_event.fantasy_type == 'earthquake':
        properties = PropertyRelationship.objects.filter(
            game=game,
            houses__gte=1,
        ).select_related('square')

        if not properties.exists():
            return FantasyResult(
            fantasy_type=fantasy_event.fantasy_type,
            values=None
        )

        demolished_houses = []

        for prop in properties:
            result_property = _demolish_square(game=game, user=prop.owner, demolition_square=prop.square,
                         number_demolished=1, free_demolish=True)
            demolished_houses.append(result_property.square.custom_id)

        return FantasyResult(
            fantasy_type=fantasy_event.fantasy_type,
            values={'squares': demolished_houses}
        )
    
    elif fantasy_event.fantasy_type == 'everybodySendsYouMoney':
        if fantasy_event.values is None:
            raise Exception('FantasyEvent values is None')
        
        money_to_share = fantasy_event.values['money']

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
            fantasy_type = fantasy_event.fantasy_type,
            values = None # que mire otra vez el estado el frontend
            )
    
    elif fantasy_event.fantasy_type == 'magnetism':
        id_jail = _get_jail_square().custom_id
        target_id = game.positions[str(user.pk)]
        for player in game.players.all(): #no caso especial para el que lanza, se moverá al mismo sitio
            if(game.positions[str(player.pk)] != id_jail):
                game.positions[str(player.pk)] = target_id

        game.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # que mire otra vez el estado y ya
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
            fantasy_type = fantasy_event.fantasy_type,
            values = None # que mire otra vez el estado y ya
            )
    else: # caso imposible presuntamente
        return FantasyResult(
            fantasy_type = None,
            values = None
            )

