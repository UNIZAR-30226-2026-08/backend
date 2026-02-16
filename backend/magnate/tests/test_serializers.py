from django.test import TestCase
from django.core.management import call_command
from magnate.models import BaseSquare
from magnate.serializers import GeneralSquareSerializer, GeneralActionSerializer
from magnate.models import *
from django.utils import timezone

class PropertySquareSerializerTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_boards')
        cls.player = CustomUser.objects.create(username="aaa",email="aaa@gmail.com")
        cls.player2 = CustomUser.objects.create(username="bbb",email="bbb@gmail.com")
        cls.game = Game.objects.create(datetime=timezone.now(),active_player=cls.player)

        cls.property_relationship1 = PropertyRelationship.objects.create(game=cls.game,owner=cls.player,
                                                                         square=BaseSquare.objects.get(custom_id=6),
                                                                         houses=2)
        cls.property_relationship2 = PropertyRelationship.objects.create(game=cls.game,owner=cls.player2,
                                                                         square=BaseSquare.objects.get(custom_id=8),
                                                                         houses=3)

        cls.actionThrowDices = ActionThrowDices.objects.create(game=cls.game,player=cls.player,
                                                               dice1=1,dice2=2,dice_bus=3,
                                                               destinations=[20,21,22],triple=False,
                                                               path=[11,12,13,14,15,16,17,18,19])
        
        cls.actionMoveTo = ActionMoveTo.objects.create(game=cls.game,player=cls.player,
                                                       square=BaseSquare.objects.get(custom_id=12))
        
        cls.actionTakeBus = ActionTakeBus.objects.create(game=cls.game,player=cls.player,
                                                         square=BaseSquare.objects.get(custom_id=13))
        
        cls.actionBuySquare = ActionBuySquare.objects.create(game=cls.game,player=cls.player,
                                                             square=BaseSquare.objects.get(custom_id=14))
        
        cls.actionSellSquare = ActionSellSquare.objects.create(game=cls.game,player=cls.player,
                                                               square=BaseSquare.objects.get(custom_id=15))
        
        cls.actionGoToJail = ActionGoToJail.objects.create(game=cls.game,player=cls.player)

        cls.actionBuild = ActionBuild.objects.create(game=cls.game,player=cls.player,
                                                     square=BaseSquare.objects.get(custom_id=17),
                                                     houses=3)
        
        cls.actionDemolish = ActionDemolish.objects.create(game=cls.game,player=cls.player,
                                                           square=BaseSquare.objects.get(custom_id=18),
                                                           houses=2)
        
        cls.actionChooseCard = ActionChooseCard.objects.create(game=cls.game,player=cls.player,
                                                               chosen_card=True)
        
        cls.actionSurrender = ActionSurrender.objects.create(game=cls.game,player=cls.player)

        cls.actionTradeProposal = ActionTradeProposal.objects.create(game=cls.game,player=cls.player,
                                                                     destination_user=cls.player2,
                                                                     offered_money=100,asked_money=200)
        cls.actionTradeProposal.offered_properties.set([cls.property_relationship1])
        cls.actionTradeProposal.asked_properties.set([cls.property_relationship2])
        
        cls.actionTradeAnswer = ActionTradeAnswer.objects.create(game=cls.game,player=cls.player,
                                                                 choose=True,proposal=cls.actionTradeProposal)
        
        cls.actionMortgageSet = ActionMortgageSet.objects.create(game=cls.game,player=cls.player,
                                                                 square=BaseSquare.objects.get(custom_id=19))
        
        cls.actionMortgageUnset = ActionMortgageUnset.objects.create(game=cls.game,player=cls.player,
                                                                     square=BaseSquare.objects.get(custom_id=20))
        
        cls.actionPayBail = ActionPayBail.objects.create(game=cls.game,player=cls.player2)

    def pre_test_1(self):
        casillas = BaseSquare.objects.all()
        print('printear')
        print(casillas[1])
        print(GeneralSquareSerializer(casillas[1]).data)
        self.assertTrue(True)

    ############################################################### squares

    def test_property_square(self):
        casilla = BaseSquare.objects.get(custom_id=8)
        data = GeneralSquareSerializer(casilla).data
        assert isinstance(data,dict)

        self.assertEqual(data["type"],'PropertySquare')
        self.assertEqual(data["custom_id"],8)
        self.assertEqual(data["group"],2)
        self.assertEqual(data["buy_price"],100)
        self.assertEqual(data["rent_prices"],[6,30,90,270,400,550])
        self.assertEqual(data["build_price"],50)

    def test_bridge_square(self):
        casilla = BaseSquare.objects.get(custom_id=15)
        data = GeneralSquareSerializer(casilla).data
        assert isinstance(data,dict)

        self.assertEqual(data["type"],'BridgeSquare')
        self.assertEqual(data["custom_id"],15)
        self.assertEqual(data["buy_price"],250)
        self.assertEqual(data["rent_prices"],[20,40])

    def test_tram_square(self):
        casilla = BaseSquare.objects.get(custom_id=107)
        data = GeneralSquareSerializer(casilla).data
        assert isinstance(data,dict)

        self.assertEqual(data["type"],'TramSquare')
        self.assertEqual(data["custom_id"],107)
        self.assertEqual(data["buy_price"],30)
           
    def test_server_square(self):
        casilla = BaseSquare.objects.get(custom_id=25)
        data = GeneralSquareSerializer(casilla).data
        assert isinstance(data,dict)

        self.assertEqual(data["type"],'ServerSquare')
        self.assertEqual(data["custom_id"],25)
        self.assertEqual(data["buy_price"],300)
        self.assertEqual(data["rent_prices"],[20,60])

    def test_exit_square(self):
        casilla = BaseSquare.objects.get(custom_id=0)
        data = GeneralSquareSerializer(casilla).data
        assert isinstance(data,dict)

        self.assertEqual(data["type"],'ExitSquare')
        self.assertEqual(data["custom_id"],0)
        self.assertEqual(data["init_money"],200)

    def test_go_to_jail_square(self):
        casilla = BaseSquare.objects.get(custom_id=20)
        data = GeneralSquareSerializer(casilla).data
        assert isinstance(data,dict)

        self.assertEqual(data["type"],'GoToJailSquare')
        self.assertEqual(data["custom_id"],20)
        
    def test_jail_square(self):
        casilla = BaseSquare.objects.get(custom_id=104)
        data = GeneralSquareSerializer(casilla).data
        assert isinstance(data,dict)

        self.assertEqual(data["type"],'JailSquare')
        self.assertEqual(data["custom_id"],104)
        self.assertEqual(data["bail_price"],40)

    def test_parking_square(self):
        casilla = BaseSquare.objects.get(custom_id=111)
        data = GeneralSquareSerializer(casilla).data
        assert isinstance(data,dict)

        self.assertEqual(data["type"],'ParkingSquare')
        self.assertEqual(data["custom_id"],111)

    def test_fantasy_square(self):
        casilla = BaseSquare.objects.get(custom_id=109)
        data = GeneralSquareSerializer(casilla).data
        assert isinstance(data,dict)

        self.assertEqual(data["type"],'FantasySquare')
        self.assertEqual(data["custom_id"],109)



    ################################################## actions

    def test_action_throw_dices(self):
        data = GeneralActionSerializer(self.actionThrowDices).data
        assert isinstance(data,dict)
       
        self.assertEqual(data["dice1"],1)
        self.assertEqual(data["dice2"],2)
        self.assertEqual(data["dice_bus"],3)
        self.assertEqual(data["destinations"],[20,21,22])
        self.assertEqual(data["triple"],False)
        self.assertEqual(data["path"],[11,12,13,14,15,16,17,18,19])

    def test_action_move_to(self):
        data = GeneralActionSerializer(self.actionMoveTo).data
        assert isinstance(data,dict)

        self.assertEqual(data["square"],BaseSquare.objects.get(custom_id=12).pk)

    def test_action_take_bus(self):
        data = GeneralActionSerializer(self.actionTakeBus).data
        assert isinstance(data,dict)

        self.assertEqual(data["square"],BaseSquare.objects.get(custom_id=13).pk)

    def test_action_buy_square(self):
        data = GeneralActionSerializer(self.actionBuySquare).data
        assert isinstance(data,dict)

        self.assertEqual(data["square"],BaseSquare.objects.get(custom_id=14).pk)

    def test_action_sell_square(self):
        data = GeneralActionSerializer(self.actionSellSquare).data
        assert isinstance(data,dict)

        self.assertEqual(data["square"],BaseSquare.objects.get(custom_id=15).pk)

    def test_action_go_to_jail(self):
        data = GeneralActionSerializer(self.actionGoToJail).data
        assert isinstance(data,dict)

        self.assertEqual(data["player"],self.player.pk)

    def test_action_build(self):
        data = GeneralActionSerializer(self.actionBuild).data
        assert isinstance(data,dict)

        self.assertEqual(data["square"],BaseSquare.objects.get(custom_id=17).pk)
        self.assertEqual(data["houses"],3)
        
    def test_action_demolish(self):
        data = GeneralActionSerializer(self.actionDemolish).data
        assert isinstance(data,dict)

        self.assertEqual(data["square"],BaseSquare.objects.get(custom_id=18).pk)
        self.assertEqual(data["houses"],2)

    def test_choose_card(self):
        data = GeneralActionSerializer(self.actionChooseCard).data
        assert isinstance(data,dict)

        self.assertEqual(data["chosen_card"],True)
    
    def test_action_surrender(self):
        data = GeneralActionSerializer(self.actionSurrender).data
        assert isinstance(data,dict)

        self.assertEqual(data["player"],self.player.pk)

    def test_trade_proposal(self):
        data = GeneralActionSerializer(self.actionTradeProposal).data
        assert isinstance(data,dict)

        self.assertEqual(data["destination_user"],self.player2.pk)
        self.assertEqual(data["offered_money"],100)
        self.assertEqual(data["asked_money"],200)
        self.assertEqual(data["offered_properties"],[self.property_relationship1.pk])
        self.assertEqual(data["asked_properties"],[self.property_relationship2.pk])
        
    def test_trade_answer(self):
        data = GeneralActionSerializer(self.actionTradeAnswer).data
        assert isinstance(data,dict)

        self.assertEqual(data["choose"],True)
        self.assertEqual(data["proposal"],self.actionTradeProposal.pk)

    def test_mortgage_set(self):
        data = GeneralActionSerializer(self.actionMortgageSet).data
        assert isinstance(data,dict)

        self.assertEqual(data["square"],BaseSquare.objects.get(custom_id=19).pk)

    def test_mortgage_unset(self):
        data = GeneralActionSerializer(self.actionMortgageUnset).data
        assert isinstance(data,dict)

        self.assertEqual(data["square"],BaseSquare.objects.get(custom_id=20).pk)

    def test_action_pay_bail(self):
        data = GeneralActionSerializer(self.actionPayBail).data
        assert isinstance(data,dict)

        self.assertEqual(data["player"],self.player2.pk)
        