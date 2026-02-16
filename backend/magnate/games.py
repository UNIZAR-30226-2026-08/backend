import random 
import json
from django.db import transaction
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
        if action == 'roll_dices':
            # TODO: Reread logic to fix this
            streak = data.get("doubles_streak", 0)
            result = await cls._roll_dices_logic(user, game, streak)
            await cls.update_game_state_dices(result, game, user)
            return result
            
        elif action == 'choose_next_square':
            possible_squares = data.get("possible_chosen_squares", [])
            result = cls._square_chosen_logic(user, game, possible_squares, data)
            if result:
                await cls.update_game_state_square_chosen(result, game, user)
            return result
        
        #TODO: change what returns and check real phases

    @classmethod
    async def _management_phase(cls, user, game, action, data):
        pass

    @classmethod
    async def _business_phase(cls, user, game, action, data):
        # gestion -> hay que cambiar todo a management
        pass

    @classmethod
    async def _liquidation_phase(cls, user, game, action, data):
        pass
            
 ############################################

    @classmethod
    @database_sync_to_async
    def update_game_state_dices(cls, result, game, user):
        pass 

    @classmethod
    @database_sync_to_async
    def update_game_state_square_chosen(cls, result, game, user):
        pass

 ############################################

    # ------------------- ROLL THE DICES IN MOVEMENT PHASE ------------------------------#
    @staticmethod
    async def _roll_dices_logic(user, game, streak):
        d1 = random.randint(1,6)
        d2 = random.randint(1,6)
        d3 = random.randint(1,6) # 4-6 are the bus faces

        bus_is_numeric = d3 <= 3
        d3_val = d3 if bus_is_numeric else "BUS"
        dice_results = [d1, d2, d3_val]

        # Triples
        if bus_is_numeric and (d1 == d2 == d3_val):
            return {
                "type": "CHOOSE_MOVE",
                "dice": dice_results,
                "next_state": "PHASE_MOVEMENT", 
                "posible_moves": "all_board_squares", # TODO: Pasar a vector
                "new_streak": 0
            }

        # Dobles
        elif d1 == d2:
            if streak >= 2:
                return {
                    "type": "GO_TO_JAIL_STREAK",
                    "dice": dice_results,
                    "next_state": "PHASE_LIQUIDATION",
                    "posible_moves": "104",
                    "new_streak": 0
                }
            else:
                new_streak = streak + 1
                if bus_is_numeric:
                    total = d1 + d2 + d3_val
                    in_jail, path = land_in_jail(game, total, user, BOARD_MAP)
                    return {
                        "type": "NORMAL_MOVE",
                        "dice": dice_results,
                        "next_state": "PHASE_LIQUIDATION" if in_jail else "PHASE_MOVEMENT",
                        "posible_moves": "104" if in_jail else path[-1],
                        "new_streak": 0 if in_jail else new_streak,
                        "path": path
                    }
                else:
                    options = await get_possible_destinations_ids(user, game, [d1, d2, d1+d2], BOARD_MAP)
                    return {
                        "type": "CHOOSE_MOVE",
                        "dice": dice_results,
                        "next_state": "PHASE_MOVEMENT",
                        "posible_moves": options,
                        "new_streak": new_streak,
                    }

        # Normal
        else:
            if bus_is_numeric:
                total = d1 + d2 + d3_val
                in_jail, path = land_in_jail(game, total, user, BOARD_MAP)
                return {
                    "type": "NORMAL_MOVE",
                    "dice": dice_results,
                    "next_state": "PHASE_LIQUIDATION" if in_jail else "PHASE_BUSINESS",
                    "posible_moves": "104" if in_jail else path[-1],
                    "new_streak": 0,
                    "path": path
                }
            else:
                options = await get_possible_destinations_ids(user, game, [d1, d2, d1+d2], BOARD_MAP)
                return {
                    "type": "CHOOSE_MOVE",
                    "dice": dice_results,
                    "next_state": "PHASE_MOVEMENT",
                    "posible_moves": options,
                    "new_streak": 0,
                }

    # ------------------- CHOOSE SQUARE LOGIC IN MOVEMENT PHASE ------------------------------#
    @staticmethod
    def _square_chosen_logic(user, game, possible_chosen_squares, data):
        # Logic of movement when the user direcctly chooses a square due to a bus or triples
        square = data.get('square')
        
        if square not in possible_chosen_squares:
            return None
        
        in_jail = square == "020"
        
        return {
            "type": "GO_TO", 
            "next_state": "PHASE_LIQUIDATION",
            "posible_moves": "104" if in_jail else square,
            "path": ["020", "104"] if in_jail else [square]
        }