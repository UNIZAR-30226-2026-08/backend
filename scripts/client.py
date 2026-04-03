import asyncio
import json
import sys
import websockets
import argparse

# default
DEFAULT_WS_URL = "ws://localhost:8000"

async def get_input(prompt):
    return await asyncio.get_event_loop().run_in_executor(None, input, prompt)

class GameClient:
    def __init__(self, base_url, session_id=None):
        self.base_url = base_url
        self.session_id = session_id
        self.websocket = None
        self.game_id = None
        self.player_id = None
        self.username = None
        self.game_state = {}

    def get_headers(self):
        headers = {}
        if self.session_id:
            headers["Cookie"] = f"sessionid={self.session_id}"
        return headers

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
            print("\nAvailable commands: throw, move, buy, sell, build, demolish, next, mortgage, unmortgage, drop, take_tram, skip_tram, choose_card, bid, trade, trade_answer, bail, surrender, exit")
            cmd = await get_input("Enter command: ")
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
            self.player_id = await get_input("Enter your Player ID (integer): ")
        
        if cmd == "throw":
            return {"type": "ActionThrowDices"}
        elif cmd == "move": 
            sq_id = await get_input("Enter Square Custom ID to move to: ")
            return {"type": "ActionMoveTo", "square": int(sq_id)}
        elif cmd == "buy":
            sq_id = await get_input("Enter Square Custom ID to buy: ")
            return {"type": "ActionBuySquare", "square": int(sq_id)}
        elif cmd == "sell": 
            sq_id = await get_input("Enter Square Custom ID to sell: ")
            return {"type": "ActionSellSquare", "square": int(sq_id)}
        elif cmd == "next":
            return {"type": "ActionNextPhase"}
        elif cmd == "build":
            sq_id = await get_input("Enter Square Custom ID to build on: ")
            houses = await get_input("Enter number of houses: ")
            return {"type": "ActionBuild", "square": int(sq_id), "houses": int(houses)}
        elif cmd == "demolish":
            sq_id = await get_input("Enter Square Custom ID to demolish: ")
            houses = await get_input("Enter number of houses: ")
            return {"type": "ActionDemolish", "square": int(sq_id), "houses": int(houses)}
        elif cmd == "mortgage":
            sq_id = await get_input("Enter Square Custom ID to mortgage: ")
            return {"type": "ActionMortgageSet", "square": int(sq_id)}
        elif cmd == "unmortgage":
            sq_id = await get_input("Enter Square Custom ID to unmortgage: ")
            return {"type": "ActionMortgageUnset", "square": int(sq_id)}
        elif cmd == "drop":
            sq_id = await get_input("Enter Square Custom ID to drop purchase: ")
            return {"type": "ActionDropPurchase", "square": int(sq_id)}
        elif cmd == "take_tram":
            sq_id = await get_input("Enter Square Custom ID of destination tram: ")
            return {"type": "ActionTakeTram", "square": int(sq_id)}
        elif cmd == "skip_tram":
            return {"type": "ActionDoNotTakeTram"}
        elif cmd == "choose_card":
            choice = await get_input("Use card? (y/n): ")
            return {"type": "ActionChooseCard", "chosen_card": choice.lower() == 'y'}
        elif cmd == "bid":
            auction_id = await get_input("Enter Auction ID: ")
            amount = await get_input("Enter bid amount: ")
            return {"type": "ActionBid", "auction": int(auction_id), "amount": int(amount)}
        elif cmd == "trade":
            dest_user = await get_input("Enter destination User ID: ")
            offered_money = await get_input("Offered money: ")
            asked_money = await get_input("Asked money: ")
            offered_props = await get_input("Offered property relationship IDs (comma separated): ")
            asked_props = await get_input("Asked property relationship IDs (comma separated): ")
            
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
            proposal_id = await get_input("Enter Proposal ID: ")
            accept = await get_input("Accept? (y/n): ")
            return {"type": "ActionTradeAnswer", "proposal": int(proposal_id), "choose": accept.lower() == 'y'}
        elif cmd == "bail":
            return {"type": "ActionPayBail"}
        elif cmd == "surrender": # TODO: surrender has to be done in games.py but i have it here still
            return {"type": "ActionSurrender"}
        else:
            print(f"Unknown command: {cmd}")
            return None

async def main():
    parser = argparse.ArgumentParser(description="Magnate Game CLI Client")
    parser.add_argument("--url", default=DEFAULT_WS_URL, help="Base WebSocket URL (e.g. ws://localhost:8000)")
    parser.add_argument("--session", help="Django sessionid cookie value for authentication")
    parser.add_argument("--game", help="Game ID to connect directly (skips queue)")
    parser.add_argument("--player_id", help="Player ID to connect")

    args = parser.parse_args()

    client = GameClient(args.url, args.session)

    game_id = args.game
    if not game_id:
        game_id = await client.connect_to_queue()
    
    if game_id:
        await client.play_game(game_id, args.player_id)
    else:
        print("Could not join a game.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
