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

def get_square(custom_id: int):
    square = BaseSquare.objects.filter(custom_id=custom_id)
    if square.count() > 1:
        raise ValueError("Too many squares found!")
    return square.first()

def move_player_logic(curr, total_steps):
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
            curr = square.in_successor
        else:
            curr = square.in_successor
        
        path_log.append(curr.custom_id)

    if isinstance(curr, GoToJailSquare):
        curr = JailSquare.objects.first()

    return {"final_id": curr.custom_id, 
            "path": path_log, "passed_go": passed_go}

async def get_possible_destinations_ids(user, game, step_options):
    destination_ids = []
    current_pos = game.positions[user]
        
    for steps in step_options:
        result = move_player_logic(current_pos, steps, board_map)
        destination_ids.append(result["final_id"])

    return sorted(list(set(destination_ids)))

# TODO: Remove
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


    @classmethod
    async def _movement_phase(cls, user, game, action, data):
        if isinstance(action, ActionThrowDices):
            # TODO: Reread logic to fix this
            streak = game.streak
            result = await cls._roll_dices_logic(user, game, streak)
            await cls.update_game_state_dices(result, game, user)
            return result
            
        elif isinstance(action, ActionMoveTo):
            # TODO: use user and game to interact with DB
            streak = game.streak
            possible_squares = data.get("possible_chosen_squares", []) #method to DB to check the possible squares stored in previous move
            chosen_square_id = str(action.square.custom_id)
            
            result = cls._square_chosen_logic( possible_squares, chosen_square_id, game, user)
            if result:
                await cls.update_game_state_square_chosen(result, game, user)
            return result
        

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
        else:
            square = BaseSquare.objects.filter(custom_id=action.destinations[0])
            if isinstance(square, JailSquare):
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
                    
                    # TODO: Fix land_in_jail
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
                
                # TODO: Fix land_in_jail
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
