import json 
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.db import transaction

from magnate.tasks import kick_out_callback
from .models import  PublicQueuePosition, PrivateRoom, Game, CustomUser
from .games import *
from magnate.serializers import GeneralResponseSerializer
from typing import cast

try:
    with open('config.json') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print("Error: The file 'data.json' was not found.")

# TODO: put every global in their correspondent local
MIN_PRIVATE_GAME_PLAYERS = CONFIG["MIN_PRIVATE_GAME_PLAYERS"]
MAX_PRIVATE_GAME_PLAYERS = CONFIG["MAX_PRIVATE_GAME_PLAYERS"]
NUM_PUBLIC_GAME_PLAYERS = CONFIG["NUM_PUBLIC_GAME_PLAYERS"]

class PublicQueueConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for the public matchmaking queue.
 
    Handles automatic matchmaking: players connect, wait until enough players
    are in the queue, and are then redirected to a newly created game.
 
    ---
    ## How to Connect
 
    **Endpoint:** ``ws://<host>/ws/queue/``
 
    **Authentication required:** Yes — the user must be authenticated via session
    or token before connecting. Unauthenticated connections are closed with code ``4002``.
 
    ---
    ## Connection Lifecycle
 
    1. Client opens the WebSocket.
    2. Server adds the user to the matchmaking queue.
    3. If enough players are queued (``NUM_PUBLIC_GAME_PLAYERS``), the server
       automatically creates a game and sends a ``match_found`` event to every
       matched player.
    4. Each matched client receives the ``game_id`` and should navigate to the
       game screen, then connect to ``GameConsumer``.
 
    ---
    ## Messages: Client → Server
 
    ### Cancel Queue
    Voluntarily leave the matchmaking queue.
 
    ```json
    { "action": "cancel" }
    ```
 
    ---
    ## Messages: Server → Client
 
    ### Match Found
    Sent when matchmaking succeeds. The connection is closed with code ``4001``
    immediately after this message.
 
    ```json
    {
        "action": "match_found",
        "game_id": 42
    }
    ```
 
    ### Error
    Sent when an invalid message is received.
 
    ```json
    {
        "action": "error",
        "message": "Datos invalidos."
    }
    ```
 
    ---
    ## Close Codes
 
    | Code | Meaning |
    |------|---------|
    | 4001 | Match found — user was moved to a game. Connect to ``GameConsumer``. |
    | 4002 | Unauthorized — user was not authenticated. |
    | 4000 | User cancelled the queue. |
 
    ---
    ## Example Flow (JavaScript)
 
    ```js
    const socket = new WebSocket("ws://localhost:8000/ws/queue/");
 
    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.action === "match_found") {
            // Navigate to game with data.game_id
            connectToGame(data.game_id);
        }
    };
 
    // To leave the queue manually:
    socket.send(JSON.stringify({ action: "cancel" }));
    ```
    """
    
    QUEUE_GROUP = "public_queue"

    async def connect(self):
        """
        Handles initial WebSocket connection.
        Validates authentication, accepts the connection, adds the user to the 
        public queue group, and triggers matchmaking logic.

        Args:
            None

        Returns:
            None
        """
        scope_user = self.scope.get('user')
        if scope_user is None or getattr(scope_user, 'is_anonymous', True):
            await self.close(code=4002)
            return
            
        self.user = await database_sync_to_async(CustomUser.objects.get)(pk=scope_user.pk)
        await self.accept()

        # join queue
        await self.channel_layer.group_add(self.QUEUE_GROUP, self.channel_name)
        
        await self.add_user_to_queue(self.user, self.channel_name)

        # checking
        match_result = await self.matchmaking_logic()
        
        if match_result:    
            game_id, players_channels = match_result
            for channel in players_channels:
                await self.channel_layer.send(
                    channel,
                    {
                        'type': 'match_found_event',
                        'game_id': game_id, 
                    }
                )
        
    async def disconnect(self, close_code):
        """
        Handles WebSocket disconnection.
        Removes the user from the public queue group and the database queue 
        unless they were disconnected because a match was found.

        Args:
            close_code (int): The WebSocket close code.

        Returns:
            None
        """
        await self.channel_layer.group_discard(self.QUEUE_GROUP, self.channel_name)
        
        if close_code == 4001:
            print(f"User {self.user} found a match and is leaving the queue.")
        elif close_code == 4002:
            return 
        else:
            print(f"User {self.user} left the queue.")
            await self.remove_user_from_queue(self.user)

    async def receive(self, text_data):
        """
        Processes incoming messages from the client.
        Currently only supports the 'cancel' action to leave the queue.

        Args:
            text_data (str): The raw JSON string received.

        Returns:
            None
        """
        try:
            data = json.loads(text_data)
            if data.get('action') == 'cancel':
                await self.close(code=4000)
        except json.JSONDecodeError:
            await self.send_error("Datos invalidos.")

    async def match_found_event(self, event):
        """
        Handler for the 'match_found_event' broadcast.
        Sends the game ID to the client.

        Args:
            event (dict): The event payload containing 'game_id'.

        Returns:
            None
        """
        await self.send(text_data=json.dumps({
            'action': 'match_found',
            'game_id': event['game_id']
        }))

    async def send_error(self, message):
        """
        Utility method to send an error message to the client.

        Args:
            message (str): The error message to be sent.

        Returns:
            None
        """
        await self.send(text_data=json.dumps({
            'action': 'error',
            'message': message
        }))


# ---------------- DB access methods --------------#
    @database_sync_to_async
    def add_user_to_queue(self, user, channel_name):
        """
        Adds a user to the PublicQueuePosition table if they are not already present.

        Args:
            user (CustomUser): The user to add.
            channel_name (str): The specific channel name for this connection.

        Returns:
            None
        """
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
        """
        Removes a user's entry from the PublicQueuePosition table.

        Args:
            user (CustomUser): The user to remove.

        Returns:
            None
        """
        existing_position =  PublicQueuePosition.objects.filter(user=user).first()
        if existing_position:
            existing_position.delete()
        else:
            # User not in queue
            return None


    # TODO: be aware of race conditions -> new users while executing the method
    @database_sync_to_async
    def matchmaking_logic(self):
        """
        Checks if there are enough players in the queue. If so, creates a new game,
        assigns starting positions and funds, randomizes the turn order, and removes 
        the users from the public queue.

        Args:
            None

        Returns:
            tuple | None: A tuple containing the new game's primary key (`game_id`) and 
                          a list of player channel names if a match is successfully made. 
                          Returns `None` if there are not enough players in the queue.
        """
        with transaction.atomic():
            
            players = list(PublicQueuePosition.objects.select_for_update().order_by('date_time')[:NUM_PUBLIC_GAME_PLAYERS])

            if len(players) < NUM_PUBLIC_GAME_PLAYERS: 
                return None
            
            player_channels = [player.channel for player in players]
            users = [player.user for player in players]
            
            # create with compulsory sh -> TODO: change to random
            game = Game.objects.create(
                datetime=timezone.now(),
                active_turn_player=users[0],  
                active_phase_player=users[0],
                phase=GameManager.ROLL_THE_DICES
            )

            # initialize money and positions (see then what the optimal money)
            game.money = {str(u.pk): 1500 for u in users}
            game.positions = {str(u.pk): "000" for u in users}
            

            game.players.set(users)
            game.ordered_players = [u.pk for u in users]
            game.ordered_players = random.sample(game.ordered_players, len(game.ordered_players)) #random order of players


            #task = kick_out_callback.apply_async(args=[game.pk, users[0].pk], countdown=50) #necessary for first turn
            #game.kick_out_task_id = task.id
            game.save()

            
            for user in users:
                user.active_game = game
                user.played_games.add(game)
                user.save()
            
            PublicQueuePosition.objects.filter(pk__in=[p.pk for p in players]).delete()
            
            return (game.pk, player_channels)

class PrivateRoomConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for private game room lobbies.
 
    Manages the pre-game lobby where a host invites friends, players set their
    ready status, and the host starts the game when all players are ready. Supports
    bot-filling up to the configured target player count.
 
    ---
    ## How to Connect
 
    **Endpoint:** ``ws://<host>/ws/room/<room_code>/``
 
    **Authentication required:** Yes. Unauthenticated users are rejected with code ``4002``.
 
    The ``room_code`` must correspond to an existing ``PrivateRoom``. Attempting to
    join a non-existent or full room will result in an error message followed by
    close code ``4003``.
 
    ---
    ## Connection Lifecycle
 
    1. Client opens the WebSocket with a valid ``room_code``.
    2. Server validates room existence, capacity, and that the user is not already in
       the room.
    3. On success, the server broadcasts a ``joined`` lobby update to all members.
    4. Players toggle ready status. The host can change settings (bot level, target
       player count).
    5. When all players are ready, the host sends ``start_game``.
    6. Server creates the game (filling remaining slots with bots if needed) and
       broadcasts a ``game_start`` event to everyone.
    7. Each client receives the ``game_id`` and connects to ``GameConsumer``.
 
    ---
    ## Messages: Client → Server
 
    All messages are JSON objects with a ``command`` field.
 
    ### Toggle Ready Status
    ```json
    { "command": "ready_status", "is_ready": true }
    ```
 
    ### Start Game *(host only)*
    Requires all players to be ready and at least ``MIN_PRIVATE_GAME_PLAYERS`` in
    the room. Bots are added to reach ``target_players`` if needed.
    ```json
    { "command": "start_game" }
    ```
 
    ### Send Chat Message
    ```json
    { "command": "chat_message", "message": "Hello!" }
    ```
 
    ### Update Room Settings *(host only)*
    Change the target number of players and/or the bot difficulty level.
    ```json
    {
        "command": "update_settings",
        "bot_level": "easy",
        "target_players": 4
    }
    ```
 
    ---
    ## Messages: Server → Client
 
    ### Player Joined
    Broadcast to all members when someone connects.
    ```json
    {
        "action": "joined",
        "user": "alice",
        "owner": "alice",
        "is_owner": true,
        "players": [
            { "username": "alice", "ready_to_play": false }
        ]
    }
    ```
 
    ### Player Left
    Broadcast to remaining members when someone disconnects. ``owner`` may change
    if the previous owner left (host migration).
    ```json
    {
        "action": "player_left",
        "user_left": "bob",
        "owner": "alice",
        "is_owner": true,
        "players": [
            { "username": "alice", "ready_to_play": false }
        ]
    }
    ```
 
    ### Ready Status Update
    Broadcast to all members when any player changes their ready status.
    ```json
    {
        "action": "ready_status",
        "user": "bob",
        "is_ready": true,
        "owner": "alice",
        "is_owner": false
    }
    ```
 
    ### Settings Changed
    Broadcast to all members when the host updates room settings.
    ```json
    {
        "action": "settings_changed",
        "bot_level": "hard",
        "target_players": 4
    }
    ```
 
    ### Game Start
    Broadcast to all members when the game has been created. The connection is
    closed with code ``4001`` immediately after.
    ```json
    {
        "action": "game_start",
        "game_id": 42
    }
    ```
 
    ### Chat Message
    Broadcast to all members.
    ```json
    {
        "action": "chat_message",
        "user": "alice",
        "message": "Good luck!"
    }
    ```
 
    ### Error
    Sent only to the client that triggered the error.
    ```json
    {
        "action": "error",
        "message": "Solo el host puede iniciar una partida."
    }
    ```
 
    ---
    ## Close Codes
 
    | Code | Meaning |
    |------|---------|
    | 4001 | Game started — connect to ``GameConsumer`` with the received ``game_id``. |
    | 4002 | Unauthorized. |
    | 4003 | Room not found, full, or user already in room. |
 
    ---
    ## Notes
 
    - ``is_owner`` in lobby events is computed per-recipient: ``true`` only for the
      current room host.
    - If the host disconnects, ownership is automatically transferred to the next
      oldest player.
    - If the last player leaves, the room is deleted.
    - Bots are created at game start to fill slots up to ``target_players``; they
      are not visible in the lobby.
 
    ---
    ## Example Flow (JavaScript)
 
    ```js
    const socket = new WebSocket("ws://localhost:8000/ws/room/ABC123/");
 
    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
 
        switch (data.action) {
            case "joined":
            case "player_left":
                updatePlayerList(data.players, data.owner);
                break;
            case "ready_status":
                updateReadyIndicator(data.user, data.is_ready);
                break;
            case "settings_changed":
                updateSettings(data.bot_level, data.target_players);
                break;
            case "game_start":
                connectToGame(data.game_id);
                break;
            case "error":
                showError(data.message);
                break;
        }
    };
 
    // Mark yourself as ready:
    socket.send(JSON.stringify({ command: "ready_status", is_ready: true }));
 
    // Host starts the game:
    socket.send(JSON.stringify({ command: "start_game" }));
    ```
    """
    async def connect(self):
        """
        Handles initial WebSocket connection to a private room lobby.
        Validates authentication and room code, accepts the connection, and 
        notifies the group of the new player.

        Args:
            None

        Returns:
            None
        """
        # Triggered when user opens a new private room or joins an existing one.
        scope_user = self.scope.get('user')
        if scope_user is None or getattr(scope_user, 'is_anonymous', True):
            await self.close(code=4002)
            return
            
        self.user = await database_sync_to_async(CustomUser.objects.get)(pk=scope_user.pk)
        
        self.url = self.scope.get('url_route')
        if self.url is None:
            await self.close(code=4002)
            return
        
        self.room_code = self.url.get('kwargs').get('room_code')
        
        self.room_group_name = f"lobby_{self.room_code}"


        was_created = await self.get_or_create_room_db(self.room_code, self.user)

        await self.accept()

        if was_created:
            await self.send(text_data=json.dumps({
                'action': 'room_created',
                'room_code': self.room_code
            }))

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
        """
        Handles WebSocket disconnection from the private lobby.
        Removes the user from the group and handles host migration or room deletion.

        Args:
            close_code (int): The WebSocket close code.

        Returns:
            None
        """
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
        """
        Processes incoming messages from lobby clients (chat, ready status, start game, settings).

        Args:
            text_data (str): The raw JSON string received.

        Returns:
            None
        """
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
                
                game_pk = await self.create_private_game(self.room_code)

                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'game_start',
                        'game_id': game_pk
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

            elif command == 'update_settings': # owner changes target users and bot level
                is_owner = await self.is_owner(self.user, self.room_code)
                if not is_owner:
                    await self.send_error("Solo el host puede cambiar la configuración.")
                    return

                bot_level = data.get('bot_level')
                target_players = data.get('target_players')

                await self.update_room_settings(self.room_code, bot_level, target_players)

                # Avisar a todos los de la sala del cambio
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'lobby_update',
                        'action': 'settings_changed',
                        'bot_level': bot_level,
                        'target_players': target_players
                    }
                )

        except json.JSONDecodeError:
            await self.send_error("Datos invalidos.")
            return

# -------------------- Handlers  -------------------- #
    async def lobby_update(self, event):
        """
        Handler for lobby status broadcasts (joined, left, ready, settings).
        Forwards the update to the connected WebSocket client.

        Args:
            event (dict): The event dictionary containing the action and relevant data.

        Returns:
            None
        """
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
        elif event['action'] == 'settings_changed':
            await self.send(text_data=json.dumps({
                'action': event['action'],
                'bot_level': event['bot_level'],
                'target_players': event['target_players']
            }))

    @database_sync_to_async
    def get_or_create_room_db(self, room_code, user):
        """
        Retrieves an existing room or creates a new one with the given code and owner.

        Args:
            room_code (str): The unique room identifier.
            user (CustomUser): The user creating or retrieving the room.

        Returns:
            bool: True if a new room was created, False if it already existed.
        """
        room = PrivateRoom.objects.filter(room_code=room_code).first()
        if not room:
            PrivateRoom.objects.create(
                room_code=room_code,
                owner=user
            )
            return True 
        return False

    
    @database_sync_to_async
    def update_room_settings(self, room_code, bot_level, target_players):
        """
        Updates the target player count and bot difficulty level for a room.

        Args:
            room_code (str): The room identifier.
            bot_level (str): The difficulty level for bots.
            target_players (int): The desired total number of players.

        Returns:
            None
        """
        room = PrivateRoom.objects.get(room_code=room_code)
        if bot_level: 
            room.bot_level = bot_level
        if target_players: 
            room.target_players = target_players
        room.save()

    @database_sync_to_async
    def create_private_game(self, room_code):
        """
        Creates a game from a private room, filling empty slots with Bots according 
        to the configured difficulty. Randomizes player order, initializes statistics, 
        and deletes the lobby.

        Args:
            room_code (str): The unique string identifier for the private room.

        Returns:
            int: The primary key (`pk`) of the newly created Game instance.
        """
        import random
        from django.utils import timezone
        from .models import PrivateRoom, Game, CustomUser
        from .games import GameManager
       

        room = PrivateRoom.objects.get(room_code=room_code)
        real_users = list(room.players.all())
        users = real_users.copy()

        # fill with bots
        huecos = room.target_players - len(real_users)
        for i in range(huecos):
            bot_username = f"Bot_{room_code}_{i+1}" 
            bot_user, _ = Bot.objects.get_or_create(
                username=bot_username
            )

            bot_user.bot_level = room.bot_level
            bot_user.save()
            
            users.append(bot_user)

        game = Game.objects.create(
            datetime=timezone.now(),
            active_turn_player=users[0], # Se ajusta abajo
            active_phase_player=users[0],
            phase=GameManager.ROLL_THE_DICES
        )

        game.money = {str(u.pk): 1500 for u in users}
        game.positions = {str(u.pk): "000" for u in users}

        game.players.set(users)
        ordered_pks = [u.pk for u in users]
        random.shuffle(ordered_pks)
        game.ordered_players = ordered_pks

        first_player = CustomUser.objects.get(pk=ordered_pks[0])
        game.active_turn_player = first_player
        game.active_phase_player = first_player

        for user in users:
            user.active_game = game
            user.played_games.add(game)
            user.current_private_room = None 
            
            user.save()
            PlayerGameStatistic.objects.get_or_create(user=user, game=game)
            
        room.delete()

        #GameManager._set_kick_out_timer(game, first_player)
        
        game.save()

        

        return game.pk



    async def chat_event(self, event):
        """
        Handler for chat messages. Sends the message content to the client.

        Args:
            event (dict): The event dictionary containing 'user' and 'message'.

        Returns:
            None
        """
        # Send chat messages to frontend
        await self.send(text_data=json.dumps({
            'action': 'chat_message',
            'user': event['user'],
            'message': event['message']
        }))

    async def game_start(self, event):
        """
        Handler for the 'game_start' event. Notifies the client that the game has begun.

        Args:
            event (dict): The event dictionary containing 'game_id'.

        Returns:
            None
        """
        await self.send(text_data=json.dumps({
            'action': 'game_start',
            'game_id': event['game_id']
        }))



# ------------------- DB access methos -------------------- #
    @database_sync_to_async
    def check_room(self, room_code):
        """
        Validates if a user can join a specific room.
        Checks room existence, capacity, and if the user is already a member.

        Args:
            room_code (str): The room identifier.

        Returns:
            tuple[bool, str | None]: A tuple (can_join, error_message).
        """
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
        """
        Updates the database to reflect a user joining a private room.

        Args:
            room_code (str): The room identifier.
            user (CustomUser): The user joining.

        Returns:
            list[dict]: A list of dictionary objects representing members of the room.
        """
        current_user = CustomUser.objects.get(username=user.username)
        room = PrivateRoom.objects.get(room_code=room_code)
        
        current_user.current_private_room = PrivateRoom.objects.get(room_code=room_code)
        current_user.ready_to_play = False
        current_user.save()

        return list(room.players.values('username', 'ready_to_play'))

    @database_sync_to_async
    def leave_room_and_update_host(self, room_code, user):
        """
        Updates the database when a user leaves a room.
        Handles host migration to the next available player or room deletion if empty.

        Args:
            room_code (str): The room identifier.
            user (CustomUser): The user leaving.

        Returns:
            dict | None: A dictionary with the new owner and player list, or None if the room was deleted.
        """
        room = PrivateRoom.objects.filter(room_code=room_code).first()
        if not room:
            return None
        user_from_db = CustomUser.objects.get(username=user.username)
        
        user_from_db.current_private_room = None
        user_from_db.save()

        new_owner = room.players.exclude(pk=user_from_db.pk).first()

        # if no one left, delete
        if new_owner is None:
            room.delete()
            return None

        room.owner = new_owner
        room.save()

        return {
            'owner': room.owner.username,
            'players': list(room.players.values('username', 'ready_to_play'))
        }

    @database_sync_to_async
    def update_player_ready_status(self, room_code, user, is_ready):
        """
        Updates the ready status of a user within a room.

        Args:
            room_code (str): The room identifier.
            user (CustomUser): The user updating their status.
            is_ready (bool): The new ready status.

        Returns:
            bool | None: True if updated, False if code mismatch, None if not in a room.
        """
        user_from_db = CustomUser.objects.get(username=user.username)

        if user_from_db.current_private_room is None:
            return None

        if user_from_db.current_private_room.room_code != room_code:
            return False
    
        user_from_db.ready_to_play = is_ready
        user_from_db.save()

    @database_sync_to_async
    def get_num_players(self, room_code):
        """
        Retrieves the current number of players in a private room.

        Args:
            room_code (str): The room identifier.

        Returns:
            int: The player count.
        """
        # Return the current number of players in the room
        room = PrivateRoom.objects.get(room_code=room_code)
        if not room:
            return 0
        return room.players.count()

    @database_sync_to_async
    def check_all_ready(self, room_code):
        """
        Checks if all players in a private room have set their status to ready.

        Args:
            room_code (str): The room identifier.

        Returns:
            bool: True if everyone is ready, False otherwise.
        """
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
        """
        Verifies if a specific user is the host (owner) of a private room.

        Args:
            user (CustomUser): The user to check.
            room_code (str): The room identifier.

        Returns:
            bool: True if the user is the owner, False otherwise.
        """
        # Check if the user is the host of the room
        room = PrivateRoom.objects.get(room_code=room_code)
        if not room:
            return False
        
        return room.owner == user

    @database_sync_to_async
    def get_room_owner(self, room_code):
        """
        Retrieves the username of the room's current owner.

        Args:
            room_code (str): The room identifier.

        Returns:
            str | None: The username of the owner, or None if not found.
        """
        # Return the username of the room's owner
        room = PrivateRoom.objects.get(room_code=room_code)
        if not room:
            return False
        
        if room.owner is None:
            return None
        
        return room.owner.username

    async def send_error(self, message):
        """
        Sends an error message to the client.

        Args:
            message (str): The error description.

        Returns:
            None
        """
        await self.send(text_data=json.dumps({
            'action': 'error',
            'message': message
        }))

@database_sync_to_async
def validate_and_save_action(data):
    """
    Validates the incoming action data using GeneralActionSerializer and saves the instance.

    Args:
        data (dict): The raw action data.

    Returns:
        tuple[Action | None, dict | None]: A tuple (action_instance, error_dict).
    """
    serializer = GeneralActionSerializer(data=data)
    
    if not serializer.is_valid():
        return None, serializer.errors
    
    action_instance = serializer.save() 
    return action_instance, None

class GameConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for an active game session.
 
    This is the main gameplay socket. Once connected, the client receives the
    current game state, can send player actions, and receives broadcasts of
    all actions and their resolved outcomes in real time.
 
    ---
    ## How to Connect
 
    **Endpoint:** ``ws://<host>/ws/game/<game_id>/``
 
    **Authentication required:** Yes. Unauthenticated connections are closed with code ``4002``.
 
    The ``game_id`` must match an existing ``Game`` that the authenticated user
    belongs to. If the user is not a participant, the connection is rejected with
    code ``4003``.
 
    ---
    ## Connection Lifecycle
 
    1. Client opens the WebSocket with the ``game_id`` received from ``PublicQueueConsumer``
       or ``PrivateRoomConsumer``.
    2. Server validates that the user is a participant.
    3. On success, the server immediately sends a ``game_state`` event to the
       connecting client with the full current game state.
    4. The client sends ``Action`` messages as the game progresses.
    5. Each valid action is broadcast as a ``game_action`` event, followed by a
       ``game_response`` event with the resolved outcome.
    6. All players in the game receive both broadcasts.
 
    ---
    ## Messages: Client → Server
 
    ### Game Action
    Sends a player action for the current game phase. The ``type`` field must
    correspond to a valid ``Action`` type for the active phase. All other fields
    are action-specific.
 
    ```json
    {
        "type": "SomeActionType",
        "...": "action-specific fields"
    }
    ```
 
    The ``game`` and ``player`` fields are injected server-side — do **not** include
    them manually.
 
    ### Chat Message
    ```json
    {
        "type": "ChatMessage",
        "msg": "Hello everyone!"
    }
    ```
 
    ---
    ## Messages: Server → Client
 
    ### Game State
    Sent immediately on connection. Contains the full serialized game state.
 
    ```json
    {
        "event_type": "game_state",
        "game_state": { "...": "full GameStatusSerializer output" }
    }
    ```
 
    ### Game Action
    Broadcast to all players when a valid action is received. Contains the raw
    action data as sent by the acting player.
 
    ```json
    {
        "event_type": "game_action",
        "data": { "type": "SomeActionType", "game": 42, "player": 7, "...": "..." }
    }
    ```
 
    ### Game Response
    Broadcast to all players immediately after ``game_action``. Contains the
    resolved outcome of the action as serialized by ``GeneralResponseSerializer``.
 
    ```json
    {
        "event_type": "game_response",
        "data": { "...": "GeneralResponseSerializer output" }
    }
    ```
 
    ### Chat Message
    Broadcast to all players in the game.
 
    ```json
    {
        "event_type": "chat_message",
        "game": 42,
        "user": "alice",
        "msg": "Hello everyone!"
    }
    ```
 
    ### Error
    Sent only to the client that triggered the error (invalid action, wrong phase,
    etc.).
 
    ```json
    {
        "event_type": "error",
        "message": "Acción no válida en la fase actual."
    }
    ```
 
    ---
    ## Close Codes
 
    | Code | Meaning |
    |------|---------|
    | 4002 | Unauthorized or missing route kwargs. |
    | 4003 | User is not a participant in this game. |
 
    ---
    ## Important Notes
 
    - Every valid action triggers **two** consecutive broadcasts: ``game_action``
      (what was sent) and ``game_response`` (the outcome). Always handle both.
    - Invalid actions (wrong phase, serialization errors, game logic errors) produce
      an ``error`` event and are **not** broadcast to other players.
    - The game state snapshot sent on connect may be slightly stale by the time
      the first ``game_action`` arrives; prefer the response stream for live updates.
 
    ---
    ## Example Flow (JavaScript)
 
    ```js
    const socket = new WebSocket(`ws://localhost:8000/ws/game/${gameId}/`);
 
    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
 
        switch (data.event_type) {
            case "game_state":
                initializeBoard(data.game_state);
                break;
            case "game_action":
                highlightAction(data.data);
                break;
            case "game_response":
                applyOutcome(data.data);
                break;
            case "chat_message":
                appendChat(data.user, data.msg);
                break;
            case "error":
                showError(data.message);
                break;
        }
    };
 
    // Send an action:
    socket.send(JSON.stringify({ type: "RollDice" }));
 
    // Send a chat message:
    socket.send(JSON.stringify({ type: "ChatMessage", msg: "Good luck!" }));
    ```
    """
    async def connect(self):
        """
        Handles initial WebSocket connection to an active game.
        Validates participant status, accepts connection, and sends the initial 
        full game state.

        Args:
            None

        Returns:
            None
        """
        # Triggered when user joins a specific match ID (game really begins) -> add to Redis room group.
        scope_user = self.scope.get('user')
        if scope_user is None or getattr(scope_user, 'is_anonymous', True):
            await self.close(code=4002)
            return
            
        # Extraemos la instancia real de CustomUser de la BD
        self.user = await database_sync_to_async(CustomUser.objects.get)(pk=scope_user.pk)
        
        self.url = self.scope.get('url_route')
        if self.url is None:
            await self.close(code=4002)
            return
        
        kwargs = self.url.get('kwargs')
        if not kwargs or 'room_id' not in kwargs:
            await self.close(code=4002)
            return

        self.game_id = int(kwargs['room_id'])

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

        game = await self.get_game()
        game_state = await database_sync_to_async(
                lambda: GameStatusSerializer(game).data)()

        await self.channel_layer.send(
            self.channel_name,
            {
                'type': 'game_state',
                'game_state': game_state
            }
        )

    async def disconnect(self, close_code):
        """
        Handles WebSocket disconnection from the game session.

        Args:
            close_code (int): The WebSocket close code.

        Returns:
            None
        """
        # Triggered when user leaves game -> notify opponent.
        await self.channel_layer.group_discard(
            self.game_group_name,
            self.channel_name
        )

   
    async def receive(self, text_data):
        """
        Processes WebSocket messages in the active game.
        Differentiates between chat messages and game actions. Deserializes actions,
        processes them via GameManager, and broadcasts the events (action sent and 
        outcome) to all clients in the group. Deletes the action from the DB if a 
        logic error occurs.

        Args:
            text_data (str): The raw JSON string received from the WebSocket client.

        Returns:
            None

        Raises:
            Sends an error via WebSocket (does not explicitly raise a Python exception) 
            if the game is not found, data is invalid, or if GameManager throws a 
            MaliciousUserInput, GameLogicError, or GameDesignError.
        """
       
        game = await self.get_game()
        if game is None:
            await self.send_error("Game not found")
            return
        
        data = json.loads(text_data)

        if data.get('type') == 'ChatMessage':
            message = data.get('msg')
            if message:
                await self.channel_layer.group_send(
                    self.game_group_name,
                    {
                        'type': 'chat_message',
                        'game': self.game_id,
                        'user': self.user.username,
                        'msg': message
                    }
                )
            return

        data['game'] = self.game_id
        data['player'] = self.user.pk

        action, errors = await validate_and_save_action(data)

        if errors or action is None:
            await self.send_error(f"Invalid data: {errors}")
            return
        
        action = cast(Action, action)

        try:
            response = await GameManager.process_action(game, self.user, action)

            if response is None:
                await database_sync_to_async(action.delete)() # Limpiamos BD
                await self.send_error("Acción no válida en la fase actual.")
                return

            # Broadcast action if not an ActionBid
            # TODO: Expand to a list if necessary
            if not isinstance(action, ActionBid):
                await self.channel_layer.group_send(
                    self.game_group_name,
                    {
                        'type': 'game_action_event',
                        'data': data
                    }
                )
            
            response_data = await database_sync_to_async(lambda: GeneralResponseSerializer(response).data)()
            
            await self.channel_layer.group_send(
                self.game_group_name,
                {
                    'type': 'game_response_event',
                    'data': response_data
                }
            )

        except (MaliciousUserInput, GameLogicError, GameDesignError, Exception) as e:
            await database_sync_to_async(action.delete)()
            await self.send_error(f"{e}")

# --------------------- Handlers ---------------------- #

    async def game_state(self, event):
        """
        Handler for sending the game state to the client.

        Args:
            event (dict): The event dictionary containing 'game_state'.

        Returns:
            None
        """
        await self.send(text_data=json.dumps({
            'event_type': 'game_state',
            'game_state': event['game_state']
        }))

    async def game_action_event(self, event):
        """
        Handler for broadcasting a game action to the client.

        Args:
            event (dict): The event dictionary containing 'data' (raw action).

        Returns:
            None
        """
        await self.send(text_data=json.dumps({
            'event_type': 'game_action',
            'data': event['data']
        }))

    async def game_response_event(self, event):
        """
        Handler for broadcasting a game response (outcome) to the client.

        Args:
            event (dict): The event dictionary containing 'data' (serialized outcome).

        Returns:
            None
        """
        await self.send(text_data=json.dumps({
            'event_type': 'game_response',
            'data': event['data']
        }))

    async def chat_message(self, event):
        """
        Handler for game chat messages.

        Args:
            event (dict): The event dictionary containing 'game', 'user', and 'msg'.

        Returns:
            None
        """
        await self.send(text_data=json.dumps({
            'event_type': 'chat_message',
            'game': event['game'],
            'user': event['user'],
            'msg': event['msg']
        }))

    async def send_error(self, message):
        """
        Sends an error message to the client.

        Args:
            message (str): The error description.

        Returns:
            None
        """
        await self.send(text_data=json.dumps({
            'event_type': 'error',
            'message': message
        }))


#----------------------- DB access --------------------#
    @database_sync_to_async
    def is_player_in_game(self, user, game_id):
        """
        Verifies if a specific user is a participant in a given game.

        Args:
            user (CustomUser): The user to check.
            game_id (int): The primary key of the game.

        Returns:
            bool: True if the user is a participant, False otherwise.
        """
        try:
            game = Game.objects.get(pk=game_id)
            return game.players.filter(pk=user.pk).exists()
        except Game.DoesNotExist:
            return False

    @database_sync_to_async
    def get_game(self):
        """
        Retrieves the current game instance from the database.

        Args:
            None

        Returns:
            Game | None: The Game instance or None if not found.
        """
        try:
            return Game.objects.get(pk=self.game_id)
        except Game.DoesNotExist:
            return None
