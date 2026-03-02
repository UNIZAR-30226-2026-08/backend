from asyncio import Server
import random 
import json
from tokenize import group
from django.db import transaction
from numpy import square

from backend.magnate.serializers import *
from .models import *
from channels.db import database_sync_to_async

def _get_square_by_custom_id(custom_id: int) -> BaseSquare:
    square = BaseSquare.objects.filter(custom_id=custom_id)
    if len(square) < 1:
        raise GameLogicError(f"no square with id {custom_id}")
    return square.first()

def _get_user_square(user: CustomUser) -> BaseSquare:
    if user not in game.current_square:
        raise GameLogicError(f"user {user} not in the game")
    return _get_square_by_custom_id(game.current_square[user])

def _get_relationship(game: Game, square: BaseSquare) -> PropertyRelationship:
    relationship = PropertyRelationship.objects.get(game=game, square=square)

    if not relationship.exists():
        raise MaliciousUserInput(f"no user owns this square")
    elif len(relationship) > 1:
        raise GameLogicError(f"more than one owners for the same square")
    else:
        relationship = relationship.first()

    return relationship

def _get_rent_price(square: PropertySquare, _property: PropertyRelationship):
    houses = _property.houses
    if square.rent_prices is None:
        return None #TODO excepcion
    if houses == -1:
        return square.rent_prices[0]
    elif houses == 0:
        return square.rent_prices[1]
    elif houses == 1:
        return square.rent_prices[2]
    elif houses == 2:
        return square.rent_prices[3]
    elif houses == 3:
        return square.rent_prices[4]
    elif houses == 4:
        return square.rent_prices[5]

def move_player_logic(curr, total_steps) -> {}:
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
            curr = curr.in_successor
        else:
            curr = curr.in_successor
        
        if curr is None:
            raise GameDesignError(f"no succesor found")
        
        path_log.append(curr.custom_id)

    if isinstance(curr, GoToJailSquare):
        curr = JailSquare.objects.first()
        if curr is None:
            raise GameDesignError(f"no jail square")

    return {"final_id": curr.custom_id, 
            "path": path_log, "passed_go": passed_go}

async def get_possible_destinations_ids(user, game, step_options):
    destination_ids = []
    current_pos = game.positions[user]
        
    for steps in step_options:
        result = move_player_logic(current_pos, steps)
        destination_ids.append(result["final_id"])

    return sorted(list(set(destination_ids)))

class GameManager:
    
    @classmethod
    async def process_action(cls, user, game, action, data):
        if game.phase == "roll_the_dices":
            return await cls._roll_dices_logic(user, game, streak=game.streak)
        elif game.phase == "choose_square":
            return await cls._square_chosen_logic(game.possible_destinations, user, game, action)
        elif game.phase == "management":
            return await cls._management_logic(user, game, action, data)
        elif game.phase == "bussiness":
            return await cls._bussiness_logic(user, game, action, data)
        elif game.phase == "answer_trade_proposal":
            return await cls._answer_trade_proposal_logic(user, game, action, data)
        elif game.phase == "liquidation":
            return await cls._liquidation_logic(user, game, action, data)

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

        if len(action.destinations) > 1:
            game.phase = "choose_square"
        else:
            square = BaseSquare.objects.filter(custom_id=action.destinations[0])

            if len(square) > 1:
                raise GameDesignError('too many squares for the same custom_id')
            else:
                square = square[0]

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
        square =  _get_user_square(user)
        jail_square = JailSquare.objects.first()

        if isinstance(square, JailSquare) and not doubles:
            action.triple = False
            action.path = []
            action.destinations = [jail_square.custom_id]
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
                action.destinations = [jail_square.custom_id]
                action.streak = 3
                await GameManager.update_game_state_dices(action, game, user)
                return action
            
            else:
                action.streak= streak + 1
                if bus_is_numeric:
                    
                    # TODO: Fix land_in_jail
                    in_jail, action.path = land_in_jail(game, d1+d2, user, BOARD_MAP)
                    action.destinations = action.path[-1] if not in_jail else [jail_square.custom_id]
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
                action.destinations = action.path[-1] if not in_jail else [jail_square.custom_id]
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
    async def _square_chosen_logic(possible_chosen_squares, square, game, user):
        # Logic of movement when the user direcctly chooses a square due to a bus or triples

        action = ActionMoveTo(game = game, player = user)
        
        if square not in possible_chosen_squares:
            raise MaliciousUserInput(f"user {user} tried to move to an illegal square")
        
        action.square = square

        await GameManager.update_game_state_square_chosen(action, game, user)
        return action
    
       
    @staticmethod
    @database_sync_to_async
    async def _management_logic(user, game, action, data):
        """
        Logic of management phase, where the user can buy properties, pay bills etc

        first -> what is the action? -> check internally its current square and data associated ->
            Then check user info to update the game state accordingly and return next state
        """
        current_square = _get_user_square(user)

        if isinstance(current_square, PropertySquare):
            _property = PropertyRelationship.objects.filter(game=game, square=current_square)
            if len(_property) > 1:
                raise GameLogicError(f"square {current_square} is owned by more than one player")
            elif property.exists() and property: #  pay rent -> check houses
                # FIXME: get this outta here
                _property = _property.first()
                to_pay = _get_rent_price(current_square, _property)
                property_owner = first.owner
                game.money[user] -= to_pay
                game.money[property_owner] += to_pay
                game.phase = "business"
                game.save()
            else: #buy option -> look at data to see if the user wants to buy and if he can afford it
                if isinstance(action, ActionBuySquare):
                    game.money[user] -= current_square.buy_price
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


        elif isinstance(current_square, ServerSquare):
            property = PropertyRelationship.objects.filter(game=game, square=current_square)
            if property.exists(): #  pay rent
                #Check whether the user owns the other ServerSquare 
                first = property.first()
                if first is None:
                    return None#TODO: expecion
                property_owner = first.owner
                squares = PropertyRelationship.objects.filter(game=game, square__type='server_squares', owner=property_owner)
                if current_square.rent_prices is None:
                    return None #TODO: excepcion
                if squares.count() == 2:
                    to_pay = current_square.rent_prices[1]
                else:
                    to_pay = current_square.rent_prices[0]

                game.money[user] -= to_pay
                game.money[property_owner] += to_pay
                game.phase = "business"
                game.save()

            else: #buy option -> look at data to see if the user wants to buy and if he can afford it
                if isinstance(action, ActionBuySquare):
                    game.money[user] -= current_square.buy_price
                    game.phase = "business"
                    new_property = PropertyRelationship(game=game, square=current_square, owner=user)
                    new_property.save()
                    game.save()
                elif isinstance(action, ActionDropPurchase):
                    game.phase = "auction"
                    # TODO: logic of auction
                    pass
            
            return {"next_phase": game.phase}
           
        else:
            raise GameLogicError('invalid action in management handling')

    @staticmethod
    async def _bussiness_logic(user, game, action, data):
        """
        Unifies the business and liquidation phases
        TODO: Liquidation
        """

        # Logic for the business phase where players can build houses, trade, etc.
        if isinstance(action, ActionBuild):
            # Check if squares are from user and if he has the complete group -> check limitations
            # Check if there's no difference of 2 built houeses between group squares

            # Check owner 
            building_square = action.square

            # Check if it's  a property and take its group
            if not isinstance(building_square, PropertySquare):
                raise MaliciousUserInput(f"user {user} tried to build in a non property square")

            relationship = _get_relationship(game, square)

            if relationship.owner != user:
                raise MaliciousUserInput(f"user {user} tried to build in an unowned property")

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
                raise MaliciousUserInput(f"user {user} does not own the group")

            for rel in group_relationships:
                if rel.houses < 0: 
                    raise GameLogicError(f"negative house value")
                elif actual_houses + action.houses - 1 > rel.houses:
                    raise MaliciousUserInput(f"already owns more than other")

            if actual_houses == 5:
                raise MaliciousUserInput(f"nothing more to build")

            relationship.houses += action.houses
            relationship.save()
            
            coste = building_square.build_price

            game.money[user] -= coste
            game.save()

            return relationship  #ack
            
        elif isinstance(action, ActionDemolish):
            # Similiar to build
            demolition_square = action.square

            #Check if it's  a property
            if not isinstance(demolition_square, PropertySquare):
                raise MaliciousUserInput(f"user {user} tried to build in a non property square")

            relationship = PropertyRelationship.objects.get(game=game, square=demolition_square)
            if not relationship.exists():
                raise MaliciousUserInput(f"no user owns this square")
            elif len(relationship) > 1:
                raise GameLogicError(f"more than one owners for the same square")
            else:
                relationship = relationship.first()

            if relationship.owner != user:
                raise MaliciousUserInput(f"user {user} tried to demolish in an unowned property")

            if actual_houses < number_demolished:
                raise MaliciousUserInput(f"user {user} tried to demolish more houses that they are built")

            square_group = demolition_square.group
    
            
            group_relationships = PropertyRelationship.objects.filter(
                game=game, 
                owner=user, 
                square__propertysquare__group=square_group
            ).select_related('square')

            # Check if we can demolish -> respect rule
            for rel in group_relationships:
                if actual_houses - number_demolished < rel.houses - 1:
                    # TODO: no se puede demoler ya que habria diferencia de 2
                    raise MaliciousUserInput(f"unable to demolish so many houses")

            relationship.houses -= number_demolished
            relationship.save()
            
            coste  = demolition_square.build_price

            user_id_str = str(user.id)
            
            
            #update game state -> we continue in the same phase
            game.money[user_id_str] += coste//2
            game.save()

            return relationship  #ack


        
        elif isinstance(action, ActionTradeProposal):
            """
            Check if every number /property makes sense, then sned to frond a
            waiting message and to all players the action The destination
            players must decide whether or not to accept -> think of a way to
            do that -> front messages 
            """
            offering = action.offering_user
            destination = action.destination_user
            offered_money = action.offered_money
            asked_money = action.asked_money
            offered_properties = action.offered_properties
            asked_properties = action.asked_properties

            if offering != user or offered_money < 0 or asked_money < 0:
                raise MaliciousUserInput(f"user {user} cannot do operation {action}")

            asked_properties_list = asked_properties.all()
            asked_count = PropertyRelationship.objects.filter(
                game=game, 
                owner=destination, 
                id__in=asked_properties_list
            ).count()

            if asked_count != asked_properties_list.count():
                raise MaliciousUserInput(f"destination does not have enough properties")

            offered_properties_list = offered_properties.all()
            offered_count = PropertyRelationship.objects.filter(
                game=game, 
                owner=offering, 
                id__in=offered_properties_list
            ).count()

            if offered_count != offered_properties_list.count():
                raise MaliciousUserInput(f"offer does not have enough properties")
            
            #update the game phase to proposal acceptance and change turn
            game.phase = "proposal_acceptance"
            game.active_player = destination
            game.save()

        elif isinstance(action, ActionMortgageSet):
            target_square = action.square
            
            try:
                relationship = PropertyRelationship.objects.get(
                    game=game, 
                    square=target_square, 
                    owner=user
                )
            except PropertyRelationship.DoesNotExist:
                raise MailiciousUserInput(f"user {user} tried to mortgage an unowned property")

            if not isinstance(target_square, PropertySquare):
                raise MailiciousUserInput(f"user {user} tried to mortgage a square that is not a property")

            if relationship.houses == -2:
                raise MailiciousUserInput(f"user {user} tried to mortgage an already mortgaged property")

            group_relationships = PropertyRelationship.objects.filter(
                game=game,
                square__propertysquare__group=target_square.group
            ).select_related('square')

            total_refund = 0
            user_id_str = str(user.id)

            for rel in group_relationships:
                # demolish if necessary
                if rel.houses > 0:
                    houses_to_sell = rel.houses
                    build_price = rel.square.propertysquare.build_price
                    
                    refund = (houses_to_sell * build_price) // 2
                    total_refund += refund
                    
                    # reset to -1
                    rel.houses = -1
                    rel.save()

            mortgage_value = target_square.buy_price // 2
            total_gain = total_refund + mortgage_value

            relationship.houses = -2 
            relationship.save()

            game.money[user_id_str] += total_gain
            game.save()

            return action
        

        elif isinstance(action, ActionMortgageUnset):
            target_square = action.square
            user_id_str = str(user.id)
            
            try:
                relationship = PropertyRelationship.objects.get(
                    game=game, 
                    square=target_square, 
                    owner=user
                )
            except PropertyRelationship.DoesNotExist:
                raise MailiciousUserInput(f"user {user} tried to unmortgage a square that is not a property")

            if relationship.houses != -2:
                raise MailiciousUserInput(f"user {user} tried to unmortgage a square that is not mortgaged")

            mortgage_value = target_square.buy_price // 2
            total_cost = mortgage_value

            game.money[user_id_str] -= total_cost
            relationship.houses = -1 # incomplete
            relationship.save()

            total_in_group = PropertySquare.objects.filter(
                board=target_square.board, 
                group=target_square.group
            ).count()

            owned_active_in_group = PropertyRelationship.objects.filter(
                game=game,
                owner=user,
                square__propertysquare__group=target_square.group
            ).exclude(houses=-2)

            if owned_active_in_group.count() == total_in_group:
                owned_active_in_group.update(houses=0)
            
            game.save()

            return action

        else:
            raise MailiciousUserInput(f"user {user} cannot perform action {action} in phase {game.phase}")

        if game.money[str(user.id)] < 0:
            game.phase = "liquidation"
        elif game.phase == "liquidation" and game.money[str(user.id)] > 0:
            # TODO: finish
            game.phase = "roll_the_dices"
        
        all_players = game.players
        players_list = list(game.players.all().order_by('id')) 
        num_players = len(players_list)
        current_index = -1
        for i, p in enumerate(players_list):
            if p == game.active_player:
                current_index = i
                break
        
        next_index = (current_index + 1) % num_players
        game.active_player = players_list[next_index]
        game.save()
            
        return action
                    
    @staticmethod
    async def _answer_trade_proposal_logic(user, game, action, data):
        if isinstance(action, ActionTradeAnswer):
            #check if the action is the same as it was offered and check the boolean
            accept = action.choose
            offer = action.proposal

            offering = offer.offering_user
            destination = offer.destination_user

            proposal_previous_phase = game.proposal

            offered_money = offer.offered_money
            asked_money = offer.asked_money
            offered_properties = offer.offered_properties
            asked_properties = offer.asked_properties

            if user != destination:
                return None #TODO: error -> proposal is not for u mate
            

            if offer != proposal_previous_phase:
                return None #TODO: you tricking me
            
            if accept:
                for relationship in offered_properties.all():
                    relationship.owner = destination
                    relationship.houses = -1 # reset houses
                    relationship.save()
                    
                for relationship in asked_properties.all():
                    relationship.owner = offering
                    relationship.houses = -1
                    relationship.save()
                game.money[str(offering.id)] -= offered_money
                game.money[str(offering.id)] += asked_money
                
                game.money[str(destination.id)] -= asked_money
                game.money[str(destination.id)] += offered_money

                game.save()
                

            game.phase = "bussiness"
            game.active_player = offering
            game.save()


            return action
        else:
            raise GameLogicError(f"cannot process action {action} in trade proposal logic")
        

