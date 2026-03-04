from django.test import TestCase
from django.core.management import call_command
from magnate.models import *
from django.utils import timezone
from magnate.fantasy import apply_fantasy_event
from asgiref.sync import async_to_sync
import random

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

        self.players = [self.player1,self.player2,self.player3,self.player4]

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
            square=BaseSquare.objects.get(custom_id=1),
            houses=2
        )
        self.propRelation2 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player2,
            square=BaseSquare.objects.get(custom_id=6),
            houses=3
        )
        self.propRelation3 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player3,
            square=BaseSquare.objects.get(custom_id=11),
            houses=4
        )
        self.propRelation4 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player4,
            square=BaseSquare.objects.get(custom_id=16),
            houses=2
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
        self.assertEqual(result.fantasy_type,'winPlainMoney')
        self.assertEqual(result.values,None)
        self.assertEqual(self.game.money[self.player1.pk],160)

    def test_win_ratio_money(self):
        event = FantasyEvent(fantasy_type='winRatioMoney',
                             values={'money':5},
                             card_cost=500)
        
        result : FantasyResult = async_to_sync(apply_fantasy_event)(self.game,self.player2,event)
        self.assertEqual(result.fantasy_type,'winRatioMoney')
        self.assertEqual(result.values,None)
        self.assertEqual(self.game.money[self.player2.pk],210)

    def test_lose_plain_money(self):
        event = FantasyEvent(fantasy_type='losePlainMoney',
                             values={'money':60},
                             card_cost=130)
        
        result : FantasyResult = async_to_sync(apply_fantasy_event)(self.game,self.player1,event)
        self.assertEqual(result.fantasy_type,'losePlainMoney')
        self.assertEqual(result.values,None)
        self.assertEqual(self.game.money[self.player1.pk],40)

    def test_lose_ratio_money(self):
        event = FantasyEvent(fantasy_type='loseRatioMoney',
                             values={'money':5},
                             card_cost=500)
        
        result : FantasyResult = async_to_sync(apply_fantasy_event)(self.game,self.player2,event)
        self.assertEqual(result.fantasy_type,'loseRatioMoney')
        self.assertEqual(result.values,None)
        self.assertEqual(self.game.money[self.player2.pk],190)

    def test_break_opponent_house(self):
        event = FantasyEvent(fantasy_type='breakOpponentHouse',
                             values=None,
                             card_cost=500)
        
        result : FantasyResult = async_to_sync(apply_fantasy_event)(self.game,
                                                                    random.choice(self.players),
                                                                    event)
        self.assertEqual(result.fantasy_type,'breakOpponentHouse')
        self.assertNotEqual(result.values,None)
        if result.values is None:
            raise Exception('Impossible')
        square_id = result.values['square']
        props = PropertyRelationship.objects.filter(
            game=self.game,
            square__custom_id=square_id,
            )
        self.assertEqual(props.count(),1)
        prop = props.first()
        if prop is None:
            raise Exception('impossible')
        
        if square_id == 1:
            self.assertEqual(prop.houses,1)
        elif square_id == 6:
            self.assertEqual(prop.houses,2)
        elif square_id == 11:
            self.assertEqual(prop.houses,3)
        elif square_id == 16:
            self.assertEqual(prop.houses,1)
        else:
            self.assertTrue(False)

    def test_break_opponent_house2(self):
        event = FantasyEvent(fantasy_type='breakOpponentHouse',
                             values=None,
                             card_cost=500)
        
        ############################################change db for only 1 player with houses
        self.propRelation1.delete()
        self.propRelation2.delete()
        self.propRelation3.delete()

        self.propRelation5 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player4,
            square=BaseSquare.objects.get(custom_id=18),#mismo grupo que 16
            houses=3
        )
        self.propRelation6 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player4,
            square=BaseSquare.objects.get(custom_id=19),#mismo grupo que 16
            houses=3
        )
        self.propRelation7 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player4,
            square=BaseSquare.objects.get(custom_id=21),#otro grupo
            houses=2
        )
        
        ###########################################

        result : FantasyResult = async_to_sync(apply_fantasy_event)(self.game,
                                                                    self.player1,
                                                                    event)
        self.assertEqual(result.fantasy_type,'breakOpponentHouse')
        self.assertNotEqual(result.values,None)
        if result.values is None:
            raise Exception('Impossible')
        square_id = result.values['square']
        props = PropertyRelationship.objects.filter(
            game=self.game,
            square__custom_id=square_id,
            )
        self.assertEqual(props.count(),1)
        prop = props.first()
        if prop is None:
            raise Exception('impossible')
        
        if square_id == 16:
            self.assertTrue(False, 'Incorrect break')
        elif square_id == 18:
            self.assertEqual(prop.houses,2)
        elif square_id == 19:
            self.assertEqual(prop.houses,2)
        elif square_id == 21:
            self.assertEqual(prop.houses,1)
        else:
            self.assertTrue(False, 'else')

    def test_break_opponent_house3(self):
        event = FantasyEvent(fantasy_type='breakOpponentHouse',
                             values=None,
                             card_cost=500)
        
        ############################################change db for squares with 0 houses
        self.propRelation1.delete()
        self.propRelation2.delete()
        self.propRelation3.delete()
        self.propRelation4.delete()

        self.propRelation5 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player4,
            square=BaseSquare.objects.get(custom_id=18),#mismo grupo que 16
            houses=0
        )
        self.propRelation6 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player4,
            square=BaseSquare.objects.get(custom_id=19),#mismo grupo que 16
            houses=0
        )
        self.propRelation7 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player4,
            square=BaseSquare.objects.get(custom_id=21),#otro grupo
            houses=0
        )
        
        ###########################################

        result : FantasyResult = async_to_sync(apply_fantasy_event)(self.game,
                                                                    self.player1,
                                                                    event)
        self.assertEqual(result.fantasy_type,'breakOpponentHouse')
        self.assertEqual(result.values,None)

    def test_break_own_house(self):
        self.propRelation5 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=3),#mismo grupo que 1
            houses=4
        )
        self.propRelation6 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=108),
            houses=1
        )
        self.propRelation7 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=110),#mismo grupo que 108
            houses=1
        )

        event = FantasyEvent(fantasy_type='breakOwnHouse',
                             values=None,
                             card_cost=1)
        
        result : FantasyResult = async_to_sync(apply_fantasy_event)(self.game,
                                                                    self.player1,
                                                                    event)
        self.assertEqual(result.fantasy_type,'breakOwnHouse')
        self.assertNotEqual(result.values,None)
        if result.values is None:
            raise Exception('Impossible')
        square_id = result.values['square']
        props = PropertyRelationship.objects.filter(
            game=self.game,
            square__custom_id=square_id,
            )
        self.assertEqual(props.count(),1)
        prop = props.first()
        if prop is None:
            raise Exception('impossible')
    
        if square_id == 1:
            self.assertTrue(False, 'Incorrect break')
        elif square_id == 3:
            self.assertEqual(prop.houses,3)
        elif square_id == 108:
            self.assertEqual(prop.houses,0)
        elif square_id == 110:
            self.assertEqual(prop.houses,0)
        else:
            self.assertTrue(False, 'else')

    def test_shuffle_positions(self): #TODO: test con carcel cuando esté
                                     #TODO: no sé que más probar la verdad
        event = FantasyEvent(fantasy_type='shufflePositions',
                             values=None,
                             card_cost=1)
        
        result : FantasyResult = async_to_sync(apply_fantasy_event)(self.game,
                                                                    self.player1,
                                                                    event)
        self.assertEqual(result.fantasy_type,'shufflePositions')
        self.assertEqual(result.values,None)
        #for player in self.players:
            #print(self.game.positions[player.pk])

    def test_move_anywhere_random(self):
        event = FantasyEvent(fantasy_type='moveAnywhereRandom',
                             values=None,
                             card_cost=1)
        result : FantasyResult = async_to_sync(apply_fantasy_event)(self.game,
                                                                    self.player1,
                                                                    event)
        self.assertEqual(result.fantasy_type,'moveAnywhereRandom')
        self.assertEqual(result.values,None)
        print(self.game.positions[self.player1.pk])

