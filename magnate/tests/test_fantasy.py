from django.test import TestCase
from django.core.management import call_command
from magnate.models import *
from django.utils import timezone
from magnate.fantasy import apply_fantasy_event
from asgiref.sync import async_to_sync
from magnate.games import _get_relationship, _get_jail_square
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

        self.game.positions[str(self.player1.pk)] = 1
        self.game.positions[str(self.player2.pk)] = 2
        self.game.positions[str(self.player3.pk)] = 103
        self.game.positions[str(self.player4.pk)] = 104

        self.game.parking_money = 1500

        self.game.money[str(self.player1.pk)] = 100
        self.game.money[str(self.player2.pk)] = 200
        self.game.money[str(self.player3.pk)] = 300
        self.game.money[str(self.player4.pk)] = 400

        self.game.save()

        # Create statistics for each player
        for player in self.players:
            PlayerGameStatistic.objects.create(user=player, game=self.game)

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
        self.game.money[str(self.player1.pk)] += 1234
        self.game.save()
        print(self.game.money[str(self.player1.pk)])

    def pre_test_2(self):
        print(self.game.money[str(self.player1.pk)])

    ####################################################################### tests
    def test_win_plain_money(self):
        event = FantasyEvent(fantasy_type='winPlainMoney',
                             value=60,
                             card_cost=130)
        
        result : FantasyResult = apply_fantasy_event(self.game,self.player1,event)
        self.assertEqual(result.fantasy_event.fantasy_type,'winPlainMoney')
        self.assertEqual(result.result, None)
        self.assertEqual(self.game.money[str(self.player1.pk)],160)

    def test_win_ratio_money(self):
        event = FantasyEvent(fantasy_type='winRatioMoney',
                             value=5,
                             card_cost=500)
        
        result : FantasyResult = apply_fantasy_event(self.game,self.player2,event)
        self.assertEqual(result.fantasy_event.fantasy_type,'winRatioMoney')
        self.assertEqual(result.result,None)
        self.assertEqual(self.game.money[str(self.player2.pk)],210)

    def test_lose_plain_money(self):
        event = FantasyEvent(fantasy_type='losePlainMoney',
                             value=60,
                             card_cost=130)
        
        result : FantasyResult = apply_fantasy_event(self.game,self.player1,event)
        self.assertEqual(result.fantasy_event.fantasy_type,'losePlainMoney')
        self.assertEqual(result.result,None)
        self.assertEqual(self.game.money[str(self.player1.pk)],40)

    def test_lose_ratio_money(self):
        event = FantasyEvent(fantasy_type='loseRatioMoney',
                             value=5,
                             card_cost=500)
        
        result : FantasyResult = apply_fantasy_event(self.game,self.player2,event)
        self.assertEqual(result.fantasy_event.fantasy_type,'loseRatioMoney')
        self.assertEqual(result.result, None)
        self.assertEqual(self.game.money[str(self.player2.pk)],190)

    def test_break_opponent_house(self):
        event = FantasyEvent(fantasy_type='breakOpponentHouse',
                             value=None,
                             card_cost=500)
        
        previous_money = self.game.money.copy()
        
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    random.choice(self.players),
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'breakOpponentHouse')
        self.assertNotEqual(result.result, None)
        if result.result is None:
            raise Exception('Impossible')
        square_id = result.result['square']
        props = PropertyRelationship.objects.filter(
            game=self.game,
            square__custom_id=square_id,
            )
        self.assertEqual(props.count(),1)
        self.assertEqual(previous_money,self.game.money)
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
                             value=None,
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

        previous_money = self.game.money.copy()

        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type, 'breakOpponentHouse')
        self.assertNotEqual(result.result, None)
        if result.result is None:
            raise Exception('Impossible')
        square_id = result.result['square']
        props = PropertyRelationship.objects.filter(
            game=self.game,
            square__custom_id=square_id,
            )
        self.assertEqual(props.count(),1)
        prop = props.first()
        if prop is None:
            raise Exception('impossible')
        
        self.assertEqual(previous_money,self.game.money)
        
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
                             value=None,
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

        previous_money = self.game.money.copy()

        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type, 'breakOpponentHouse')
        self.assertEqual(result.result, None)
        self.assertEqual(previous_money,self.game.money)
        

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
                             value=None,
                             card_cost=1)
        
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'breakOwnHouse')
        self.assertNotEqual(result.result, None)
        if result.result is None:
            raise Exception('Impossible')
        square_id = result.result['square']
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
        event = FantasyEvent(fantasy_type='shufflePositions',
                             value=None,
                             card_cost=1)
        
        result : FantasyResult = apply_fantasy_event(self.game,self.player1,event)
        self.assertEqual(result.fantasy_event.fantasy_type,'shufflePositions')
        self.assertEqual(result.result,None)
        #for player in self.players:
            #print(self.game.positions[str(player.pk)])

    def test_move_anywhere_random(self):
        event = FantasyEvent(fantasy_type='moveAnywhereRandom',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                                    self.player1,
                                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'moveAnywhereRandom')
        self.assertEqual(result.result,None)
        #print(self.game.positions[str(self.player1.pk)])

    def test_move_opponent_anywhere_random(self):
        event = FantasyEvent(fantasy_type='moveOpponentAnywhereRandom',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'moveOpponentAnywhereRandom')
        self.assertNotEqual(result.result,None)
        if result.result is None:
            self.assertTrue(False)
            return
        self.assertNotEqual(self.player1.pk,result.result['target_player'])
        #print(result.result['target_player_pk'])
        #print(self.game.positions[str(result.result['target_player_pk'])])

    def test_share_money_all(self):
        event = FantasyEvent(fantasy_type='shareMoneyAll',
                             value=30,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'shareMoneyAll')
        self.assertEqual(self.game.money[str(self.player1.pk)],100-(30*3))
        self.assertEqual(self.game.money[str(self.player2.pk)],200+30)
        self.assertEqual(self.game.money[str(self.player3.pk)],300+30)
        self.assertEqual(self.game.money[str(self.player4.pk)],400+30)
        
    def test_free_house1(self):
        self.propRelation1.delete()
        self.propRelation2.delete()
        self.propRelation3.delete()
        self.propRelation4.delete()

        ###### complete group 4
        self.propRelation1 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=16),
            houses=2
        )
        self.propRelation2 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=18),
            houses=2
        )
        self.propRelation3 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=19),
            houses=2
        )

        ####### non completed group 5
        self.propRelation4 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=21),
            houses=-1
        )


        ###############################
        event = FantasyEvent(fantasy_type='freeHouse',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        
        self.assertEqual(result.fantasy_event.fantasy_type,'freeHouse')
        if result.result is None:
            self.assertTrue(False)
            return
        
        targeted_property_relationship = _get_relationship(self.game,
                    BaseSquare.objects.get(custom_id=result.result['square']))
        
        if targeted_property_relationship is None:
            self.assertTrue(False)
            return

        self.assertEqual(targeted_property_relationship.houses,3)

    def test_free_house2(self):
        self.propRelation1.delete()
        self.propRelation2.delete()
        self.propRelation3.delete()
        self.propRelation4.delete()

        self.propRelation4 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=21),
            houses=-1
        )

        ###############################
        event = FantasyEvent(fantasy_type='freeHouse',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        
        self.assertEqual(result.fantasy_event.fantasy_type,'freeHouse')
        self.assertEqual(result.result, None)
        self.assertEqual(self.propRelation4.houses,-1)

    def test_free_house3(self):
        self.propRelation1.delete()
        self.propRelation2.delete()
        self.propRelation3.delete()
        self.propRelation4.delete()

        self.propRelation1 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=16),
            houses=1
        )
        self.propRelation2 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=18),
            houses=1
        )
        self.propRelation3 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=19),
            houses=0
        )

        ###############################
        event = FantasyEvent(fantasy_type='freeHouse',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        
        self.assertEqual(result.fantasy_event.fantasy_type,'freeHouse')
        if result.result is None:
            self.assertTrue(False)
            return
        
        self.assertEqual(result.result['square'],19)
        targeted_property_relationship = _get_relationship(self.game,
                    BaseSquare.objects.get(custom_id=19))
        
        if targeted_property_relationship is None:
            self.assertTrue(False)
            return

        self.assertEqual(targeted_property_relationship.houses,1)

    def test_go_to_jail(self):
        event = FantasyEvent(fantasy_type='goToJail',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'goToJail')
        jail_id = _get_jail_square().custom_id
        self.assertEqual(self.game.positions[str(self.player1.pk)],jail_id)
        self.assertEqual(self.game.jail_remaining_turns[str(self.player1.pk)],3)

    def test_send_to_jail(self):
        event = FantasyEvent(fantasy_type='sendToJail',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'sendToJail')
        jail_id = _get_jail_square().custom_id
        if result.result is None:
            self.assertFalse(True)
            return
        self.assertEqual(self.game.positions[str(result.result['target_player'])],jail_id)
        self.assertNotEqual(result.result['target_player'],self.player1.pk)
        self.assertEqual(self.game.jail_remaining_turns[str(result.result['target_player'])],3)
    
    def test_everybody_to_jail(self):
        event = FantasyEvent(fantasy_type='everybodyToJail',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'everybodyToJail')
        jail_id = _get_jail_square().custom_id
        for p in self.game.players.all():
            self.assertEqual(self.game.positions[str(p.pk)],jail_id)
            self.assertEqual(self.game.jail_remaining_turns[str(p.pk)],3)

    def test_double_or_nothing(self):
        event = FantasyEvent(fantasy_type='doubleOrNothing',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        
        self.assertEqual(result.fantasy_event.fantasy_type,'doubleOrNothing')
        if result.result is None:
            self.assertTrue(False)
            return
        
        if result.result['doubled']:
            #print('doubled')
            self.assertEqual(self.game.money[str(self.player1.pk)],200)
        else:
            #print('not doubled')
            self.assertEqual(self.game.money[str(self.player1.pk)],0)

    def test_get_parking_money(self):
        self.game.parking_money = 1500
        self.game.save()

        event = FantasyEvent(fantasy_type='getParkingMoney',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'getParkingMoney')
        self.assertEqual(self.game.money[str(self.player1.pk)],1600)

    def test_revive_property1(self):
        self.propRelation1.delete()
        self.propRelation2.delete()
        self.propRelation3.delete()
        self.propRelation4.delete()

        ####### group 5
        self.propRelation1 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=16),
            houses=0
        )
        self.propRelation2 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=18),
            houses=0
        )
        self.propRelation3 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=19),
            houses=0,
            mortgage=True
        )

        ######################

        event = FantasyEvent(fantasy_type='reviveProperty',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'reviveProperty')
        if result.result is None:
            self.assertTrue(False)
            return
        self.assertEqual(result.result['square'],19)
        targeted_property_relationship = _get_relationship(self.game,
                    BaseSquare.objects.get(custom_id=19))
        
        if targeted_property_relationship is None:
            self.assertTrue(False)
            return

        self.assertEqual(targeted_property_relationship.mortgage,False)
        
    def test_revive_property2(self):
        self.propRelation1.delete()
        self.propRelation2.delete()
        self.propRelation3.delete()
        self.propRelation4.delete()

        ####### group 5
        self.propRelation1 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=16),
            houses=0
        )
        self.propRelation2 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=18),
            houses=0
        )
        self.propRelation3 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=19),
            houses=0
        )

        ######################

        event = FantasyEvent(fantasy_type='reviveProperty',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'reviveProperty')
        
        self.assertEqual(result.result, None)    

    def test_earthquake(self):
        self.propRelation5 = PropertyRelationship.objects.create(
            game=self.game,owner=self.player1,
            square=BaseSquare.objects.get(custom_id=19),
            houses=0
        )

        event = FantasyEvent(fantasy_type='earthquake',
                             value=None,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'earthquake')

        relationships = PropertyRelationship.objects.all()
        self.assertEqual(relationships[0].houses,1)
        self.assertEqual(relationships[1].houses,2)
        self.assertEqual(relationships[2].houses,3)
        self.assertEqual(relationships[3].houses,1)
        self.assertEqual(relationships[4].houses,0)

        if result.result is None:
            self.assertTrue(False)
            return
        self.assertEqual(len(result.result['squares']),4)

    def test_everybody_sends_you_money(self):
        event = FantasyEvent(fantasy_type='everybodySendsYouMoney',
                             value=30,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type, 'everybodySendsYouMoney')
        self.assertEqual(self.game.money[str(self.player1.pk)],100+3*30)
        self.assertEqual(self.game.money[str(self.player2.pk)],200-30)
        self.assertEqual(self.game.money[str(self.player3.pk)],300-30)
        self.assertEqual(self.game.money[str(self.player4.pk)],400-30)

    def test_magnetism(self):
        jail_id = _get_jail_square().custom_id
        self.game.positions[str(self.player4.pk)] = jail_id
        self.game.save()

        original_position = self.game.positions[str(self.player1.pk)]
        event = FantasyEvent(fantasy_type='magnetism',
                             value=30,
                             card_cost=1)
        result : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event)
        self.assertEqual(result.fantasy_event.fantasy_type,'magnetism')
        self.assertEqual(result.result,None)
        self.assertEqual(self.game.positions[str(self.player1.pk)],original_position)
        self.assertEqual(self.game.positions[str(self.player2.pk)],original_position)
        self.assertEqual(self.game.positions[str(self.player3.pk)],original_position)
        self.assertEqual(self.game.positions[str(self.player4.pk)],jail_id)

    def test_go_to_start(self):
        jail_id = _get_jail_square().custom_id
        self.game.positions[str(self.player2.pk)] = jail_id
        self.game.save()

        event1 = FantasyEvent(fantasy_type='goToStart',
                             value=30,
                             card_cost=1)
        result1 : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player1,
                                                    event1)
        
        event2 = FantasyEvent(fantasy_type='goToStart',
                             value=30,
                             card_cost=1)
        result2 : FantasyResult = apply_fantasy_event(self.game,
                                                    self.player2,
                                                    event2)
        

        self.assertEqual(result1.fantasy_event.fantasy_type,'goToStart')
        self.assertEqual(result2.fantasy_event.fantasy_type,'goToStart')

        self.assertEqual(self.game.positions[str(self.player1.pk)],BaseSquare.objects.get(custom_id=0).custom_id)
        self.assertEqual(self.game.money[str(self.player1.pk)],300)

        self.assertEqual(self.game.positions[str(self.player2.pk)],jail_id)
        self.assertEqual(self.game.money[str(self.player2.pk)],200)
