from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    # TODO: Max length ?
    username = models.CharField(max_length=40, unique=True)
    # TODO: Needed ?
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

class Game(models.Model):
    datetime = models.DateTimeField()
    # TODO: What happens if a user has deleted his account

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

class QueueMetadata(models.Model):
    # Waiting users in the queue
    # TODO: create single row at the start of the application
    users = models.IntegerField(default=0)

class QueuePosition(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    # TODO: implement skill based matchmaking


