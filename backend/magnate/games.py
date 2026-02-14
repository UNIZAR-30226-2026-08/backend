import random 
import json
from .models import Game
from .consumers import GameConsumer
from django.db import transaction



import json

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
            #depending on steps 
            remaining_steps = total_steps - i
            
            if remaining_steps % 2 == 0:
                next_id = square['out_successor']
            else:
                next_id = square['in_successor']

        else:
            next_id = square.get('id_successor')

        if next_id == "000":
            passed_go = True
        
        # Avanzar
        curr = next_id
        path_log.append(curr)

    return {
        "final_id": curr,
        "path": path_log,
        "passed_go": passed_go
    }

def get_possible_destinations_ids(user, game, step_options, board_map):

    destination_ids = []
    
    try:
        player_state = game.game_players.get(user=user)
        current_pos = str(player_state.position.custom_id)
    except:
        current_pos = "000"
    for steps in step_options:
        result = move_player_logic(current_pos, steps, board_map)
        final_id = result['final_id']
       
    destination_ids.append(final_id)

    return sorted(list(set(destination_ids)))


def roll_dices(action, user, game, streak):
    # Check the 
    try:
        with open('../boards/board1.json') as f:
            BOARD = json.load(f)
    except FileNotFoundError:
        print("Error: The file 'data.json' was not found.")

    board = load_board_map(BOARD)

    d1 = random.randint(1,6)
    d2 = random.randint(1,6)
    d3 = random.randint(1,6) #4-6 are the bus faces

    if d3 <= 3 :
        d3_val = d3
        bus_is_numeric = True
    else:
        d3_val = "BUS"
        bus_is_numeric = False

    dice_results = [d1, d2, d3_val]

    #  triples
    if bus_is_numeric and (d1 == d2 == d3_val):
        # Return next satet, all board squares, the message of triple move and the results of the dices
        return {
            "type": "CHOOSE_MOVE",
            "dice": dice_results,
            "next_state": "PHASE_MOVEMENT", 
            "posible_moves": "all_board_squares", 
            "new_streak": 0
        
        }

    # doubles
    elif d1 == d2:
        # jail
        if streak >= 2:
            return {
                "type": "GO_TO_JAIL_STREAK",
                "dice": dice_results,
                "next_state": "PHASE_LIQUIDATION",
                "posible_moves": "104",
                "new_streak": 0
            }
        
        # valid double
        else:
            new_streak = streak + 1
            
            # bus?
            if bus_is_numeric:
                total = d1 + d2 + d3_val
                #Check if you go to jail
                in_jail, path = land_in_jail(game, total, user, board)
                if in_jail:
                    return {
                        "type": "NORMAL_MOVE",
                        "dice": dice_results,
                        "next_state" : "PHASE_LIQUIDATION",
                        "posible_moves": "104",
                        "new_streak": 0,
                        "path": path
                    }
                else:
                    return {
                         "type": "NORMAL_MOVE",
                        "dice": dice_results,
                        "next_state" : "PHASE_MOVEMENT",
                        "posible_moves": path[-1],
                        "new_streak": new_streak,
                        "path": path
                    }
            else:
                # bus -> choose
                options = get_possible_destinations_ids(user, game, [d1, d2, d1+d2], board)
                return {
                    "type": "CHOOSE_MOVE",
                    "dice": dice_results,
                    "next_state" : "PHASE_MOVEMENT",
                    "posible_moves": options,
                    "new_streak": new_streak,
                }

    # normal
    else:
        if bus_is_numeric:
            total = d1 + d2 + d3_val
            in_jail, path = land_in_jail(game, total, user, board)
            if in_jail:
                return {
                        "type": "NORMAL_MOVE",
                        "dice": dice_results,
                        "next_state" : "PHASE_LIQUIDATION",
                        "posible_moves": "104",
                        "new_streak": 0,
                        "path": path
                    }
            else:
                return {
                    "type": "NORMAL_MOVE",
                    "dice": dice_results,
                    "next_state" : "PHASE_BUSINESS",
                    "posible_moves": path[-1],
                    "new_streak": 0,
                    "path": path
                }
        else:
            options = get_possible_destinations_ids(user, game, [d1, d2, d1+d2], board)
            return {
                "type": "CHOOSE_MOVE",
                "dice": dice_results,
                "next_state" : "PHASE_MOVEMENT",
                "posible_moves": options,
                "new_streak": 0,
            }
        
@transaction.atomic
def land_in_jail(game, total, user, board):
    info = move_player_logic(game.current_square[user], total,board)
    return  info["final_id"] == "020", info["path"]


