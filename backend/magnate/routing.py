from . import consumers
from django.urls import re_path


websocket_urlpatterns = [
    # Route for the queue manager (when users are waiting for a game)
    re_path(r'ws/queue/public/$', consumers.PublicQueueConsumer.as_asgi()),

    # Route for private room lobby management
    re_path(r'ws/queue/private/(?P<room_code>\w+)/$', consumers.PrivateRoomConsumer.as_asgi()),

    # Dynamic route for game rooms
    re_path(r'ws/game/(?P<room_id>\w+)/$', consumers.GameConsumer.as_asgi()),
]