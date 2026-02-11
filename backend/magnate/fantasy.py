from magnate.models import FantasyEvent
import random

class FantasyEventFactory:
    def generate(self) -> FantasyEvent:
        fantasy_type = random.choice(FantasyEvent.FantasyType.values)

        values = None
        card_cost = None

        if fantasy_type == 'winPlainMoney':
            card_cost = 130
            rand = random.randrange(5)
            if(rand == 0):
                values = {'money': 20}
            elif(rand == 1):
                values = {'money': 60}
            elif(rand == 2):
                values = {'money': 120}
            elif(rand == 3):
                values = {'money': 150}
            elif(rand == 4):
                values = {'money': 200}
                
            
        elif fantasy_type == 'winRatioMoney':
            card_cost = 500
            rand = random.randrange(4)
            if(rand == 0):
                values = {'money': 1}
            elif(rand == 1):
                values = {'money': 2}
            elif(rand == 2):
                values = {'money': 5}
            elif(rand == 3):
                values = {'money': 10}


        elif fantasy_type == 'losePlainMoney':
            card_cost = 80
            rand = random.randrange(5)
            if(rand == 0):
                values = {'money': 40}
            elif(rand == 1):
                values = {'money': 80}
            elif(rand == 2):
                values = {'money': 120}
            elif(rand == 3):
                values = {'money': 150}
            elif(rand == 4):
                values = {'money': 200}


        elif fantasy_type == 'loseRatioMoney':
            card_cost = 30
            rand = random.randrange(4)
            if(rand == 0):
                values = {'money': 1}
            elif(rand == 1):
                values = {'money': 2}
            elif(rand == 2):
                values = {'money': 5}
            elif(rand == 3):
                values = {'money': 10}

        elif fantasy_type == 'breakOpponentHouse':
            card_cost = 150

        elif fantasy_type == 'breakOwnHouse':
            card_cost = 30

        elif fantasy_type == 'shufflePositions':
            card_cost = 50

        elif fantasy_type == 'moveAnywhereRandom':
            card_cost = 50

        elif fantasy_type == 'moveOpponentAnywhereRandom':
            card_cost = 60

        elif fantasy_type == 'shareMoneyAll':
            card_cost = 5
            rand = random.randrange(3)
            if(rand == 0):
                values = {'money': 20}
            elif(rand == 1):
                values = {'money': 30}
            elif(rand == 2):
                values = {'money': 50}

        elif fantasy_type == 'dontPayNextTurnRent':
            card_cost = 35

        elif fantasy_type == 'allYourRentsX2OneTurn':
            card_cost = 100

        elif fantasy_type == 'freeHouse':
            card_cost = 80
        
        elif fantasy_type == 'outOfJailCard':
            card_cost = 40

        elif fantasy_type == 'goToJail':
            card_cost = 25
        
        elif fantasy_type == 'sendToJail':
            card_cost = 80

        elif fantasy_type == 'everybodyToJail':
            card_cost = 50
        
        elif fantasy_type == 'doubleOrNothing':
            card_cost = 50

        elif fantasy_type == 'getParkingMoney':
            card_cost = 500

        elif fantasy_type == 'reviveProperty':
            card_cost = 100

        elif fantasy_type == 'earthquake':
            card_cost = 200

        elif fantasy_type == 'everybodySendsYouMoney':
            card_cost = 120
            rand = random.randrange(3)
            if(rand == 0):
                values = {'money': 20}
            elif(rand == 1):
                values = {'money': 30}
            elif(rand == 2):
                values = {'money': 50}

        elif fantasy_type == 'magnetism':
            card_cost = 100

        elif fantasy_type == 'goToStart':
            card_cost = 90

        return FantasyEvent(
                event_type = fantasy_type,
                values = values,
                card_cost = card_cost
                )

def apply_fantasy_event(gameID, fantasy_event: FantasyEvent):
    raise NotImplementedError

