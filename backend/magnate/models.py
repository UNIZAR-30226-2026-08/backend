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
    played_games = models.ManyToManyField('Game', blank=True, related_name='played_by')

    active_game: "Game | None" = models.ForeignKey('Game', 
                                    on_delete=models.SET_NULL,
                                    null=True,
                                    blank=True,
                                    related_name='active_players') # type: ignore
    

    # Big ?
    points = models.PositiveIntegerField(default=0)
    exp = models.PositiveIntegerField(default=0)
    elo = models.PositiveIntegerField(default=0)

class Item(models.Model):
    class ItemType(models.TextChoices):
        ficha = 'ficha'
        iconos = 'iconos'
    itemType = models.CharField(choices=ItemType, max_length=10, default='ficha')


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
    
class FantasyEvent(models.Model):
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
    values = models.JSONField(null=True)
    card_cost = models.IntegerField(default=0)

    def __init__(self, fantasy_type, values, card_cost):
        self.fantasy_type = fantasy_type
        self.values = values
        self.card_cost = card_cost

class FantasyResult(models.Model):
    fantasy_type = models.CharField(choices=FantasyEvent.FantasyType, max_length=40)
    values = models.JSONField(null=True)

###############################################################################

class Game(models.Model):
    datetime = models.DateTimeField()
    # Maps user_id -> square_custom_id
    positions = models.JSONField(default=dict, blank=True)
    # Maps user_id -> amount
    money = models.JSONField(default=dict, blank=True)
    # TODO: Look for better names
    active_phase_player = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='phase_to_play')
    active_turn_player = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='turns_to_play')

    class GamePhase(models.TextChoices):
        roll_the_dices = 'roll_the_dices'
        choose_square = 'choose_square'
        management = 'management'
        liquidation = 'liquidation'
        business = 'business'
        auction = 'auction'
        proposal_acceptance = 'proposal_acceptance'


    phase = models.CharField(choices=GamePhase, max_length=20, default='roll_the_dices')
    players = models.ManyToManyField('CustomUser', related_name='active_playing')
    streak = models.IntegerField(default=0)
    possible_destinations = models.JSONField(default=list, blank=True)
    parking_money = models.PositiveIntegerField(default=0)
    # Maps user_id -> uint
    jail_remaining_turns = models.JSONField(default=dict, blank=True)
    proposal = models.ForeignKey('ActionTradeProposal', on_delete=models.SET_NULL, null=True, blank=True, related_name='trade_proposal')

    auction_state = models.JSONField(default=dict, blank=True)


class PropertyRelationship(models.Model):
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='PropertyRelationship_in_game')
    owner = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='owned_by') # type: ignore
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='owned_square')

    houses = models.IntegerField(default=-1)# -1: incomplete group, 0: complete group,
                                            #1-4: houses, #5: hotel
    mortgage = models.BooleanField(default=False)

###############################################################################

class Action(models.Model):
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='in_game')
    player = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='made_by')

class ActionThrowDices(Action):
    dice1 = models.PositiveIntegerField(default=0)
    dice2 = models.PositiveIntegerField(default=0)
    # One of them is bus
    dice_bus = models.PositiveIntegerField(default=0)
    destinations = models.JSONField(default=list, blank=True)
    triple = models.BooleanField(default=False)
    path = models.JSONField(default=list, blank=True)
    streak = models.IntegerField(default=0)

class ActionMoveTo(Action):
    # Custom ID or real ID ? Mario opina que custom ID
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='move_to')

class ActionTakeTram(Action):
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='tram_move_to')

class ActionDoNotTakeTram(Action):
    pass

class ActionDropPurchase(Action):
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='dropped')

class ActionBuySquare(Action):
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='bought')

class ActionSellSquare(Action):
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='sold')

class ActionGoToJail(Action):
    pass

class ActionBuild(Action):
    houses = models.IntegerField(default=1)
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='build_square')

class ActionDemolish(Action):
    houses = models.IntegerField(default=0)
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='demolish_square')

class ActionChooseCard(Action):
    chosen_card = models.BooleanField(default=False)

class ActionSurrender(Action):
    pass

class ActionTradeProposal(Action):
    destination_user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='destination_user')
    offered_money = models.PositiveIntegerField(default=0)
    asked_money = models.PositiveIntegerField(default=0)
    offered_properties = models.ManyToManyField('PropertyRelationship', related_name='offered_properties')
    asked_properties = models.ManyToManyField('PropertyRelationship', related_name='asked_properties')

class ActionTradeAnswer(Action):
    choose = models.BooleanField(default=False)
    proposal = models.OneToOneField('ActionTradeProposal', on_delete=models.CASCADE, related_name='proposal')

class ActionMortgageSet(Action):
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='mortgage_set_square')

class ActionMortgageUnset(Action):
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='mortgage_unset_square')

class ActionPayBail(Action):
    pass

class ActionNextPhase(Action):
    pass

class ActionBid(Action):
    amount = models.PositiveIntegerField(default=0)

###############################################################################

class Response(models.Model):
    # TODO: Complete
    pass