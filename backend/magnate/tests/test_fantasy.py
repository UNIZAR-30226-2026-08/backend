from django.test import TestCase
from django.core.management import call_command
from magnate.models import *
from django.utils import timezone
from magnate.fantasy import apply_fantasy_event
from asgiref.sync import async_to_sync

class FantasyTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        call_command('init_boards')

    def setUp(self) -> None:
        ################################# set up players
        self.player1 = CustomUser.objects.create(username="aaa",email="aaa@gmail.com")
        self.player2 = CustomUser.objects.create(username="bbb",email="bbb@gmail.com")
        self.player3 = CustomUser.objects.create(username="ccc",email="ccc@gmail.com")
        self.player4 = CustomUser.objects.create(username="ddd",email="ddd@gmail.com")

        ################################## set up game
        self.game = Game.objects.create(datetime=timezone.now())
        self.game.players.set([self.player1,self.player2,self.player3,self.player4])

        self.game.positions[self.player1.pk] = 1
        self.game.positions[self.player2.pk] = 2
        self.game.positions[self.player3.pk] = 103
        self.game.positions[self.player4.pk] = 104

        self.game.parking_money = 1500

        self.game.money[self.player1.pk] = 100
        self.game.money[self.player2.pk] = 200
        self.game.money[self.player3.pk] = 300
        self.game.money[self.player4.pk] = 400

        self.game.save()

        ################################## set up propertyRelationships
        self.propRelation1 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=6),
            houses=1
        )
        self.propRelation2 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player2,
            square=BaseSquare.objects.get(custom_id=16),
            houses=2
        )
        self.propRelation3 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player3,
            square=BaseSquare.objects.get(custom_id=26),
            houses=3
        )
        self.propRelation4 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player4,
            square=BaseSquare.objects.get(custom_id=36),
            houses=4
        )

    ####################################################################tests de prueba
    def pre_test_1(self):
        self.game.money[self.player1.pk] += 1234
        self.game.save()
        print(self.game.money[self.player1.pk])

    def pre_test_2(self):
        print(self.game.money[self.player1.pk])

    ####################################################################### tests
    def test_win_plain_money(self):
        event = FantasyEvent(fantasy_type='winPlainMoney',
                             values={'money':60},
                             card_cost=130)
        
        result : FantasyResult = async_to_sync(apply_fantasy_event)(self.game,self.player1,event)
        print(result.fantasy_type)
