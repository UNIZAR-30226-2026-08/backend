from django.db import models
from django.contrib.auth.models import AbstractUser
from polymorphic.models import PolymorphicModel

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=40, unique=True)
    current_private_room: "PrivateRoom | None" = models.ForeignKey( 'PrivateRoom', on_delete=models.SET_NULL,  null=True,  blank=True,related_name='players') # type: ignore
    ready_to_play = models.BooleanField(default=False) # depending of the current private room could be interpreted as  ready or looking for a public game


    class Roles(models.TextChoices):
        regular = 'regular'
        admin = 'admin'
    role = models.CharField(choices=Roles, max_length=10, default='regular')

    owned_items = models.ManyToManyField('Item', blank=True, related_name='owners')
    played_games = models.ManyToManyField(
        'Game', 
        through='PlayerGameStatistic', 
        blank=True, 
        related_name='played_by'
    )

    active_game: "Game | None" = models.ForeignKey('Game', 
                                    on_delete=models.SET_NULL,
                                    null=True,
                                    blank=True,
                                    related_name='active_players') # type: ignore
    

    # Big ?
    points = models.PositiveIntegerField(default=0)
    exp = models.PositiveIntegerField(default=0)
    elo = models.PositiveIntegerField(default=0)
    user_piece = models.PositiveIntegerField(default=1) #TODO: poner default cuando tengamos fichas definidas
    num_played_games = models.PositiveIntegerField(default=0) #TODO: ir aumentando este dato
    num_won_games = models.PositiveIntegerField(default=0) #TODO: ir aumentando este dato
    

class Bot(CustomUser):
    bot_level = models.CharField(max_length=20, null=True, blank=True) # "easy" /"expert" etc
    has_proposed_trade = models.BooleanField(default=False)


class Item(models.Model):
    class ItemType(models.TextChoices):
        piece = 'piece'
        emoji = 'emoji'
    custom_id = models.PositiveIntegerField(unique=True)
    itemType = models.CharField(choices=ItemType, max_length=10, default='ficha')
    price = models.PositiveIntegerField(default=0)


###############################################################################

class Board(models.Model):
    # active_fantasy_cards = ...
    custom_id = models.PositiveIntegerField(default=0)
    pass

class BaseSquare(PolymorphicModel):
    custom_id = models.PositiveIntegerField(default=0)
    board = models.ForeignKey('Board',
                              on_delete=models.SET_NULL,
                              null=True,
                              blank=True,
                              related_name='part_of_table')
    in_successor = models.ForeignKey('BaseSquare',
                              on_delete=models.SET_NULL,
                              null=True,
                              blank=True,
                              related_name='in_predecessors')

class PropertySquare(BaseSquare):
    # Change
    group = models.PositiveIntegerField(default=0)
    buy_price = models.PositiveIntegerField(default=0)
    build_price = models.PositiveIntegerField(default=0)
    # An int[6] array
    rent_prices = models.JSONField(null=True)

class FantasySquare(BaseSquare):
    pass

class BridgeSquare(BaseSquare):
    buy_price = models.PositiveIntegerField(default=0)
    rent_prices = models.JSONField(null=True)
    out_successor = models.ForeignKey('BaseSquare',
                              on_delete=models.SET_NULL,
                              null=True,
                              blank=True,
                              related_name='out_predecessors')

class TramSquare(BaseSquare):
    buy_price = models.PositiveIntegerField(default=0)

class ParkingSquare(BaseSquare): #hendrix renting
    money = models.PositiveIntegerField(default=0)

class ServerSquare(BaseSquare):
    buy_price = models.PositiveIntegerField(default=0)
    # An int[2] array
    rent_prices = models.JSONField(null=True)

class ExitSquare(BaseSquare):
    init_money = models.PositiveIntegerField(default=0)

class GoToJailSquare(BaseSquare):
    pass

class JailSquare(BaseSquare):
    bail_price = models.PositiveIntegerField(default=0)

class JailVisitSquare(BaseSquare):
    pass

###############################################################################

#------ Models for Public Matchmaking Queue ------#
class PublicQueuePosition(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    channel = models.CharField(max_length=300) 
    date_time = models.DateTimeField()

#------ Models for Private Management ------#
class PrivateRoom(models.Model):
    #The one who starts the room and later the game
    owner:"CustomUser | None" = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='hosted_rooms')# type: ignore
    # Players will be linked from CustomUser.current_private_room
    room_code: str = models.CharField(max_length=10, unique=True) #type: ignore
    players: models.QuerySet['CustomUser']
    # Number of players total -> to include bots
    target_players = models.PositiveIntegerField(default=4)
    bot_level = models.CharField(max_length=20, default='medium')
    
class FantasyEvent(models.Model):
    """
    Fantasy events are triggered when a player lands on a fantasy square.
    
    Frontend Fantasy Payload Example:
    ```json
    {
      "type": "win_plain_money",
      "value": 20,
      "cost": 130
    }
    ```
    """
    class FantasyType(models.TextChoices):
        winPlainMoney = 'winPlainMoney',
        winRatioMoney = 'winRatioMoney',
        losePlainMoney = 'losePlainMoney',
        loseRatioMoney = 'loseRatioMoney',
        breakOpponentHouse = 'breakOpponentHouse',
        breakOwnHouse = 'breakOwnHouse',
        shufflePositions = 'shufflePositions',
        moveAnywhereRandom = 'moveAnywhereRandom',
        moveOpponentAnywhereRandom = 'moveOpponentAnywhereRandom',
        shareMoneyAll = 'shareMoneyAll',
        freeHouse = 'freeHouse',
        goToJail = 'goToJail',
        sendToJail = 'sendToJail',
        everybodyToJail = 'everybodyToJail',
        doubleOrNothing = 'doubleOrNothing',
        getParkingMoney = 'getParkingMoney',
        reviveProperty = 'reviveProperty',
        earthquake = 'earthquake',
        everybodySendsYouMoney = 'everybodySendsYouMoney',
        magnetism = 'magnetism',
        goToStart = 'goToStart'
    

    fantasy_type = models.CharField(choices=FantasyType, max_length=40)
    value = models.IntegerField(default=0, null=True)
    card_cost = models.IntegerField(default=0)

class FantasyResult(models.Model):
    fantasy_event = models.ForeignKey(FantasyEvent, on_delete=models.SET_NULL, related_name='fantasy_event_resulted', null=True)
    result = models.JSONField(null=True)

###############################################################################

class Game(models.Model):
    """
    Represents the core state and data of a single "Magnate" game session.

    Attributes:
        datetime (DateTimeField): The timestamp of when the game was created or started.
        positions (JSONField): Maps a player's user ID (str/int) to their current square's custom ID (int).
        money (JSONField): Maps a player's user ID (str/int) to their current money balance (int).
        active_phase_player (ForeignKey): The user who must take action in the current micro-phase 
            (e.g., the user who needs to respond to a trade, which might differ from the active_turn_player).
        active_turn_player (ForeignKey): The user whose actual turn it is on the board.
        phase (CharField): The current `GamePhase` of the game state machine.
        players (ManyToManyField): The pool of users actively participating in this game.
        ordered_players (JSONField): A list of player primary keys `[pk1, pk2, pk3, ...]` 
            representing the strict turn order of the game.
        streak (IntegerField): Tracks consecutive identical dice rolls (e.g., rolling doubles). 
            Usually triggers jail time if it hits 3.
        possible_destinations (JSONField): Maps a target `square_id` (str) to the `dice_combination` (int) 
            required to get there. Used when a player has multiple routing options (e.g., taking a tram).
        parking_money (PositiveIntegerField): The accumulated jackpot for landing on the "Free Parking" equivalent.
        jail_remaining_turns (JSONField): Maps a player's user ID (str/int) to the number of turns (int) 
            they have left to serve in jail.
        proposal (ForeignKey): A reference to an active trade proposal (`ActionTradeProposal`) currently 
            blocking the game state awaiting a response.
        fantasy_event (ForeignKey): A reference to an active chance/community chest style event 
            (`FantasyEvent`) currently being resolved.
        current_auction (ForeignKey): A reference to an active property auction (`Auction`) taking place.
        finished (BooleanField): Flag indicating if the game has concluded.
        bonus_response (ForeignKey): Reference to a specific bonus or penalty modifier (`ResponseBonus`) 
            applied to the current state.
        kick_out_task_id (CharField): The ID of the scheduled Celery task responsible for kicking 
            a player if they fail to act within the time limit.
        next_phase_task_id (CharField): The ID of the scheduled Celery task responsible for auto-advancing 
            the game to the next phase if a timeout occurs.
        current_turn (PositiveIntegerField): The global counter for the number of turns that have elapsed.
    """
    datetime = models.DateTimeField()
    # Maps user_id -> square_custom_id
    positions = models.JSONField(default=dict, blank=True)
    # Maps user_id -> amount
    money = models.JSONField(default=dict, blank=True)
    active_phase_player = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='phase_to_play')
    active_turn_player = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='turns_to_play')

    class GamePhase(models.TextChoices):
        """
        Enumeration of the possible states (phases) within a game's turn cycle.
        
        Attributes:
            roll_the_dices: The initial phase of a turn. The `active_turn_player` 
                must throw the dice to determine movement.
            choose_square: Triggered when a player's movement path presents a fork 
                or routing option (e.g., deciding whether to take a tram/subway line). 
                The player must select their specific destination square.
            choose_fantasy: Triggered when a player lands on a dynamic event square 
                The player must acknowledge and resolve the active `fantasy_event`.
            management: Triggered when a player lands on an unowned property. The 
                player must choose to either purchase the property at its list price 
                or decline the purchase (which typically immediately triggers an `auction`).
            business: A versatile phase usually occurring at the end of a turn 
                or before a roll. The player can build/demolish houses, mortgage/unmortgage 
                properties, or finalize their board state before passing the turn.
            liquidation: An emergency phase triggered when a player owes a debt 
                (to the bank or another player) that exceeds their current liquid cash. 
                They are forced to sell assets or mortgage properties to cover the debt, 
                or face bankruptcy.
            auction: A competitive, multi-player phase triggered when a property 
                is declined in the `management` phase. The standard turn loop pauses, and 
                players take turns placing bids until a winner is determined.
            proposal_acceptance: An interruptive phase triggered when one player 
                sends a trade request to another. The game loop pauses, the 
                `active_phase_player` switches to the recipient, and they must either 
                accept or decline the pending `proposal`.
            end_game: A terminal state indicating the match has concluded, usually 
                because all other players have gone bankrupt. No further actions can 
                be taken.
        """
        roll_the_dices = 'roll_the_dices'
        choose_square = 'choose_square'
        choose_fantasy = 'choose_fantasy'
        management = 'management'
        liquidation = 'liquidation'
        business = 'business'
        auction = 'auction'
        proposal_acceptance = 'proposal_acceptance'
        end_game = 'end_game'


    phase = models.CharField(choices=GamePhase, max_length=20, default='roll_the_dices')
    players = models.ManyToManyField('CustomUser', related_name='active_playing')
    # ordered_player = [pk1, pk2, pk3, ...]
    ordered_players = models.JSONField(default=list)
    streak = models.IntegerField(default=0)
    #dict[string,int], key=square_id, value=dice_combination to get there
    possible_destinations = models.JSONField(default=dict, blank=True)
    parking_money = models.PositiveIntegerField(default=0)
    # Maps user_id -> uint
    jail_remaining_turns = models.JSONField(default=dict, blank=True)
    proposal = models.ForeignKey('ActionTradeProposal', on_delete=models.SET_NULL, null=True, blank=True, related_name='trade_proposal')

    fantasy_event = models.ForeignKey('FantasyEvent', on_delete=models.SET_NULL, null=True, blank=True, related_name='fantasy_event')

    current_auction = models.ForeignKey('Auction', on_delete=models.SET_NULL, null=True, blank=True, related_name='active_game')
    
    finished = models.BooleanField(default=False)
    bonus_response = models.ForeignKey('ResponseBonus', on_delete=models.SET_NULL, null=True, blank=True, related_name='bonus_response')

    kick_out_task_id = models.CharField(max_length=255, null=True, blank=True)
    next_phase_task_id = models.CharField(max_length=255, null=True, blank=True)

    current_turn = models.PositiveIntegerField(default=1)

class Auction(models.Model):
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='auctions')
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='auctioned_in')
    bids = models.JSONField(default=dict, blank=True) #  user_id -> amount
    final_amount = models.PositiveIntegerField(null=True, blank=True)
    winner = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='won_auctions') # type: ignore
    is_active = models.BooleanField(default=True)
    is_tie = models.BooleanField(default=False)

class PropertyRelationship(models.Model):
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='property_relationships')
    owner = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='owned_by') # type: ignore
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='owned_square')

    houses = models.IntegerField(default=-1)# -1: incomplete group, 0: complete group,
                                            #1-4: houses, #5: hotel
    mortgage = models.BooleanField(default=False)

###############################################################################

class Action(models.Model):
    """
    Represents generic action, so every action shares these fields
    
    Frontend Request Payload Example:
    ```json
    {
      "type": "Action",
      "game": 1,
      "player": 2,
    }
    ```
    """
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='in_game')
    player = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='made_by')

class ActionThrowDices(Action):
    """
    Action to throw the dices. It is basically empty.
    
    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionThrowDices",
      "game": 1,
      "player": 2,
    }
    ```
    """
    pass

class ActionMoveTo(Action):
    """
    Action to move to a square. 
    
    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionThrowDices",
      "game": 1,
      "player": 2,
      "square": 101,
    }
    ```
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='move_to')

class ActionTakeTram(Action):
    """
    Action to take the tram when possible
    
    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionTakeTram",
      "game": 1,
      "player": 2,
      "square": 200,
    }
    ```
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='tram_move_to')

class ActionDropPurchase(Action):
    """
    Action to decline purchasing a property.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionDropPurchase",
      "game": 1,
      "player": 2,
      "square": 15
    }
    ```
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='dropped')

class ActionBuySquare(Action):
    """
    Action to buy an unowned property.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionBuySquare",
      "game": 1,
      "player": 2,
      "square": 15
    }
    ```
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='bought')

class ActionSellSquare(Action):
    """
    Action to sell a property.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionSellSquare",
      "game": 1,
      "player": 2,
      "square": 15
    }
    ```
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='sold')

class ActionBuild(Action):
    """
    Action to build houses/hotels on a property.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionBuild",
      "game": 1,
      "player": 2,
      "houses": 1,
      "square": 12
    }
    ```
    """
    houses = models.IntegerField(default=1)
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='build_square')

class ActionDemolish(Action):
    """
    Action to demolish houses/hotels on a property.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionDemolish",
      "game": 1,
      "player": 2,
      "houses": 1,
      "square": 12
    }
    ```
    """
    houses = models.IntegerField(default=0)
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='demolish_square')

class ActionChooseCard(Action):
    """
    Action to interact with or draw a fantasy card.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionChooseCard",
      "game": 1,
      "player": 2,
      "chosen_revealed_card": true
    }
    ```
    """
    chosen_revealed_card = models.BooleanField(default=False)

class ActionSurrender(Action):
    """
    Action to quit/surrender the game. It is empty.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionSurrender",
      "game": 1,
      "player": 2
    }
    ```
    """
    pass

class ActionTradeProposal(Action):
    """
    Action to propose a trade to another player.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionTradeProposal",
      "game": 1,
      "player": 2,
      "destination_user": 3,
      "offered_money": 200,
      "asked_money": 0,
      "offered_properties": [5, 6],
      "asked_properties": [12]
    }
    ```
    """
    destination_user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='destination_user')
    offered_money = models.PositiveIntegerField(default=0)
    asked_money = models.PositiveIntegerField(default=0)
    offered_properties = models.ManyToManyField('PropertyRelationship', related_name='offered_properties')
    asked_properties = models.ManyToManyField('PropertyRelationship', related_name='asked_properties')

class ActionTradeAnswer(Action):
    """
    Action to accept or decline a trade proposal.
    choose = True if trade was accepted

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionTradeAnswer",
      "game": 1,
      "player": 2,
      "choose": true,
    }
    ```
    """
    choose = models.BooleanField(default=False)

class ActionMortgageSet(Action):
    """
    Action to mortgage a property.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionMortgageSet",
      "game": 1,
      "player": 2,
      "square": 15
    }
    ```
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='mortgage_set_square')

class ActionMortgageUnset(Action):
    """
    Action to lift a mortgage from a property.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionMortgageUnset",
      "game": 1,
      "player": 2,
      "square": 15
    }
    ```
    """
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='mortgage_unset_square')

class ActionPayBail(Action):
    """
    Action to pay the bail fee to get out of jail. It is empty.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionPayBail",
      "game": 1,
      "player": 2
    }
    ```
    """
    pass

class ActionNextPhase(Action):
    """
    Action to transition to the next game phase or end turn. It is empty.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionNextPhase",
      "game": 1,
      "player": 2
    }
    ```
    """
    pass

class ActionBid(Action):
    """
    Action to place a bid on a property auction.

    Frontend Request Payload Example:
    ```json
    {
      "type": "ActionBid",
      "game": 1,
      "player": 2,
      "auction": 4,
      "amount": 150
    }
    ```
    """
    amount = models.PositiveIntegerField(default=0)

###############################################################################

class Response(models.Model):
    """
    Base model for game state updates broadcasted to the frontend.
    
    Frontend Response Payload Example:
    ```json
    {
      "type": "Response",
      "money": {"1": 1500, "2": 1200},
      "active_phase_player": 2,
      "active_turn_player": 2,
      "phase": "management"
    }
    ```
    """
    money = models.JSONField(default=dict, blank=True)
    active_phase_player = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='response_phase_to_play')
    active_turn_player = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='response_turns_to_play')
    phase = models.CharField(choices=Game.GamePhase, max_length=20)
    positions = models.JSONField(default=dict, blank=True) # user -> cumtom_id (int)

class ResponseSkipPhase(Response):
    """
    Base response for an event that skips a phase
    
    Frontend Response Payload Example:
    ```json
    {
      "type": "Response",
      "money": {"1": 1500, "2": 1200},
      "active_phase_player": 2,
      "active_turn_player": 2,
      "phase": "management"
    }
    ```
    """
    pass

class ResponseMovement(Response):
    """
    Base response for an event that moves a player across the board.
    
    Frontend Response Payload Example:
    ```json
    {
      "type": "ResponseMovement",
      "money": {"1": 1500, "2": 1200},
      "active_phase_player": 2,
      "active_turn_player": 2,
      "phase": "moving",
      "path": [10, 11, 12, 13, 14, 15],
      "fantasy_event": null
    }
    ```
    """
    path = models.JSONField(default=list, blank=True)
    fantasy_event = models.ForeignKey('FantasyEvent', on_delete=models.CASCADE, null=True, blank=True)

class ResponseThrowDices(ResponseMovement):
    """
    Response detailing the result of a dice roll and valid movement destinations.
    
    Frontend Response Payload Example:
    ```json
    {
      "type": "ResponseThrowDices",
      "money": {"1": 1500, "2": 1200},
      "active_phase_player": 2,
      "active_turn_player": 2,
      "phase": "moving",
      "path": [10, 11, 12],
      "fantasy_event": null,
      "dice1": 4,
      "dice2": 3,
      "dice_bus": 1,
      "destinations": [17],
      "triple": false,
      "streak": 0
    }
    ```
    """
    dice1 = models.PositiveIntegerField(default=0)
    dice2 = models.PositiveIntegerField(default=0)
    dice_bus = models.PositiveIntegerField(default=0)
    destinations = models.JSONField(default=list, blank=True)
    triple = models.BooleanField(default=False)
    streak = models.IntegerField(default=0)

class ResponseChooseSquare(ResponseMovement):
    """
    Response confirming a player's movement to a specifically chosen square.
    
    Frontend Response Payload Example:
    ```json
    {
      "type": "ResponseChooseSquare",
      "money": {"1": 1500, "2": 1200},
      "active_phase_player": 2,
      "active_turn_player": 2,
      "phase": "moving",
      "path": [10, 25],
      "fantasy_event": null
    }
    ```
    """
    pass

class ResponseChooseFantasy(Response):
    """
    Response delivering the result of a drawn Chance/Community Chest card.
    
    Frontend Response Payload Example:
    ```json
    {'type': 'ResponseChooseFantasy', 
     'fantasy_result': {'fantasy_event': {'fantasy_type': 'freeHouse', 'value': None, 'card_cost': 80}, 'result': None}, 
     'money': {'1': 1440, '2': 1500}, 
     'phase': 'business', 
     'positions': {'1': '10', '2': '17'}, 
     'active_phase_player': 2, 
     'active_turn_player': 2
    }
    ```
    """
    fantasy_result = models.ForeignKey('FantasyResult', on_delete=models.CASCADE)

class ResponseAuction(Response):
    """
    Response updating the state of an ongoing or completed auction.
    Note: The @property decorators will likely be serialized as regular fields.
    
    Frontend Response Payload Example:
    ```json
    {
      "type": "ResponseAuction",
      "money": {"1": 1150, "2": 1200},
      "active_phase_player": 1,
      "active_turn_player": 2,
      "phase": "management",
      "auction": 12,
      "winner": 1,
      "final_amount": 350,
      "is_tie": false
    }
    ```
    """
    auction = models.OneToOneField('Auction', on_delete=models.CASCADE, related_name='response')

    @property
    def winner(self):
        return self.auction.winner
    
    @property
    def final_amount(self):
        return self.auction.final_amount
    
    @property
    def is_tie(self):
        return self.auction.is_tie
    
class ResponseBonus(Response):
    """
    Response delivering the result of a drawn Chance/Community Chest card.
    
    Frontend Response Payload Example:
    ```json
    {
    "type": "ResponseBonus",
    "money": {"1": 1600, "2": 1200},
    "active_phase_player": 2,
    "active_turn_player": 2,
    "phase": "management",
    "bonuses": {
    "walked_squares": {"display_name": "El más viajero", "bonus_amount": 200, "winners": [1, 3]},
    "built_houses":   {"display_name": "El más constructor", "bonus_amount": 200, "winners": [2]},
    "num_trades":     {"display_name": "El más trader", "bonus_amount": 200, "winners": []}
}
    }
    }
    ```
    """
    bonuses = models.JSONField(default=dict, blank=True)

###############################################################################

# la relacion jugador-partida ahora es esto (django pilota)
# y puedo añadir info adicional además de la relación, las stats
class PlayerGameStatistic(models.Model):
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE)
    game = models.ForeignKey('Game', on_delete=models.CASCADE)
    
    walked_squares = models.PositiveIntegerField(default=0)
    won_money = models.PositiveIntegerField(default=0)
    lost_money = models.PositiveIntegerField(default=0)
    num_fantasy_events = models.PositiveIntegerField(default=0)
    built_houses = models.PositiveIntegerField(default=0)
    demolished_houses = models.PositiveIntegerField(default=0)
    times_in_jail = models.PositiveIntegerField(default=0)
    turns_in_jail = models.PositiveIntegerField(default=0)
    num_paid_rents = models.PositiveIntegerField(default=0)
    num_trades = models.PositiveIntegerField(default=0)
    num_mortgages = models.PositiveIntegerField(default=0)
    
    class Meta:
        # 1 player and game for each stats
        unique_together = ('user', 'game')

class BonusCategory(models.Model):
    class StatField(models.TextChoices):
        walked_squares    = 'walked_squares'
        won_money         = 'won_money'
        lost_money        = 'lost_money'
        num_fantasy_events = 'num_fantasy_events'
        built_houses      = 'built_houses'
        demolished_houses = 'demolished_houses'
        times_in_jail     = 'times_in_jail'
        turns_in_jail     = 'turns_in_jail'
        num_paid_rents    = 'num_paid_rents'
        num_trades        = 'num_trades'
        num_mortgages     = 'num_mortgages'
        end_game = 'end_game'

    stat_field = models.CharField(choices=StatField, max_length=30, unique=True)
    bonus_amount = models.PositiveIntegerField(default=200)
