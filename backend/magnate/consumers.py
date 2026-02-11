import json 
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.db import transaction
from .models import  PublicQueuePosition, PrivateRoom, Game, CustomUser

# TODO: check how to implement DB access form async context -> database_sync_to_async in doc

# TODO: temporarily here, should be in json config file o smth like that

MIN_PRIVATE_GAME_PLAYERS = 2
MAX_PRIVATE_GAME_PLAYERS = 4
NUM_PUBLIC_GAME_PLAYERS = 4


class PublicQueueConsumer(AsyncWebsocketConsumer):
    
    async def connect(self):
        # Triggered when user opens the matchmaking page or "Join Game". Accept connection & auth.
        self.user = self.scope.get('user')
        if self.user is None:
            await self.close(code=4002)
            return
        
        # Security 
        if self.user.is_anonymous:
            await self.close(code=4002)  
            return

        await self.accept()

        await self.add_user_to_queue(self.user, self.channel_name)

        match_result = await self.matchmaking_logic()
        
        
        if match_result:    
            game_id, players_channels = match_result
            # Notify front end to redirect to game room
            for channel in players_channels:
                await self.channel_layer.send(
                    channel,
                    {
                        'type': 'match_found_event', # Method below
                        'game_id': game_id
                    }
                )
        
    async def disconnect(self, close_code):
        # Triggered when user closes tab or finds a match -> manage differences with close code. Remove from DB 
        if close_code ==4001:
            print(f"User {self.user} found a match and is leaving the queue.")
        elif close_code ==4002:
            print(f"Unauthorized user attempted to connect and was rejected.")
            return 
        else:
            print(f"User {self.user} left the queue.")

        await self.remove_user_from_queue(self.user)

    async def receive(self, text_data):
        # Cancel button -> tell front guys
        try:
            data = json.loads(text_data)
            if data.get('action') == 'cancel':
                await self.close(code=4000)
        except json.JSONDecodeError:
            await self.send_error("Datos invalidos.")
            return


# --------------- Handlers -------------------#
    async def match_found_event(self, event):
        await self.send(text_data=json.dumps({
            'action': 'match_found',
            'game_id': event['game_id']
        }))

        await self.close(code=4001)

    async def send_error(self, message):
        await self.send(text_data=json.dumps({
            'action': 'error',
            'message': message
        }))


# ---------------- DB access methods --------------#
    @database_sync_to_async
    def add_user_to_queue(self, user, channel_name):
        existing_position = PublicQueuePosition.objects.filter(user=user).first()
        if existing_position:
            # User already in queue, don't add again
            return None
        
        # Create queue position for the user
        PublicQueuePosition.objects.create(
            user=user,
            channel = channel_name,
            date_time=timezone.now()
            
        )


    @database_sync_to_async
    def remove_user_from_queue(self, user):
        existing_position =  PublicQueuePosition.objects.filter(user=user).first()
        if existing_position:
            existing_position.delete()
        else:
            # User not in queue
            return None


    # TODO: be aware of race conditions -> new users while executing the method
    @database_sync_to_async
    def matchmaking_logic(self):
        # Check if enough players in queue -> create game instance, return game ID and channels of matched players
        # Avoid race conditions
        with transaction.atomic():

            number_of_players = PublicQueuePosition.objects.select_for_update().count()
            
            if number_of_players < NUM_PUBLIC_GAME_PLAYERS: 
                return None
            
            players = list(PublicQueuePosition.objects.select_for_update().order_by('date_time')[:NUM_PUBLIC_GAME_PLAYERS])
            player_channels = [player.channel for player in players]
            users = [player.user for player in players]
            game = Game.objects.create(datetime=timezone.now())

            for user in users:
                if game is None:
                    return None
                
                user.active_game = game
                user.played_games.add(game)
                user.save()
            
            # Remove players from queue
            PublicQueuePosition.objects.filter(pk__in=[p.pk for p in players]).delete()
            
            return (game.pk, player_channels)


            


        



class PrivateRoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Triggered when user opens a new private room or joins an existing one.
        self.user = self.scope.get('user')
        if self.user is None:
            await self.close(code=4002)
            return

        # Security
        if self.user.is_anonymous:
            await self.close(code=4002)  
            return
        
        self.url = self.scope.get('url_route')
        if self.url is None:
            await self.close(code=4002)
            return
        
        self.room_code = self.url.get('kwargs').get('room_code')
        
        self.room_group_name = f"lobby_{self.room_code}"

        can_join, message = await self.check_room(self.room_code)

        # Case of invalid code or full lobby -> reject connection
        if not can_join:
            # Acept to send error message and close connection
            await self.accept()
            await self.send(text_data=json.dumps({'error': message}))
            await self.close(code=4003) 
            return
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()

        players = await self.join_room_group_db(self.room_code, self.user)
        if not players:
            await self.close(code=4003)
            return

        # Notify lobby members of new player and update player list
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'lobby_update',
                'action': 'joined',
                'user': self.user.username,
                'players': players,
                'owner': players[0]['username']
            }
        )

    async def disconnect(self, close_code):
        # Triggered when user leaves the private room lobby.
        # If owner leaves -> change host to the second older player. Else -> just update lobby.
        if close_code == 4002:
            print(f"Unauthorized user attempted to connect and was rejected.")
            return
        
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

        # DB operations -> if needed, rotate host, remove room if empty, etc. Return updated player list and new host if needed.
        room_data = await self.leave_room_and_update_host(self.room_code, self.user)

        if not room_data:
            return
        
        if self.user is None:
            return
        

        if room_data:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'lobby_update',
                    'action': 'player_left',
                    'user_left': self.user.username,
                    'owner': room_data["owner"],
                    'players': room_data['players'] 
                }
            )       

    
    async def receive(self, text_data):
        # Chat messages or 'start_game' command /'ready' status updates.
        if self.user is None:
            return
        
        try:
            data = json.loads(text_data)
            command = data.get('command')

            if not command:
                await self.send_error("Comando invalido.")
                return


            if command == 'start_game':
                is_owner = await self.is_owner(self.user, self.room_code)
                if not is_owner:
                        await self.send_error("Solo el host puede iniciar una partida.")
                        return
                num_players = await self.get_num_players(self.room_code)

                if num_players < MIN_PRIVATE_GAME_PLAYERS:
                    await self.send_error(f"Se necesitan {MIN_PRIVATE_GAME_PLAYERS} jugadores para iniciar la partida.")
                    return
            
                all_ready = await self.check_all_ready(self.room_code)
                if not all_ready:
                    await self.send_error("Todos los jugadores deben estar listos para iniciar la partida.")
                    return
                
                # TODO: use room_id as game_id?? or generate it for public and private games

                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'game_start',
                        'game_id': self.room_code
                    })



            elif command == 'ready_status':
                is_ready = data.get('is_ready')

                # Update in db 
                await self.update_player_ready_status(self.room_code, self.user, is_ready)

                owner = await self.get_room_owner(self.room_code)


                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'lobby_update',
                        'action': 'ready_status',
                        'user': self.user.username,
                        'is_ready': is_ready, 
                        'owner': owner
                    }
                )


            elif command == 'chat_message':
                message = data.get('message')
                await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'chat_event',
                                'user': self.user.username,
                                'message': message
                            }
                        )
        except json.JSONDecodeError:
            await self.send_error("Datos invalidos.")
            return

# -------------------- Handlers  -------------------- #
    async def lobby_update(self, event):
        if self.user is None:
            return
        
        # Send lobby updates to frontend (new player joined, player left)
        if event['action'] == 'joined':
            await self.send(text_data=json.dumps({
                'action': event['action'],
                'user': event['user'],
                'owner': event['owner'],
                'is_owner': (self.user.username == event['owner']),
                'players': event['players']
            }))
        elif event['action'] == 'player_left':
            await self.send(text_data=json.dumps({
                'action': event['action'],
                'user_left': event['user_left'],
                'owner': event['owner'],
                'is_owner': (self.user.username == event['owner']),
                'players': event['players']
            }))
        elif event['action'] == 'ready_status':
            await self.send(text_data=json.dumps({
                'action': event['action'],
                'user': event['user'],
                'is_ready': event['is_ready'], 
                'owner': event['owner'], 
                'is_owner': (self.user.username == event['owner'])
            }))



    async def chat_event(self, event):
        # Send chat messages to frontend
        await self.send(text_data=json.dumps({
            'action': 'chat_message',
            'user': event['user'],
            'message': event['message']
        }))

    async def game_start(self, event):
        await self.send(text_data=json.dumps({
            'action': 'game_start',
            'game_id': event['game_id']
        }))
        await self.close(code=4001)



# ------------------- DB access methos -------------------- #
    @database_sync_to_async
    def check_room(self, room_code):
        if self.user is None:
            return False, None
        
        # Check if room exists and if user can join (not full, not already in, etc). Create if doesn't exist and user is creating it.
        room  = PrivateRoom.objects.filter(room_code=room_code).first()
        
        if not room:
            return False, "Sala no encontrada."
        
        
        
        #Using relation players in users - private room
        current_number_players =  room.players.count()

        if current_number_players >= MAX_PRIVATE_GAME_PLAYERS:
            return False, "Sala llena."
        
        user = CustomUser.objects.get(username=self.user.username)
        current_private_room = user.current_private_room

        if current_private_room== room:
            return False, "Ya estás en esta sala."
        
        return True, None



    @database_sync_to_async
    def join_room_group_db(self, room_code, user):
        current_user = CustomUser.objects.get(username=user.username)
        current_user.current_private_room = PrivateRoom.objects.get(room_code=room_code)
        current_user.ready_to_play = False
        current_user.save()

    @database_sync_to_async
    def leave_room_and_update_host(self, room_code, user):
        room = PrivateRoom.objects.get(room_code=room_code)
        user_from_db = CustomUser.objects.get(username=user.username)

        
        user_from_db.current_private_room = None
        user_from_db.save()

        room.owner = room.players.first()
        room.save()

        return {'owner': room.owner.username, 'players': room.players.all()}



        
        


    @database_sync_to_async
    def update_player_ready_status(self, room_code, user, is_ready):
        user_from_db = CustomUser.objects.get(username=user.username)

        if user_from_db.current_private_room.room_code != room_code:
            return False
    
        user_from_db.ready_to_play = is_ready
        user_from_db.save()


    @database_sync_to_async
    def get_num_players(self, room_code):
        # Return the current number of players in the room
        room = PrivateRoom.objects.get(room_code=room_code)
        if not room:
            return 0
        return room.players.count()


    @database_sync_to_async
    def check_all_ready(self, room_code):
        # Check if all players in the room are ready
        room = PrivateRoom.objects.get(room_code=room_code)
        if not room:
            return False
        
        for player in room.players.all():
            if not player.ready_to_play:
                return False
        
        return True


    @database_sync_to_async
    def is_owner(self, user, room_code):
        # Check if the user is the host of the room
        room = PrivateRoom.objects.get(room_code=room_code)
        if not room:
            return False
        
        return room.owner == user

    @database_sync_to_async
    def get_room_owner(self, room_code):
        # Return the username of the room's owner
        room = PrivateRoom.objects.get(room_code=room_code)
        if not room:
            return False
        
        return room.owner.username


    async def send_error(self, message):
        await self.send(text_data=json.dumps({
            'action': 'error',
            'message': message
        }))




class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Triggered when user joins a specific match ID (game really begins) -> add to Redis room group.
        self.user = self.scope.get('user')
        if self.user is None:
            await self.close(code=4002)
            return
        

        # Security
        if self.user.is_anonymous:
            await self.close(code=4002)
            return
        
        self.url = self.scope.get('url_route')
        if self.url is None:
            await self.close(code=4002)
            return
        self.game_id = self.url.get('kwargs').get('room_id')

        self.game_group_name = f"game_{self.game_id}"

        player_is_in_game = await self.is_player_in_game(self.user, self.game_id)

        if not player_is_in_game:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(
            self.game_group_name,
            self.channel_name
        )

        await self.accept()

        # TODO: Game state includes all info bout the game start. Talk with the boys to dicuss it.
        game_state = await self.get_game_state(self.game_id, self.user)

        await self.send(text_data=json.dumps({
            'action': 'game_state',
            'game_state': game_state
        }))

        

    async def disconnect(self, close_code):
        # Triggered when user leaves game -> notify opponent.
        await self.channel_layer.group_discard(
            self.game_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        # Triggered when user sends a move -> broadcast to room group.
        # Also manages game over conditions triggering disconnects.
        # Manages DB interactions over purchases, rents etc
        pass

# --------------------- Handlers ---------------------- #
    async def game_state(self, event):
        await self.send(text_data=json.dumps({
            'action': 'game_state',
            'game_state': event['game_state']
        }))

# --------------------- DB access methods ---------------------- #
    @database_sync_to_async
    def is_player_in_game(self, user, game_id):
        # Verify if the user is part of the active players for this game
        pass

    @database_sync_to_async
    def get_game_state(self, game_id, user):
        # Retrieve the current state of the game from the database
        pass
