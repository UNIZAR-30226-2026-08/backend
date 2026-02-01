import json 
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import QueueMetadata, QueuePosition

# TODO: check how to implement DB access form async context -> database_sync_to_async in doc

class QueueConsumer(AsyncWebsocketConsumer):
    
    async def connect(self):
        # Triggered when user opens the matchmaking page. Accept connection & auth.
        pass

    async def disconnect(self, close_code):
        # Triggered when user closes tab or finds a match. Remove from DB 
        pass

    async def receive(self, text_data):
        # Triggered when client sends 'join_queue' command or polls for status.
        pass


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Triggered when user joins a specific match ID -> add to Redis room group.
        pass

    async def disconnect(self, close_code):
        # Triggered when user leaves game -> notify opponent.
        pass
    
    async def receive(self, text_data):
        # Triggered when user sends a move -> broadcast to room group.
        pass