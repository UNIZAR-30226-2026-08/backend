from . import consumers
from django.urls import re_path


websocket_urlpatterns = [
    # Route for the queue manager (when users are waiting for a game)
    re_path(r'ws/queue_manager/$', consumers.QueueConsumer.as_asgi()),

    # Dynamic route for game rooms
    re_path(r'ws/game/(?P<room_id>\w+)/$', consumers.GameConsumer.as_asgi()),
]