from celery import shared_task
from .models import Game

from .games import GameManager

@shared_task
def auction_callback(game_pk: int):
    print("Ending auction")
    game = Game.objects.get(pk=game_pk)
    GameManager._end_auction(game)

