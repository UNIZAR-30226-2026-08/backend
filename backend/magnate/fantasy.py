from magnate.models import *
from channels.db import database_sync_to_async
from collections import defaultdict
import random

class FantasyEventFactory:
    @staticmethod
    def generate() -> FantasyEvent:
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

        elif fantasy_type == 'dontPayNextTurnRent':
            card_cost = 35

        elif fantasy_type == 'allYourRentsX2OneTurn':
            card_cost = 100

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

@database_sync_to_async
def apply_fantasy_event(game: Game, user: CustomUser , fantasy_event: FantasyEvent) -> FantasyResult:

    if fantasy_event.fantasy_type == 'winPlainMoney':
        if fantasy_event.values is None:
            raise Exception('FantasyEvent values is None')
        
        money_to_add = fantasy_event.values['money']
        game.money[user.pk] += money_to_add
        game.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # vacio porque frontend ya sabe todo
        )
    
    elif fantasy_event.fantasy_type == 'winRatioMoney':
        if fantasy_event.values is None:
            raise Exception('FantasyEvent values is None')

        ratio_to_add = fantasy_event.values['money']
        game.money[user.pk] = int(game.money[user.pk] * (1 + ratio_to_add/100))
        game.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # vacio porque frontend ya sabe todo
        )
    
    elif fantasy_event.fantasy_type == 'losePlainMoney':
        if fantasy_event.values is None:
            raise Exception('FantasyEvent values is None')
        
        money_to_sub = fantasy_event.values['money']
        game.money[user.pk] -= money_to_sub
        game.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # vacio porque frontend ya sabe todo
        )
    
    elif fantasy_event.fantasy_type == 'loseRatioMoney':
        if fantasy_event.values is None:
            raise Exception('FantasyEvent values is None')

        ratio_to_sub = fantasy_event.values['money']
        game.money[user.pk] = int(game.money[user.pk] * (1 - ratio_to_sub/100))
        game.save()

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
        
        target_prop.houses -= 1 #TODO, check grupo completo
        target_prop.save(update_fields=['houses'])

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = {'square': target_prop.square.custom_id}
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
        
        target_prop.houses -= 1
        target_prop.save(update_fields=['houses'])

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = {'square': target_prop.square.custom_id}
            )

    elif fantasy_event.fantasy_type == 'shufflePositions': #TODO: tener en cuenta carcel
        #move everybody to random square
        ids = list(BaseSquare.objects.values_list('custom_id', flat=True))
        for player in game.players.all():
            rand_square_id = random.choice([n for n in ids if n != game.positions[player.pk]])
            game.positions[player.pk] = rand_square_id #TODO: current_square???

        game.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # que mire otra vez el estado y ya
            )
    
    elif fantasy_event.fantasy_type == 'moveAnywhereRandom':
        ids = list(BaseSquare.objects.values_list('custom_id', flat=True))
        rand_square_id = random.choice([n for n in ids if n != game.positions[user.pk]])
        game.current_square[user.pk] = rand_square_id
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
        ids = list(BaseSquare.objects.values_list('custom_id', flat=True))
        rand_square_id = random.choice([n for n in ids if n != game.positions[target_player.pk]])
        game.current_square[target_player.pk] = rand_square_id
        game.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # que mire otra vez el estado y ya
            )
    
    elif fantasy_event.fantasy_type == 'ShareMoneyAll':
        if fantasy_event.values is None:
            raise Exception('FantasyEvent values is None')
        
        money_to_share = fantasy_event.values['money']

        opponents = game.players.exclude(pk=user.pk)
        opponents_list = list(opponents)
        opponents_count = len(opponents_list)

        for player in opponents_list:
            game.money[player.pk] += money_to_share

        game.money[user.pk] -= money_to_share*opponents_count

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
            key = prop.square.color_group
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
        
        target_prop.houses += 1
        target_prop.save(update_fields=['houses'])

        return FantasyResult(
            fantasy_type=fantasy_event.fantasy_type,
            values={'square': target_prop.square.custom_id}
        )
    
    elif fantasy_event.fantasy_type == 'goToJail':
        raise NotImplementedError('fantasy type not implemented')
    
    elif fantasy_event.fantasy_type == 'sendToJail':
        raise NotImplementedError('fantasy type not implemented')
    
    elif fantasy_event.fantasy_type == 'everybodyToJail':
        raise NotImplementedError('fantasy type not implemented')
    
    elif fantasy_event.fantasy_type == 'doubleOrNothing':
        r = random.choice([True,False])
        if r:
            game.money[user.pk] *= 2
        else:
            game.money[user.pk] = 0
        game.save()

        return FantasyResult(
            fantasy_type=fantasy_event.fantasy_type,
            values={'doubled': r}
        )
        
    
    elif fantasy_event.fantasy_type == 'getParkingMoney':
        game.money[user.pk] += game.parking_money
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
            values={'squares': None}
            )

        target = random.choice(properties)
        target.mortgage = False
        target.save()

        return FantasyResult(
            fantasy_type=fantasy_event.fantasy_type,
            values={'squares': target.square.custom_id}
            )

    
    elif fantasy_event.fantasy_type == 'earthquake':
        properties = PropertyRelationship.objects.filter(
            game=game,
            houses__gte=1,
        ).select_related('square')

        if not properties.exists():
            return FantasyResult(
            fantasy_type=fantasy_event.fantasy_type,
            values={'squares': None}
        )

        demolished_houses = []

        for prop in properties:
            prop.houses -= 1 #python no tiene --, tocate los *******
            prop.save(update_fields=['houses'])
            demolished_houses.append(prop.square.custom_id)

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
            game.money[player.pk] -= money_to_share

        game.money[user.pk] += money_to_share*opponents_count

        game.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # que mire otra vez el estado el frontend
            )
    
    elif fantasy_event.fantasy_type == 'magnetism': #TODO: tener en cuenta carcel
        target_id = game.positions[user.pk]
        for player in game.players: #no caso especial para el que lanza, se moverá al mismo sitio
            game.current_square[player.pk] = target_id #TODO: positions???

        game.save()

        return FantasyResult(
            fantasy_type = fantasy_event.fantasy_type,
            values = None # que mire otra vez el estado y ya
            )

    elif fantasy_event.fantasy_type == 'goToStart':
        start_square = ExitSquare.objects.first()
        if start_square is None:
            raise Exception('No encuentra casilla de salida')
        
        game.current_square[user.pk] = start_square.custom_id
        game.money[user.pk] += start_square.init_money

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

