import json 
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import QueueMetadata, QueuePosition

# TODO: check how to implement DB access form async context -> database_sync_to_async in doc

class PublicQueueConsumer(AsyncWebsocketConsumer):
    
    async def connect(self):
        # Triggered when user opens the matchmaking page or "Join Game". Accept connection & auth.
        pass

    async def disconnect(self, close_code):
        # Triggered when user closes tab or finds a match -> manage differences. Remove from DB 
        pass

    async def receive(self, text_data):
        # Not used for now
        pass


class PrivateRoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Triggered when user opens a new private room or joins an existing one.
        pass

    async def disconnect(self, close_code):
        # Triggered when user leaves the private room lobby.
        pass
    
    async def receive(self, text_data):
        # Chat messages or 'start_game' command /'ready' status updates.
        pass


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Triggered when user joins a specific match ID (game really begins) -> add to Redis room group.
        pass

    async def disconnect(self, close_code):
        # Triggered when user leaves game -> notify opponent.
        pass
    
    async def receive(self, text_data):
        # Triggered when user sends a move -> broadcast to room group.
        # Also manages game over conditions triggering disconnects.
        pass