import asyncio
import json
from statistics import mode
import sys
import websockets
import argparse
import random
import string

# default
DEFAULT_WS_URL = "ws://localhost:8000"



class GameClient:
    def __init__(self, base_url, session_id=None):
        self.base_url = base_url
        self.session_id = session_id
        self.websocket = None
        self.game_id = None
        self.player_id = None
        self.username = None
        self.game_state = {}
        self.game_started = False
        self.input_queue = asyncio.Queue()

    async def input_worker(self):
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            await self.input_queue.put(line.strip())

    async def get_input(self, prompt):
        print(prompt, end='', flush=True)
        return await self.input_queue.get()

    def get_headers(self):
        headers = {}
        if self.session_id:
            headers["Cookie"] = f"sessionid={self.session_id}"
        return headers
    

    ## Gemini para hacer estas funciones
    async def listen_lobby(self, ws):
        try:
            async for message in ws:
                data = json.loads(message)
                action = data.get("action")

                if action == "chat_message":
                    print(f"\n[CHAT] {data.get('user')}: {data.get('message')}\nLobby> ", end="", flush=True)
                elif action == "room_created":
                    print(f"\n[Lobby] Sala creada. Código: {data.get('room_code')}\nLobby> ", end="", flush=True)
                elif action == "joined":
                    players = data.get('players', [])
                    names = [p['username'] for p in players]
                    print(f"\n[Lobby] {data.get('user')} se unió. Jugadores: {names}\nLobby> ", end="", flush=True)
                elif action == "player_left":
                    print(f"\n[Lobby] {data.get('user_left')} salió.\nLobby> ", end="", flush=True)
                elif action == "settings_changed":
                    bot_lvl = data.get('bot_level')
                    max_p = data.get('target_players')
                    print(f"\n[Lobby] ⚙️ Ajustes cambiados: Nivel Bots -> {bot_lvl} | Max Jugadores -> {max_p}\nLobby> ", end="", flush=True)
                elif action == "ready_status":
                    print(f"\n[Lobby] {data.get('user')} {'✓ listo' if data.get('is_ready') else '✗ no listo'}\nLobby> ", end="", flush=True)
                elif action in ["game_start", "game_started", "match_found"]:
                    self.game_id = data.get("game_id")
                    self.game_started = True
                    print(f"\n[Lobby] ¡Partida {self.game_id} iniciada!")
                    return  # termina listen_task → dispara asyncio.wait
                elif action == "error":
                    print(f"\n[Error] {data.get('message')}\nLobby> ", end="", flush=True)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error escuchando lobby: {e}")

    async def connect_to_private_lobby(self, mode, room_code = None):
        if mode == "create" and not room_code:
            room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        if mode == "join" and not room_code:
            room_code = await self.get_input("\nIntroduce el código de la sala para unirte: ")

        url = f"{self.base_url}/ws/queue/private/{room_code}/"
        print(f"Conectando a: {url}")

        try:
            async with websockets.connect(url, additional_headers=self.get_headers()) as ws:
                self.websocket = ws

                if mode == "create":
                    print(f"\n======================================")
                    print(f"   CÓDIGO DE SALA: {room_code}")
                    print(f"======================================\n")

                print("Comandos disponibles: 'chat <msg>', 'ready', 'notready', 'botlevel <nivel>', 'maxplayers <num>', 'start' (solo host), 'disconnect'")

                listen_task = asyncio.create_task(self.listen_lobby(ws))
                input_task = asyncio.create_task(self.lobby_input(ws))

                done, pending = await asyncio.wait(
                    [listen_task, input_task],
                    return_when=asyncio.FIRST_COMPLETED
                )

                for task in pending:
                    task.cancel()

                # Si listen_task terminó, es porque llegó game_start
                if self.game_started:
                    await ws.close()
                    return self.game_id

        except Exception as e:
            print(f"Error conectando a lobby privado: {e}")

        return None
    
    async def lobby_input(self, ws):
        while True:
            cmd = await self.get_input("Lobby> ")
            cmd = cmd.strip()

            if cmd.startswith("chat "):
                message = cmd[5:]
                await ws.send(json.dumps({
                    "command": "chat_message",
                    "message": message
                }))
            elif cmd == "ready":
                await ws.send(json.dumps({
                    "command": "ready_status",
                    "is_ready": True
                }))
            elif cmd == "notready":
                await ws.send(json.dumps({
                    "command": "ready_status",
                    "is_ready": False
                }))
            elif cmd == "start":
                await ws.send(json.dumps({
                    "command": "start_game"
                }))
            elif cmd.startswith("botlevel "):
                level = cmd.split(" ", 1)[1]
                await ws.send(json.dumps({
                    "command": "update_settings",
                    "bot_level": level
                }))
            elif cmd.startswith("maxplayers "):
                try:
                    target = int(cmd.split(" ", 1)[1])
                    await ws.send(json.dumps({
                        "command": "update_settings",
                        "target_players": target
                    }))
                except ValueError:
                    print("Por favor, introduce un número válido.")
            elif cmd == "disconnect" or cmd == "exit":
                print("Desconectando del lobby...")
                await ws.close()
                break
            else:
                print("Comandos disponibles: 'chat <msg>', 'ready', 'notready', 'botlevel <nivel>', 'maxplayers <num>', 'start' (solo host), 'disconnect'")

    async def connect_to_queue(self):
        url = f"{self.base_url}/ws/queue/public/"
        print(f"Connecting to queue: {url}")
        try:
            async with websockets.connect(url, additional_headers=self.get_headers()) as ws:
                print("Connected to queue. Waiting for a match...")
                async for message in ws:
                    data = json.loads(message)
                    if data.get("action") == "match_found":
                        print(f"Match found! Game ID: {data['game_id']}")
                        await ws.close()
                        return data["game_id"]
                    elif data.get("action") == "error":
                        print(f"Queue Error: {data.get('message')}")
                        return None
        except Exception as e:
            print(f"Failed to connect to queue: {e}")
            return None

    async def play_game(self, game_id: int, player_id: int):
        self.game_id = game_id
        self.player_id = player_id
        url = f"{self.base_url}/ws/game/{game_id}/"
        print(f"Connecting to game: {url}")
        
        try:
            async with websockets.connect(url, additional_headers=self.get_headers()) as ws:
                self.websocket = ws
                
                # Start listener and sender tasks
                listener_task = asyncio.create_task(self.listen())
                sender_task = asyncio.create_task(self.sender())
                
                done, pending = await asyncio.wait(
                    [listener_task, sender_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                for task in pending:
                    task.cancel()
        except Exception as e:
            print(f"Game Connection Error: {e}")
            
    async def listen(self):
        if not self.websocket:
            return
        
        async for message in self.websocket:
            data = json.loads(message)
            action = data.get("action")
            print(action)
            
            if action == "game_state":
                self.game_state = data["game_state"]
                
                # Logic to identify your ID from the game state
                # We can print it clearly here
                print("\n" + "="*30)
                print("--- Current Game State ---")
                
                # If you haven't set your ID yet, this helps you find it
                if not self.player_id:
                    print("HINT: Look at 'money' or 'positions' to find your ID.")
                else:
                    print(f"YOU ARE PLAYER ID: {self.player_id}")
                
                print("="*30)
                print(json.dumps(self.game_state, indent=2))
                is_my_turn = self.game_state.get("active_turn_player") == self.username
                turn_status = "YOUR TURN " if is_my_turn else "⌛ Waiting for opponent..."
                print(f"\n{turn_status}")

                # --- NUEVO: COMPROBACIÓN DE FIN DE PARTIDA O BANCARROTA ---
                phase = self.game_state.get("phase")
                money_dict = self.game_state.get("money", {})

                if phase == "end_game":
                    print("\n🏆 El juego ha terminado. (Simulando redirección a pantalla final...)")
                    await self.websocket.close()
                    sys.exit(0) # Simula cambiar de página
                    
                if self.player_id and str(self.player_id) not in money_dict:
                    print(money_dict)
                    print("\n💀 Has sido eliminado o te has rendido. (Simulando redirección a pantalla final...)")
                    await self.websocket.close()
                    sys.exit(0) # Simula cambiar de página
                # -----------------------------------------------------------
            
            elif action == "init_identity":
                self.player_id = data["player_id"]
                self.username = data["username"]
                print(f"AUTHENTICATED AS: {self.username} (ID: {self.player_id})")
            
            elif action == "game_action":
                print("\n--- Game Action Received ---")
                print(json.dumps(data["data"], indent=2))

            elif action == "game_response":
                print("\n--- Game Response Received ---")
                print(json.dumps(data["data"], indent=2))

                # --- NUEVO: COMPROBACIÓN DE FIN DE PARTIDA O BANCARROTA ---
                # Las acciones (rendirse) y tareas de celery envían el estado en 'data'
                game_data = data.get("data", {})
                phase = game_data.get("phase")
                money_dict = game_data.get("money", {})

                if phase == "end_game":
                    print("\n🏆 El juego ha terminado. (Simulando redirección a pantalla final...)")
                    await self.websocket.close()
                    sys.exit(0) # Simula cambiar de página
                    
                if self.player_id and str(self.player_id) not in money_dict:
                    print("\n💀 Has sido eliminado o te has rendido. (Simulando redirección a pantalla final...)")
                    await self.websocket.close()
                    sys.exit(0) # Simula cambiar de página
                # -----------------------------------------------------------
            elif action == "chat_message":
                print("\n--- Game Message Received ---")
                print(f"[{data.get('user')}]: {data.get('msg')}")

            elif action == "error":
                print(f"\nSERVER ERROR: {data.get('message')}")

            else:
                print(f"\nMessage from server: {message}")

    async def sender(self):
        if not self.websocket:
            return
        if not self.game_id:
            return
        
        while True:
            print("\nAvailable commands: throw, move, buy, build, demolish, next, mortgage, unmortgage, drop, take_tram, skip_tram, choose_card, bid, trade, trade_answer, bail, surrender, exit")
            cmd = await self.get_input("Enter command: ")
            cmd = cmd.strip().lower()

            if cmd == "exit":
                break
            
            try:
                action_data = await self.parse_command(cmd)
                if action_data:
                    await self.websocket.send(json.dumps(action_data))
            except ValueError:
                print("Invalid input: Please enter numbers where expected.")
            except Exception as e:
                print(f"Error parsing command: {e}")

    async def parse_command(self, cmd):
        if not self.player_id:
            self.player_id = await self.get_input("Enter your Player ID (integer): ")
        
        if cmd == "throw":
            return {"type": "ActionThrowDices"}
        elif cmd == "chat":
            return {"type": "ChatMessage", "msg": "Hello world!"}
        elif cmd == "move": 
            sq_id = await self.get_input("Enter Square Custom ID to move to: ")
            return {"type": "ActionMoveTo", "square": int(sq_id)}
        elif cmd == "buy":
            sq_id = await self.get_input("Enter Square Custom ID to buy: ")
            return {"type": "ActionBuySquare", "square": int(sq_id)}
        elif cmd == "next":
            return {"type": "ActionNextPhase"}
        elif cmd == "build":
            sq_id = await self.get_input("Enter Square Custom ID to build on: ")
            houses = await self.get_input("Enter number of houses: ")
            return {"type": "ActionBuild", "square": int(sq_id), "houses": int(houses)}
        elif cmd == "demolish":
            sq_id = await self.get_input("Enter Square Custom ID to demolish: ")
            houses = await self.get_input("Enter number of houses: ")
            return {"type": "ActionDemolish", "square": int(sq_id), "houses": int(houses)}
        elif cmd == "mortgage":
            sq_id = await self.get_input("Enter Square Custom ID to mortgage: ")
            return {"type": "ActionMortgageSet", "square": int(sq_id)}
        elif cmd == "unmortgage":
            sq_id = await self.get_input("Enter Square Custom ID to unmortgage: ")
            return {"type": "ActionMortgageUnset", "square": int(sq_id)}
        elif cmd == "drop":
            sq_id = await self.get_input("Enter Square Custom ID to drop purchase: ")
            return {"type": "ActionDropPurchase", "square": int(sq_id)}
        elif cmd == "take_tram":
            sq_id = await self.get_input("Enter Square Custom ID of destination tram: ")
            return {"type": "ActionTakeTram", "square": int(sq_id)}
        elif cmd == "skip_tram":
            return {"type": "ActionDoNotTakeTram"}
        elif cmd == "choose_card":
            choice = await self.get_input("Use card? (y/n): ")
            return {"type": "ActionChooseCard", "chosen_card": choice.lower() == 'y'}
        elif cmd == "bid":
            amount = await self.get_input("Enter bid amount: ")
            return {"type": "ActionBid", "amount": int(amount)}
        elif cmd == "trade":
            dest_user = await self.get_input("Enter destination User ID: ")
            offered_money = await self.get_input("Offered money: ")
            asked_money = await self.get_input("Asked money: ")
            offered_props = await self.get_input("Offered property relationship IDs (comma separated): ")
            asked_props = await self.get_input("Asked property relationship IDs (comma separated): ")
            
            offered_props_list = [int(x.strip()) for x in offered_props.split(",") if x.strip()]
            asked_props_list = [int(x.strip()) for x in asked_props.split(",") if x.strip()]
            
            return {
                "type": "ActionTradeProposal", 
                "destination_user": int(dest_user),
                "offered_money": int(offered_money),
                "asked_money": int(asked_money),
                "offered_properties": offered_props_list,
                "asked_properties": asked_props_list
            }
        elif cmd == "trade_answer":
            proposal_id = await self.get_input("Enter Proposal ID: ")
            accept = await self.get_input("Accept? (y/n): ")
            return {"type": "ActionTradeAnswer", "proposal": int(proposal_id), "choose": accept.lower() == 'y'}
        elif cmd == "bail":
            return {"type": "ActionPayBail"}
        elif cmd == "surrender": # TODO: surrender has to be done in games.py but i have it here still
            return {"type": "ActionSurrender"}
        else:
            print(f"Unknown command: {cmd}")
            return None
        
    ################ PRIVATE ROOMS  ########################
    

async def main():
    parser = argparse.ArgumentParser(description="Magnate Game CLI Client")
    parser.add_argument("--url", default=DEFAULT_WS_URL, help="Base WebSocket URL (e.g. ws://localhost:8000)")
    parser.add_argument("--session", help="Django sessionid cookie value for authentication")
    parser.add_argument("--game", help="Game ID to connect directly (skips queue)")
    parser.add_argument("--player_id", help="Player ID to connect")
    parser.add_argument("--mode", choices=["public", "create", "join"], default="public")
    parser.add_argument("--room_code", help="Room code for private lobby (only for create/join modes)")

    args = parser.parse_args()


    client = GameClient(args.url, args.session)
    asyncio.create_task(client.input_worker())

    game_id = args.game
    if not game_id:
        if args.mode == "public":
            game_id = await client.connect_to_queue()
        else:
            game_id = await client.connect_to_private_lobby(args.mode, args.room_code)
    
    if game_id:
        await client.play_game(game_id, args.player_id)
    else:
        print("Could not join or create game.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
