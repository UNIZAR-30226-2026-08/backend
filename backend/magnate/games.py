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
        if game.phase == "PHASE_MOVEMENT":
            return await cls._movement_phase(user, game, action, data)
        elif game.phase == "PHASE_BUSINESS":
            return await cls._business_phase(user, game, action, data)
        elif game.phase == "PHASE_MANAGEMENT":
            return await cls._management_phase(user, game, action, data)
        elif game.phase == "PHASE_LIQUIDATION":
            return await cls._liquidation_phase(user, game, action, data)

    @classmethod
    async def _movement_phase(cls, user, game, action, data):
        if isinstance(action, ActionThrowDices):
            # TODO: Reread logic to fix this
            streak = data.get("doubles_streak", 0)
            result = await cls._roll_dices_logic(user, game, streak)
            await cls.update_game_state_dices(result, game, user)
            return result
            
        elif isinstance(action, ActionMoveTo):
            # TODO: use user and game to interact with DB
            streak = data.get("doubles_streak", 0)
            possible_squares = data.get("possible_chosen_squares", []) #method to DB to check the possible squares stored in previous move
            chosen_square_id = str(action.square.custom_id)
            
            result = cls._square_chosen_logic( possible_squares, chosen_square_id, streak, game, user)
            if result:
                await cls.update_game_state_square_chosen(result, game, user)
            return result
        
        #TODO: change what returns and check real phases

###### BUSINESS PHASE METHODS ####################

    @classmethod
    async def _buy_square(cls, user, game, data):
        #Check game state so that user can buy the square and change DB
        # Returns success and the next phase -> depends on streak
        pass

    @classmethod
    async def _pay_rent(cls, user, game, data):
        #Check game state so that user can pay the rent
        pass 

    @classmethod
    async def _initiate_auction(cls, user, game, data):
        #Check game state so that user can initiate the auction
        # and return success. Change turns so that everyone can bid
        pass

    @classmethod
    async def _bid(cls, user, game, data):
        #Check game state so that user can bid
        #return success
        pass

    @classmethod
    async def _end_auction(cls, user, game, data):
        #Ends the acution and returns who wins
        # returning to "turn-game"
        pass





    @classmethod
    async def _business_phase(cls, user, game, action, data):
        # business -> compra alquilar, poner a subasta etc
        if action == "buy_square":
            result = await cls._buy_square(user, game, data)
            return result
        elif action == "pay_rent":
            result = await cls._pay_rent(user, game, data)
            return result
        elif action == "initiate_auction":
            result = await cls._initiate_auction(user, game, data)
            return result
        elif action == "bid":
            result = await cls._bid(user, game, data)
            return result
        elif action == "end_auction":
            result = await cls._end_auction(user, game, data)
            return result
        
        
        
        
    @classmethod
    async def _management_phase(cls, user, game, action, data):
        pass

    

    @classmethod
    async def _liquidation_phase(cls, user, game, action, data):
        pass
            
 ############################################

    @classmethod
    @database_sync_to_async
    def update_game_state_dices(cls, action, game, user):
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

    @classmethod
    @database_sync_to_async
    def update_game_state_square_chosen(cls, action, game, user):
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
        # Triples
        if bus_is_numeric and (d1 == d2 == d3):
            action.triple = True
            action.path = []
            action.destinations = []
            action.streak = 0

            return action

        
        # Dobles
        elif d1 == d2:
            action.triple = False
            if streak >= 2:
                action.path = []
                action.destinations = ["104"]
                action.streak = 3

                return action
            
            else:
                action.streak= streak + 1
                if bus_is_numeric:
                    
                    in_jail, action.path = land_in_jail(game, total, user, BOARD_MAP)
                    action.destinations = action.path[-1] if not in_jail else ["104"]
                    action.streak = 0 if in_jail else action.streak

                    return action
                else:
                    options = await get_possible_destinations_ids(user, game, [d1, d2, d1+d2], BOARD_MAP)
                    action.path = []
                    action.destinations = options
                    action.streak = 0

                    return action

        # Normal
        else:
            action.triple = False
            action.streak = 0
            if bus_is_numeric:
                
                in_jail, action.path = land_in_jail(game, d1+d2+d3, user, BOARD_MAP)
                action.destinations = action.path[-1] if not in_jail else ["104"]
                
                return action
            else:
                options = await get_possible_destinations_ids(user, game, [d1, d2, d1+d2], BOARD_MAP)
                action.path = []
                action.destinations = options

                return action

    # ------------------- CHOOSE SQUARE LOGIC IN MOVEMENT PHASE ------------------------------#
    @staticmethod
    def _square_chosen_logic(possible_chosen_squares, square, streak, game, user):
        # Logic of movement when the user direcctly chooses a square due to a bus or triples

        action = ActionMoveTo(game = game, player = user)
        
        if square not in possible_chosen_squares:
            return None
        
        
        action .square = square

        return action