from django.test import TestCase
from django.core.management import call_command
from magnate.models import BaseSquare
from magnate.serializers import GeneralSquareSerializer, GeneralActionSerializer, action_from_json, FantasyEventSerializer
from magnate.models import *
from django.utils import timezone
from magnate.fantasy import FantasyEventFactory

class SerializerTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_boards')

        ############################# actions
        cls.player = CustomUser.objects.create(username="aaa",email="aaa@gmail.com")
        cls.player2 = CustomUser.objects.create(username="bbb",email="bbb@gmail.com")
        cls.game = Game.objects.create(datetime=timezone.now())
        cls.game.players.set([cls.player])

        cls.property_relationship1 = PropertyRelationship.objects.create(game=cls.game,owner=cls.player,
                                                                         square=BaseSquare.objects.get(custom_id=6),
                                                                         houses=2)
        cls.property_relationship2 = PropertyRelationship.objects.create(game=cls.game,owner=cls.player2,
                                                                         square=BaseSquare.objects.get(custom_id=8),
                                                                         houses=3)

        cls.actionThrowDices = ActionThrowDices.objects.create(game=cls.game, player=cls.player)
        
        cls.actionMoveTo = ActionMoveTo.objects.create(game=cls.game,player=cls.player,
                                                       square=BaseSquare.objects.get(custom_id=12))
        
        cls.actionTakeTram = ActionTakeTram.objects.create(game=cls.game,player=cls.player,
                                                         square=BaseSquare.objects.get(custom_id=13))

        cls.actionDoNotTakeTram = ActionDoNotTakeTram.objects.create(game=cls.game,player=cls.player)
        
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
        casilla = BaseSquare.objects.get(custom_id=201)
        data = GeneralSquareSerializer(casilla).data
        assert isinstance(data,dict)

        self.assertEqual(data["type"],'JailSquare')
        self.assertEqual(data["custom_id"],201)
        self.assertEqual(data["bail_price"],40)

    #TODO: visit jail

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
        json_in = {"type": "ActionThrowDices",
                   "game":self.game.pk,
                   "player":self.player.pk}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionThrowDices)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)

    def test_action_move_to(self):
        data = GeneralActionSerializer(self.actionMoveTo).data
        assert isinstance(data,dict)
        self.assertEqual(data["square"],12)

        json_in = {"type": "ActionMoveTo",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "square":101}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionMoveTo)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        self.assertEqual(instance.square.custom_id,101)
        

    def test_action_take_tram(self):
        data = GeneralActionSerializer(self.actionTakeTram).data
        assert isinstance(data,dict)
        self.assertEqual(data["square"],13)

        json_in = {"type": "ActionTakeTram",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "square":102}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionTakeTram)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        self.assertEqual(instance.square.custom_id,102)

    def test_action_do_not_take_tram(self):
        data = GeneralActionSerializer(self.actionDoNotTakeTram).data
        assert isinstance(data,dict)

        json_in = {"type": "ActionDoNotTakeTram",
                   "game":self.game.pk,
                   "player":self.player.pk}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionDoNotTakeTram)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)

    def test_action_buy_square(self):
        data = GeneralActionSerializer(self.actionBuySquare).data
        assert isinstance(data,dict)
        self.assertEqual(data["square"],14)

        json_in = {"type": "ActionBuySquare",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "square":103}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionBuySquare)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        self.assertEqual(instance.square.custom_id,103)

    def test_action_sell_square(self):
        data = GeneralActionSerializer(self.actionSellSquare).data
        assert isinstance(data,dict)
        self.assertEqual(data["square"],15)

        json_in = {"type": "ActionSellSquare",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "square":104}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionSellSquare)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        self.assertEqual(instance.square.custom_id,104)

    def test_action_go_to_jail(self):
        data = GeneralActionSerializer(self.actionGoToJail).data
        assert isinstance(data,dict)
        self.assertEqual(data["player"],self.player.pk)

        json_in = {"type": "ActionGoToJail",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "square":103}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionGoToJail)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)

    def test_action_build(self):
        data = GeneralActionSerializer(self.actionBuild).data
        assert isinstance(data,dict)
        self.assertEqual(data["square"],17)
        self.assertEqual(data["houses"],3)

        json_in = {"type": "ActionBuild",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "houses":2,
                   "square":105}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionBuild)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        self.assertEqual(instance.houses,2)
        self.assertEqual(instance.square.custom_id,105)
        
    def test_action_demolish(self):
        data = GeneralActionSerializer(self.actionDemolish).data
        assert isinstance(data,dict)
        self.assertEqual(data["square"],18)
        self.assertEqual(data["houses"],2)

        json_in = {"type": "ActionDemolish",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "houses":1,
                   "square":106}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionDemolish)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        self.assertEqual(instance.houses,1)
        self.assertEqual(instance.square.custom_id,106)

    def test_choose_card(self):
        data = GeneralActionSerializer(self.actionChooseCard).data
        assert isinstance(data,dict)
        self.assertEqual(data["chosen_card"],True)

        json_in = {"type": "ActionChooseCard",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "chosen_card":True}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionChooseCard)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        self.assertEqual(instance.chosen_card,True)
    
    def test_action_surrender(self):
        data = GeneralActionSerializer(self.actionSurrender).data
        assert isinstance(data,dict)
        self.assertEqual(data["player"],self.player.pk)

        json_in = {"type": "ActionSurrender",
                   "game":self.game.pk,
                   "player":self.player2.pk}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionSurrender)
        self.assertEqual(instance.player,self.player2)
        self.assertEqual(instance.game,self.game)

    def test_trade_proposal(self):
        data = GeneralActionSerializer(self.actionTradeProposal).data
        assert isinstance(data,dict)
        self.assertEqual(data["destination_user"],self.player2.pk)
        self.assertEqual(data["offered_money"],100)
        self.assertEqual(data["asked_money"],200)
        self.assertEqual(data["offered_properties"],[self.property_relationship1.pk])
        self.assertEqual(data["asked_properties"],[self.property_relationship2.pk])
        
        json_in = {"type": "ActionTradeProposal",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "destination_user":self.player2.pk,
                   "offered_money":300,
                   "asked_money":400,
                   "offered_properties":[self.property_relationship1.pk],
                   "asked_properties":[self.property_relationship2.pk]}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionTradeProposal)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        self.assertEqual(instance.destination_user,self.player2)
        self.assertEqual(instance.offered_money,300)
        self.assertEqual(instance.asked_money,400)
        self.assertEqual(list(instance.offered_properties.all()),[self.property_relationship1])
        self.assertEqual(list(instance.asked_properties.all()),[self.property_relationship2])

    def test_trade_answer(self):
        data = GeneralActionSerializer(self.actionTradeAnswer).data
        assert isinstance(data,dict)
        self.assertEqual(data["choose"],True)
        self.assertEqual(data["proposal"],self.actionTradeProposal.pk)

        self.actionTradeAnswer.delete() #cant coexist 2 answers for the same proposal

        json_in = {"type": "ActionTradeAnswer",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "choose":True,
                   "proposal":self.actionTradeProposal.pk}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionTradeAnswer)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        self.assertEqual(instance.choose,True)
        self.assertEqual(instance.proposal,self.actionTradeProposal)


    def test_mortgage_set(self):
        data = GeneralActionSerializer(self.actionMortgageSet).data
        assert isinstance(data,dict)
        self.assertEqual(data["square"],19)

        json_in = {"type": "ActionMortgageSet",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "square":107}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionMortgageSet)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        self.assertEqual(instance.square.custom_id,107)

    def test_mortgage_unset(self):
        data = GeneralActionSerializer(self.actionMortgageUnset).data
        assert isinstance(data,dict)
        self.assertEqual(data["square"],20)

        json_in = {"type": "ActionMortgageUnset",
                   "game":self.game.pk,
                   "player":self.player.pk,
                   "square":108}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionMortgageUnset)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        self.assertEqual(instance.square.custom_id,108)

    def test_action_pay_bail(self):
        data = GeneralActionSerializer(self.actionPayBail).data
        assert isinstance(data,dict)
        self.assertEqual(data["player"],self.player2.pk)

        json_in = {"type": "ActionPayBail",
                   "game":self.game.pk,
                   "player":self.player.pk}
        instance = action_from_json(json_in)
        assert isinstance(instance,ActionPayBail)
        self.assertEqual(instance.player,self.player)
        self.assertEqual(instance.game,self.game)
        

##############################################################################fantsy serializers
    def test_fantasy_event(self):
        fantasyEvent1 = FantasyEvent(fantasy_type='winPlainMoney',
                                         values={'money':1}, card_cost=2)
        fantasyEvent2 = FantasyEventFactory.generate()

        data = FantasyEventSerializer(fantasyEvent1).data
        assert isinstance(data,dict)

        self.assertEqual(data['fantasy_type'],'winPlainMoney')
        self.assertEqual(data['values']['money'],1)
        self.assertEqual(data['card_cost'],2)

        data2 = FantasyEventSerializer(fantasyEvent2).data
        assert isinstance(data2,dict)

        self.assertEqual(data2['fantasy_type'],fantasyEvent2.fantasy_type)
        self.assertEqual(data2['values'],fantasyEvent2.values)
        self.assertEqual(data2['card_cost'],fantasyEvent2.card_cost)