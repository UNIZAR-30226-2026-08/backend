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

class QueueMetadata(models.Model):
    # Waiting users in the queue
    # TODO: create single row at the start of the application
    users = models.IntegerField(default=0)

class QueuePosition(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    # TODO: implement skill based matchmaking