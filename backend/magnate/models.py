from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    # TODO: Max length ?
    # TODO: Needed ?
    username = models.CharField(max_length=40, unique=True)
    # TODO: Needed ?
    current_private_room = models.ForeignKey( 'PrivateRoom', on_delete=models.SET_NULL,  null=True,  blank=True,related_name='players')
    ready_to_play = models.BooleanField(default=False) # depending of the current private room could be interpreted as  ready or looking for a public game


    class Roles(models.TextChoices):
        regular = 'regular'
        admin = 'admin'
    role = models.CharField(choices=Roles, max_length=10, default='regular')

    owned_items = models.ManyToManyField('Item', blank=True, related_name='owners')
    played_games = models.ManyToManyField('Game', blank=True, related_name='played_by')

    active_game = models.ForeignKey('Game', 
                                    on_delete=models.SET_NULL,
                                    null=True,
                                    blank=True,
                                    related_name='active_players')

    # Big ?
    points = models.PositiveIntegerField(default=0)
    exp = models.PositiveIntegerField(default=0)
    elo = models.PositiveIntegerField(default=0)

class Item(models.Model):
    class ItemType(models.TextChoices):
        ficha = 'ficha'
        iconos = 'iconos'
    itemType = models.CharField(choices=ItemType, max_length=10, default='ficha')

#defined below
#class Game(models.Model):
#    datetime = models.DateTimeField()
#    # TODO: What happens if a user has deleted his account

###############################################################################

class Board(models.Model):
    # active_fantasy_cards = ...
    custom_id = models.PositiveIntegerField(default=0)
    pass

class BaseSquare(models.Model):
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
    build_price = models.PositiveIntegerField(default=0)
    # An int[2] array
    rent_prices = models.JSONField(null=True)
    out_successor = models.ForeignKey('BaseSquare',
                              on_delete=models.SET_NULL,
                              null=True,
                              blank=True,
                              related_name='out_predecessors')

class TramSquare(BaseSquare):
    buy_price = models.PositiveIntegerField(default=0)

class ParkingSquare(BaseSquare):
    price = models.PositiveIntegerField(default=0)

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

###############################################################################

#------ Models for Public Matchmaking Queue ------#
class PublicQueuePosition(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    # TODO: check this max length
    channel = models.CharField(max_length=300) 
    date_time = models.DateTimeField()

    # TODO: implement skill based matchmaking / start with timestamps ¿?

#------ Models for Private Management ------#
class PrivateRoom(models.Model):
    #The one who starts the room and later the game
    owner = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='hosted_rooms')
    # TODO: set max_length
    # Players will be linked from CustomUser.current_private_room
    room_code = models.CharField(max_length=10, unique=True)
    
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
        dontPayNextTurnRent = 'dontPayNextTurnRent',
        allYourRentsX2OneTurn = 'allYourRentsX2OneTurn',
        freeHouse = 'freeHouse',
        outOfJailCard = 'outOfJailCard',
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
    

    fantasy_type = models.CharField(choices=FantasyType, max_length=10)
    values = models.JSONField(null=True)
    card_cost = models.IntegerField(default=0)

###############################################################################

class Game(models.Model):
    datetime = models.DateTimeField()
    positions = models.JSONField(default=list, blank=True)
    money = models.JSONField(default=list, blank=True)
    turn = models.IntegerField(default=0)
    class GamePhase(models.TextChoices):
        moving = 'moving',
        management = 'management',
        liquidation = 'liquidation',
    phase = models.CharField(choices=GamePhase, max_length=10)
    active_player = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='active_playing')
    # TODO: How to store property group ownership?

class PropertyRelationship(models.Model):
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='in_game')
    owner = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='owned_by')
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='owned_square')

    houses = models.IntegerField(default=-1)#-1: incomplete group, 0: complete group,
                                            #1-4: houses, #5: hotel

class Action(models.Model):
    game = models.ForeignKey('Game', on_delete=models.CASCADE, related_name='in_game')
    player = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='made_by')

class ActionThrowDices(Action):
    dice1 = models.IntegerField(default=0)
    dice2 = models.IntegerField(default=0)
    # One of them is bus
    dice_bus = models.IntegerField(default=0)

class ActionMoveTo(Action):
    # Custom ID or real ID ? Mario opina que custom ID
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='moved_to')

class ActionTakeBus(Action):
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='moved_to')

class ActionBuySquare(Action):
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='bought')

class ActionSellSquare(Action):
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='sold')

class ActionGoToJail(Action):
    pass

class ActionBuild(Action):
    houses = models.IntegerField(default=0)
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='build_square')

class ActionDemolish(Action):
    houses = models.IntegerField(default=0)
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='demolish_square')

class ActionChooseCard(Action):
    chosen_card = models.IntegerField(default=0)

class ActionSurrender(Action):
    pass


#TODO: hablar tradeo completo, los del frontend casi me pegan. tengo miedo.
#TODO: Pensar si hacer esto en una sola clase
class ActionTradeProposalSquareForMoney(Action):
    #TODO: Sell out of jail card
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='square')
    money = models.IntegerField(default=0)

class ActionTradeProposalMoneyForSquare(Action):
    #TODO: Buy out of jail card
    money = models.IntegerField(default=0)
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='square')

class ActionTradeAnswer(Action):
    choose = models.IntegerField(default=0) # yes or no, TODO: boolean?

class ActionMortgageSet(Action):
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='square')

class ActionMortgageUnset(Action):
    square = models.ForeignKey('BaseSquare', on_delete=models.CASCADE, related_name='square')

class ActionPayBail(Action):
    pass



# TODO: Add more Actions
