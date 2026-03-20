from django.test import TestCase
from django.core.management import call_command
from magnate.models import *
from magnate.games import *
from django.utils import timezone
from asgiref.sync import async_to_sync
from ..games import *
from ..agent import *
from ..serializers import *

class AgentsTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        call_command('init_boards')

    def setUp(self):
        self.agent1 = CustomUser.objects.create(username="a1", email="a1@gmail.com")
        self.agent2 = CustomUser.objects.create(username="a2", email="a2@gmail.com")
        
        self.game = Game.objects.create(
            datetime=timezone.now(),
            active_phase_player=self.agent1,
            active_turn_player=self.agent1,
            phase=GameManager.ROLL_THE_DICES
        )

        self.game.players.set([self.agent1, self.agent2])
        self.game.ordered_players = [self.agent1.pk, self.agent2.pk]
        self.game.save()

        # Create statistics for each player
        for agent in [self.agent1, self.agent2]:
            PlayerGameStatistic.objects.create(user=agent, game=self.game)

        self.game.money = {
            str(self.agent1.pk): 1500, 
            str(self.agent2.pk): 1500,
        }
        self.game.positions = {
            str(self.agent1.pk): "001",
            str(self.agent2.pk): "001",
        }

        self.game.save()

    def test_simulate_game(self):
        agent1 = Agent(self.game, self.agent1, 'very_easy')
        agent2 = Agent(self.game, self.agent2, 'very_easy')
        
        print('\n' + '=' * 60)
        print('STARTING GAME SIMULATION')
        print('=' * 60)
        
        for turn in range(1, 26):
            active_player = self.game.active_phase_player

            if self.game.phase == GameManager.AUCTION:
                async_to_sync(GameManager._end_auction)(self.game)

            if active_player == self.agent1:
                action = agent1.choose_action(self.game)
            elif active_player == self.agent2:
                action = agent2.choose_action(self.game)

            print(f"\n[Turn {turn:02d}] Player: {active_player.username}")
            s_action = GeneralActionSerializer(action).data
            print(f" ├─ Action:   {s_action}")
            
            response = async_to_sync(GameManager.process_action)(self.game, active_player, action)
            
            s_response = GeneralResponseSerializer(response).data
            print(f" └─ Response: {s_response}")
            
            # 5. Refresh game state from the database for the next iteration
            # This is crucial so active_phase_player actually changes in the loop
            self.game.refresh_from_db()

        print('\n' + '=' * 60)
        print('SIMULATION COMPLETE')
        print('=' * 60 + '\n')
        
        self.assertIsNotNone(self.game.pk, "Game should still exist after simulation")
