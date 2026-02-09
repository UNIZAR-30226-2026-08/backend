from magnate.models import FantasyEvent
import random

class FantasyEventFactory:
    def generate(self) -> FantasyEvent:
        fantasy_type = random.choice(FantasyType.values)

        values = None

        if fantasy_type == 'loseMoney':
            values = {'money': random.randrange(100, 1000, 50)}
        elif fantasy_type == 'gainMoney':
            values = {'money': random.randrange(100, 1000, 50)}

        return FantasyEvent(
                event_type = fantasy_type,
                values = values
                )

def apply_fantasy_event(gameID, fantasy_event: FantasyEvent):
    raise NotImplementedError

