import asyncio
from django.test import TransactionTestCase
from django.core.management import call_command
from django.utils import timezone
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.urls import re_path
from channels.db import database_sync_to_async
from django.test import override_settings
from magnate.models import *
from magnate.consumers import *
from magnate.games import GameManager
import os

# 1. Recreamos tu enrutador (routing) para que los tests sepan a qué Consumer llamar
application = URLRouter([
    re_path(r'ws/queue/public/$', PublicQueueConsumer.as_asgi()), # type: ignore
    re_path(r'ws/queue/private/(?P<room_code>\w+)/$', PrivateRoomConsumer.as_asgi()), # type: ignore
    re_path(r'ws/game/(?P<room_id>\w+)/$', GameConsumer.as_asgi()), # type: ignore
])

@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class ConsumersTest(TransactionTestCase):
    
    def setUp(self):
        os.environ['DJANGO_TESTING'] = '1'
        call_command('init_boards')

    ############################
    ##### PUBLIC MATCHMAKING ####
    ############################
    async def test_public_queue_matchmaking(self):
        communicators = []
        users = []

        # connect all
        for i in range(NUM_PUBLIC_GAME_PLAYERS):
            user = await database_sync_to_async(CustomUser.objects.create)(
                username=f"pub_user_{i}", email=f"pub_{i}@example.com"
            )
            users.append(user)
            
            comm = WebsocketCommunicator(application, "ws/queue/public/")
            comm.scope['user'] = user # type: ignore
            
            connected, _ = await comm.connect()
            self.assertTrue(connected)
            communicators.append(comm)

        # after thar, receive messages
        for comm in communicators:
            response = await comm.receive_json_from(timeout=2.0)
            self.assertEqual(response['action'], 'match_found')
            self.assertIn('game_id', response)

        game_count = await database_sync_to_async(Game.objects.count)()
        self.assertEqual(game_count, 1)

    ######################
    ##### PUBLIC LOBBY #####
    ######################
    async def test_private_lobby_flow(self):
        """
        Player creates a lobby other joins and both ready to start game
        """
        users = []
        for i in range(MIN_PRIVATE_GAME_PLAYERS):
            u = await database_sync_to_async(CustomUser.objects.create)(
                username=f"priv_user_{i}", email=f"priv_{i}@example.com"
            )
            users.append(u)
            
        owner = users[0]
        guest = users[1]

        room_code = "TESTROOM"

        await database_sync_to_async(PrivateRoom.objects.create)(room_code=room_code, owner=owner)

        

        # creation
        comm_owner = WebsocketCommunicator(application, f"ws/queue/private/{room_code}/")
        comm_owner.scope['user'] = owner  # type: ignore
        connected, _ = await comm_owner.connect()
        self.assertTrue(connected)
        
        res_owner = await comm_owner.receive_json_from()
        
        self.assertNotIn('error', res_owner, f"El servidor rechazó al creador: {res_owner.get('error')}")
        
        self.assertEqual(res_owner['action'], 'joined')
        self.assertTrue(res_owner['is_owner']) # he is him

        # conection
        comm_guest = WebsocketCommunicator(application, f"ws/queue/private/{room_code}/")
        comm_guest.scope['user'] = guest  # type: ignore
        connected, _ = await comm_guest.connect()
        self.assertTrue(connected)

        res_guest = await comm_guest.receive_json_from()
        self.assertNotIn('error', res_guest, f"El servidor rechazó al invitado: {res_guest.get('error')}")
        self.assertEqual(res_guest['action'], 'joined')
        
        # new user in
        update_owner = await comm_owner.receive_json_from()
        self.assertEqual(update_owner['action'], 'joined')
        self.assertEqual(update_owner['user'], guest.username)

        # ready
        await comm_owner.send_json_to({'command': 'ready_status', 'is_ready': True})
        await comm_owner.receive_json_from() 
        await comm_guest.receive_json_from() 

        await comm_guest.send_json_to({'command': 'ready_status', 'is_ready': True})
        await comm_owner.receive_json_from()
        await comm_guest.receive_json_from()

        # start
        await comm_owner.send_json_to({'command': 'start_game'})

        # game_id
        start_res_owner = await comm_owner.receive_json_from()
        start_res_guest = await comm_guest.receive_json_from()
        
        self.assertEqual(start_res_owner['action'], 'game_start')
        self.assertEqual(start_res_guest['action'], 'game_start')
        self.assertEqual(start_res_owner['game_id'], room_code)

        await comm_owner.disconnect()
        await comm_guest.disconnect()

    ############################
    ##### GAME CONSUMER TEST ####
    ############################
    async def test_game_consumer_connection(self):
        """
        Accept conexion if in the game
        """
        user = await database_sync_to_async(CustomUser.objects.create)(
            username="p1", email="p1@gmail.com"
        )
        
        # create game
        game = await database_sync_to_async(Game.objects.create)(
            datetime=timezone.now(),
            active_turn_player=user,
            active_phase_player=user,
            phase=GameManager.MANAGEMENT
        )
        # p1 in game
        await database_sync_to_async(game.players.add)(user)
        
        game.money = {str(user.pk): 1500}
        game.positions = {str(user.pk): 0}
        await database_sync_to_async(game.save)()
        
        # front conex
        comm = WebsocketCommunicator(application, f"ws/game/{game.pk}/")
        comm.scope['user'] = user  # type: ignore
        
        connected, _ = await comm.connect()
        self.assertTrue(connected, "El servidor rechazó la conexión al tablero")
        
        res = await comm.receive_json_from()
        self.assertEqual(res['action'], 'game_state')
        self.assertIn('game_state', res)
        self.assertEqual(res['game_state']['phase'], GameManager.MANAGEMENT)
        self.assertEqual(res['game_state']['money'][str(user.pk)], 1500)
        
        await comm.disconnect()

        async def test_game_action_broadcast(self):
            user = await database_sync_to_async(CustomUser.objects.create)(
                username="p_broadcast", email="p_b@gmail.com"
            )
            game = await database_sync_to_async(Game.objects.create)(
                datetime=timezone.now(),
                active_turn_player=user,
                active_phase_player=user,
                phase=GameManager.MANAGEMENT
            )
            await database_sync_to_async(game.players.add)(user)
            game.money = {str(user.pk): 2000}
            game.positions = {str(user.pk): 1} # Some square
            await database_sync_to_async(game.save)()

            comm = WebsocketCommunicator(application, f"ws/game/{game.pk}/")
            comm.scope['user'] = user # type: ignore
            await comm.connect()
            await comm.receive_json_from() # Consume initial state

            # Send a move action (ActionMoveTo)
            square = await database_sync_to_async(BaseSquare.objects.get)(custom_id=2)
            await comm.send_json_to({
                'action': 'game_action',
                'type': 'ActionMoveTo',
                'square': 2
            })

            broadcast = await comm.receive_json_from()
            self.assertEqual(broadcast['action'], 'game_action')
            self.assertEqual(broadcast['data']['type'], 'ActionMoveTo')
            self.assertEqual(broadcast['data']['square'], 2)

            await comm.disconnect()