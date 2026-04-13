from django.test import TestCase
from django.core.management import call_command
from magnate.models import *
from magnate.games import *
from django.utils import timezone
from asgiref.sync import async_to_sync
from ..games import *
from ..agent import *
from ..serializers import *
from unittest.mock import patch


import time

@patch('magnate.tasks.auction_callback.apply_async', **{'return_value.id': 'mock_auction_id'}) #type: ignore
@patch('magnate.tasks.kick_out_callback.apply_async', **{'return_value.id': 'mock_kick_id'})  # type: ignore
@patch('magnate.tasks.next_phase_callback.apply_async', **{'return_value.id': 'mock_phase_id'})  # type: ignore
class AgentsTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        call_command('init_boards')

    def setUp(self):
        self.agent1 = Bot.objects.create(username="a1", email="a1@gmail.com")
        self.agent2 = Bot.objects.create(username="a2", email="a2@gmail.com")
        
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
            str(self.agent1.pk): "000",
            str(self.agent2.pk): "000",
        }

        self.game.save()

    def test_simulate_game(self, mock_next_phase, mock_kick_out, mock_auction_task):
        agent1 = Agent(self.game, self.agent1, 'expert')
        agent2 = Agent(self.game, self.agent2, 'very_easy')
        
        print('\n' + '=' * 60)
        print('STARTING GAME SIMULATION')
        print('=' * 60)
        
        turn = 0
        while turn < 500:
            if self.game.phase == GameManager.END_GAME:
                print(f"\n[!] El juego terminó prematuramente en el turno {turn} (Fase: END_GAME).")
                break
            active_player = self.game.active_phase_player
            
            if active_player.pk == self.agent1.pk:
                action = agent1.choose_action()
            elif active_player.pk == self.agent2.pk:
                action = agent2.choose_action()

            if action is None:
                continue

            print(f"\n[Turn {turn:02d}] Player: {active_player.username}")
            s_action = GeneralActionSerializer(action).data
            print(f" ├─ Action:   {s_action}")

            
            
            if not isinstance(action, Action):
                raise GameLogicError("Wrong type")
            
            response = async_to_sync(GameManager.process_action)(self.game, active_player, action)

            if self.game.phase == GameManager.AUCTION:
                GameManager._end_auction(self.game)
                self.game.refresh_from_db()
                continue
            
            s_response = GeneralResponseSerializer(response).data
            print(f" └─ Response: {s_response}")
            
            # 5. Refresh game state from the database for the next iteration
            # This is crucial so active_phase_player actually changes in the loop
            self.game.refresh_from_db()

            turn += 1

        print('\n' + '=' * 60)
        print('SIMULATION COMPLETE')
        print('=' * 60 + '\n')
        
        self.assertIsNotNone(self.game.pk, "Game should still exist after simulation")
