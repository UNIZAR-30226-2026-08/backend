from asyncio import Server
import random 
import json
from django.db import transaction

from backend.magnate.serializers import *
from .models import *
from channels.db import database_sync_to_async

try:
    with open('../boards/board1.json') as f:
        BOARD_JSON = json.load(f)
except FileNotFoundError:
    BOARD_JSON = {}

# El Gemini me ha hecho esto pidiendole que hiciese una función de cargar el json
def load_board_map(board_json):
    board_map = {}
    
    lists = ["property_squares", "bridge_squares", "tram_squares", 
             "server_squares", "fantasy_squares"]
    for key in lists:
        if key in board_json:
            for item in board_json[key]:
                item['type'] = key
                board_map[item['id']] = item

    singles = ["exit_square", "go_to_jail_square", "jail_square", "parking_square"]
    for key in singles:
        if key in board_json:
            item = board_json[key]
            item['type'] = key
            board_map[item['id']] = item
            
    return board_map

BOARD_MAP = load_board_map(BOARD_JSON)

# TODO: sum money if the player passes through exit square or parking
def move_player_logic(current_id, total_steps, board_map):
    curr = current_id
    path_log = [curr]
    passed_go = False

    for i in range(total_steps):
        if curr not in board_map:
            raise ValueError(f"Casilla {curr} no encontrada")

        square = board_map[curr]
        next_id = None
        
        if square.get('type') == 'bridge_squares':
            # depending on steps 
            if total_steps % 2 == 0:
                next_id = square['out_successor']
            else:
                next_id = square['in_successor']
        else:
            next_id = square.get('id_successor')

        if next_id == "000":
            passed_go = True
        
        curr = next_id
        path_log.append(curr)

    if curr == "020":
        curr = "140"

    return {"final_id": curr, "path": path_log, "passed_go": passed_go}


async def get_possible_destinations_ids(user, game, step_options, board_map):
    destination_ids = []
    try:
        player_state = await game.game_players.aget(user=user)
        current_pos = str(player_state.position.custom_id)
    except:
        current_pos = "000"
        
    for steps in step_options:
        result = move_player_logic(current_pos, steps, board_map)
        destination_ids.append(result["final_id"])

    return sorted(list(set(destination_ids)))


def land_in_jail(game, total, user, board):
    info = move_player_logic(game.current_square[user], total, board)
    return info["final_id"] == "020", info["path"]


class GameManager:
    
    @classmethod
    async def process_action(cls, user, game, action, data):
        if game.phase == "roll_the_dices":
            return await cls._roll_dices_logic(user, game, streak=game.streak)
        elif game.phase == "choose_square":
            return await cls._square_chosen_logic(game.possible_destinations, user, game, action)
        elif game.phase == "management":
            return await cls._management_logic(user, game, action, data)


        

 ############################################

    @classmethod
    @database_sync_to_async
    async def update_game_state_dices(cls, action, game, user):
        """
        Persiste la ActionThrowDices en BD usando su serializer y actualiza
        el estado de la partida (destinos posibles almacenados en el JSON del juego).
        La instancia ya fue creada por action_from_json, así que sólo la actualizamos.
        """
        serializer = ActionThrowDicesSerializer(
            action,
            data={
                'game': game.pk,
                'player': user.pk,
                'dice1': action.dice1,
                'dice2': action.dice2,
                'dice_bus': action.dice_bus,
                'destinations': action.destinations,
                'triple': action.triple,
                'path': action.path,
            },
            partial=True
        )
        if serializer.is_valid():
            serializer.save()

        game.current_square[user] = action.destinations if action.path != [] else game.current_square[user]
        game.possible_destinations = action.destinations if len(action.destinations) > 1 else []
        game.streak = action.streak

        if len(action.destinations) >1:
            game.phase = "choose_square"
        elif action.destinations == ["104"]:
            game.phase = "liquidation"
        else:
            game.phase = "management" #pay bills or buy if possible
        game.save()

    @classmethod
    @database_sync_to_async
    async def update_game_state_square_chosen(cls, action, game, user):
        """
        Persiste la ActionMoveTo en BD usando su serializer y actualiza
        la posición del jugador en la partida.
        """
        serializer = ActionMoveToSerializer(
            action,
            data={
                'game': game.pk,
                'player': user.pk,
                'square': action.square.custom_id,
            },
            partial=True
        )
        if serializer.is_valid():
            serializer.save()

        game.current_square[user] = action.square.custom_id
        game.possible_destinations = []
        if game.streak > 0:
            game.phase = "roll_the_dices"
        else:
            game.phase = "management" #pay bills or buy if possible
        game.save()

    @classmethod
    @database_sync_to_async
    async def update_game_state_management(cls, action, game, user):


 ############################################

    # ------------------- ROLL THE DICES IN MOVEMENT PHASE ------------------------------#
    @staticmethod
    async def _roll_dices_logic(user, game, streak):
        #TODO: add the logic if the user is in jail. 
        d1 = random.randint(1,6)
        d2 = random.randint(1,6)
        d3 = random.randint(1,6) # 4-6 are the bus faces

        bus_is_numeric = d3 <= 3
        dice_results = [d1, d2, d3]

        action = ActionThrowDices(game=game, player=user)
        
        action.dice1 = d1
        action.dice2 = d2
        action.dice_bus = d3

        doubles = d1 == d2 or (bus_is_numeric and (d1 == d3 or d2 == d3))

        #first -> if in jail and normal
        if game.positions[user] == "104" and not doubles:
            action.triple = False
            action.path = []
            action.destinations = ["104"]
            action.streak = 0
            await GameManager.update_game_state_dices(action, game, user)
        
        # Triples
        if bus_is_numeric and (d1 == d2 == d3):
            action.triple = True
            action.path = []
            action.destinations = []
            action.streak = 0

            await GameManager.update_game_state_dices(action, game, user)

            return action

        
        # Dobles
        elif doubles:
            action.triple = False
            # doubles and jail -> liquidation
            if streak >= 2:
                action.path = []
                action.destinations = ["104"]
                action.streak = 3
                await GameManager.update_game_state_dices(action, game, user)
                return action
            
            else:
                action.streak= streak + 1
                if bus_is_numeric:
                    
                    in_jail, action.path = land_in_jail(game, d1+d2, user, BOARD_MAP)
                    action.destinations = action.path[-1] if not in_jail else ["104"]
                    action.streak = 0 if in_jail else action.streak
                    await GameManager.update_game_state_dices(action, game, user)
                    return action
                else:
                    options = await get_possible_destinations_ids(user, game, [d1, d2, d1+d2], BOARD_MAP)
                    action.path = []
                    action.destinations = options
                    action.streak = 0
                    await GameManager.update_game_state_dices(action, game, user)
                    return action

        # Normal
        else:
            action.triple = False
            action.streak = 0
            if bus_is_numeric:
                
                in_jail, action.path = land_in_jail(game, d1+d2+d3, user, BOARD_MAP)
                action.destinations = action.path[-1] if not in_jail else ["104"]
                await GameManager.update_game_state_dices(action, game, user)
                
                return action
            else:
                options = await get_possible_destinations_ids(user, game, [d1, d2, d1+d2], BOARD_MAP)
                action.path = []
                action.destinations = options
                await GameManager.update_game_state_dices(action, game, user)
                return action

    # ------------------- CHOOSE SQUARE LOGIC IN MOVEMENT PHASE ------------------------------#
    @staticmethod
    async def _square_chosen_logic(possible_chosen_squares, square,game, user):
        # Logic of movement when the user direcctly chooses a square due to a bus or triples

        action = ActionMoveTo(game = game, player = user)
        
        if square not in possible_chosen_squares:
            return None
        
        
        action .square = square

        await GameManager.update_game_state_square_chosen(action, game, user)
        return action
    
    @staticmethod
    def get_rent_price(square: PropertySquare, property):
        houses = property.houses
        if houses == -1:
            return square.rent[0]
        elif houses == 0:
            return square.rent[1]
        elif houses == 1:
            return square.rent[2]
        elif houses == 2:
            return square.rent[3]
        elif houses == 3:
            return square.rent[4]
        elif houses == 4:
            return square.rent[5]
        
    @staticmethod
    @database_sync_to_async
    async def _management_logic(user, game, action, data):
        # Logic of management phase, where the user can buy properties, pay bills etc

        #first -> what is the action? -> chekc internally its current square and data associated. Then check user info
        # to update the game state accordingly and return next state
        current_square = get_square(game.current_square[user])

        if isinstance(current_square, ExitSquare):
            #done in move logic
            pass

        elif isinstance(current_square, PropertySquare):
            property = PropertyRelationship.objects.filter(game=game, square=current_square)
            if property.exists(): #  pay rent -> chekc houses
                to_pay = GameManager.get_rent_price(current_square, property.first())
                property_owner = property.first().owner
                game.money[user] -= to_pay
                game.money[property_owner] += to_pay
                game.phase = "business"
                game.save()
            else: #buy option -> look at data to see if the user wants to buy and if he can afford it
                if isinstance(action, ActionBuySquare):
                    game.money[user] -= current_square.price
                    game.phase = "business"
                    new_property = PropertyRelationship(game=game, square=current_square, owner=user)
                    user_properties = PropertyRelationship.objects.filter(game=game, owner=user)
                    user_same_group_properties = user_properties.filter(square__group=current_square.group)

                    if user_same_group_properties.count() == current_square.group_squares - 1:
                        new_property.houses = 0
                        user_same_group_properties.update(houses=0)
                    else: 
                        new_property.houses = -1
                    new_property.save()

                    game.save()
                elif isinstance(action, ActionDropPurchase):
                    game.phase = "auction"
                    pass

        elif isinstance(current_square, FantasySquare):
            pass # -> other phase
        elif isinstance(current_square, BridgeSquare):
            pass
        elif isinstance(current_square, TramSquare):
            if isinstance(action, ActionTakeTram):
                square = action.square
                #check if user can afford it and if that square is a possible destination
                tram_squares = TramSquare.objects.filter()
                tram_squares_ids = [s.custom_id for s in tram_squares]

                if square.custom_id in tram_squares_ids: # confirms its valid
                    game.money[user] -= square.buy_price
                    game.current_square[user] = square.custom_id
                    game.phase = "management"
                    game.save()

            elif isinstance(action, ActionDoNotTakeTram):
                game.phase = "management"
                game.save()


        elif isinstance(current_square, ParkingSquare):
            pass
        
        elif isinstance(current_square, ServerSquare):
            property = PropertyRelationship.objects.filter(game=game, square=current_square)
            if property.exists(): #  pay rent
                #Check whether the user owns the other ServerSquare 
                property_owner = property.first().owner
                squares = PropertyRelationship.objects.filter(game=game, square__type='server_squares', owner=property_owner)
                if squares.count() == 2:
                    to_pay = current_square.rent [1]
                else:
                    to_pay = current_square.rent [0]

                game.money[user] -= to_pay
                game.money[property_owner] += to_pay
                game.phase = "business"
                game.save()

            else: #buy option -> look at data to see if the user wants to buy and if he can afford it
                if isinstance(action, ActionBuySquare):
                    game.money[user] -= current_square.price
                    game.phase = "business"
                    new_property = PropertyRelationship(game=game, square=current_square, owner=user)
                    new_property.save()
                    game.save()
                elif isinstance(action, ActionDropPurchase):
                    game.phase = "auction"
                    # TODO: logic of auction
                    pass
            
            return {"next_phase": game.phase}
                    
            
                
        elif isinstance(current_square, JailSquare):
            pass
        
        
        