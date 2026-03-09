from django.test import TestCase
from django.core.management import call_command
from magnate.exceptions import *
from magnate.models import *
from magnate.games import *
from magnate.serializers import *
from django.utils import timezone
from asgiref.sync import async_to_sync
from unittest.mock import patch
from magnate.exceptions import *


class GamesTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        call_command('init_boards')

    def setUp(self):
        self.player1 = CustomUser.objects.create(username="p1", email="p1@gmail.com")
        self.player2 = CustomUser.objects.create(username="p2", email="p2@gmail.com")
        self.player3 = CustomUser.objects.create(username="p3", email="p3@gmail.com")
        
        self.game = Game.objects.create(
            datetime=timezone.now(),
            active_phase_player=self.player1,
            active_turn_player=self.player1,
            phase=GameManager.MANAGEMENT
        )

        self.game.players.set([self.player1, self.player2, self.player3])

        self.property_square = PropertySquare.objects.filter(buy_price__gt=0).first()
        if self.property_square is None:
            raise GameLogicError("no property square")

        self.server_square = ServerSquare.objects.filter(buy_price__gt=0).first()

        self.game.money = {
            str(self.player1.pk): 1500, 
            str(self.player2.pk): 1500,
            str(self.player3.pk): 1500
        }
        self.game.positions = {
            str(self.player1.pk): self.property_square.custom_id, 
            str(self.player2.pk): 0,
            str(self.player3.pk): 0
        }
        self.game.save()

    ##########################
    ###### BUSINESS TESTS ######
    ##########################

    def test_buy_property(self):
        action = ActionBuySquare(game=self.game, player=self.player1, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        self.assertEqual(self.game.phase, GameManager.BUSINESS)
        
        rel = PropertyRelationship.objects.get(game=self.game, square=self.property_square)
        self.assertEqual(rel.owner, self.player1)
        if self.property_square is None:
            raise GameLogicError("no property square") 
        
        expected_money = 1500 - self.property_square.buy_price
        self.assertEqual(self.game.money[str(self.player1.pk)], expected_money)


    def test_build_and_demolish_houses(self):
        if self.property_square is None:
            raise GameLogicError("no property square")
        
        group_id = self.property_square.group
        group_squares = PropertySquare.objects.filter(group=group_id)

        # all props to p1 to build
        for sq in group_squares:
            PropertyRelationship.objects.create(game=self.game, owner=self.player1, square=sq, houses=0)

        self.game.phase = GameManager.BUSINESS
        self.game.save()

        build_action = ActionBuild(game=self.game, player=self.player1, square=self.property_square, houses=1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, build_action)

        rel = PropertyRelationship.objects.get(game=self.game, square=self.property_square)
        self.assertEqual(rel.houses, 1)

        demolish_action = ActionDemolish(game=self.game, player=self.player1, square=self.property_square, houses=1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, demolish_action)

        rel.refresh_from_db()
        self.assertEqual(rel.houses, 0)

    def test_set_and_unset_mortgage(self):

        PropertyRelationship.objects.create(game=self.game, owner=self.player1, square=self.property_square, houses=-1)
        self.game.phase = GameManager.BUSINESS
        self.game.save()

        # set
        action_set = ActionMortgageSet(game=self.game, player=self.player1, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action_set)

        rel = PropertyRelationship.objects.get(game=self.game, square=self.property_square)
        self.assertTrue(rel.mortgage)

        # unset
        action_unset = ActionMortgageUnset(game=self.game, player=self.player1, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action_unset)

        rel.refresh_from_db()
        self.assertFalse(rel.mortgage)

    ##########################
    ###### ACUTION  TESTS ######
    ##########################
    def test_auction_complete_flow(self):
        """
        1. P1 do not purchase
        2. Initiate auction
        3. Players bid
        4. Terminate
        """

        if self.property_square is None:
            raise GameLogicError("no property square")

        drop_action = ActionDropPurchase(game=self.game, player=self.player1, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player1, drop_action)

        self.game.refresh_from_db()
        self.assertEqual(self.game.phase, GameManager.AUCTION)
        self.assertEqual(self.game.auction_state["square_id"], self.property_square.custom_id)

        # 2. Pujas ocultas de los jugadores
        bid_p1 = ActionBid(game=self.game, player=self.player1, amount=100)
        bid_p2 = ActionBid(game=self.game, player=self.player2, amount=300) # <- Ganador
        bid_p3 = ActionBid(game=self.game, player=self.player3, amount=250)

        async_to_sync(GameManager.process_action)(self.game, self.player1, bid_p1)
        async_to_sync(GameManager.process_action)(self.game, self.player2, bid_p2)
        async_to_sync(GameManager.process_action)(self.game, self.player3, bid_p3)

        self.game.refresh_from_db()
        bids = self.game.auction_state["bids"]
        self.assertIn(str(self.player1.pk), bids)
        self.assertIn(str(self.player2.pk), bids)
        self.assertIn(str(self.player3.pk), bids)
        self.assertEqual(bids[str(self.player2.pk)], 300)

        result_dict = async_to_sync(GameManager._end_auction)(self.game)

        self.assertEqual(result_dict["winner"], self.player2.pk)
        self.assertEqual(result_dict["amount"], 300)

        self.game.refresh_from_db()
        self.assertEqual(self.game.phase, GameManager.BUSINESS)

        rel = PropertyRelationship.objects.get(game=self.game, square=self.property_square)
        self.assertEqual(rel.owner, self.player2)
        self.assertEqual(self.game.money[str(self.player2.pk)], 1500 - 300)

    def test_auction_desert(self):
        if self.server_square is None:
            raise GameLogicError("no server square")

        GameManager._initiate_auction(self.game, self.server_square)
        
        self.game.refresh_from_db()
        self.assertEqual(self.game.phase, GameManager.AUCTION)

        result_dict = async_to_sync(GameManager._end_auction)(self.game)

        self.assertIsNone(result_dict["winner"])
        self.assertEqual(result_dict["amount"], 0)

        self.game.refresh_from_db()
        self.assertEqual(self.game.phase, GameManager.BUSINESS)
        self.assertEqual(self.game.auction_state, {})
        
        with self.assertRaises(PropertyRelationship.DoesNotExist):
            PropertyRelationship.objects.get(game=self.game, square=self.server_square)


    ##################################
    ###### MOVEMENT & RENT TESTS ######
    ##################################

    def test_pay_rent_on_owned_property(self):
        """
        P2 lands in a P1 property with 1 house
        Calculate rent and pay it to P1
        """
        if self.property_square is None:
            raise GameLogicError("no property square")

        PropertyRelationship.objects.create(
            game=self.game, owner=self.player1, square=self.property_square, houses=1
        )
        
        self.game.phase = GameManager.CHOOSE_SQUARE
        self.game.active_phase_player = self.player2
        self.game.possible_destinations = [self.property_square.custom_id]
        self.game.save()

        # movement
        action_move = ActionMoveTo(game=self.game, player=self.player2, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player2, action_move)
        
        self.game.refresh_from_db()

        # expected rent
        expected_rent = self.property_square.rent_prices[2]
        
        self.assertEqual(self.game.money[str(self.player2.pk)], 1500 - expected_rent)
        self.assertEqual(self.game.money[str(self.player1.pk)], 1500 + expected_rent)

    def test_take_tram(self):
        """
        P1 taking tram
        """
        tram_square_1 = TramSquare.objects.first()
        tram_square_2 = TramSquare.objects.last()
        
        if not tram_square_1 or not tram_square_2:
            raise GameLogicError("No tram squares in DB")

        self.game.positions[str(self.player1.pk)] = tram_square_1.custom_id
        self.game.phase = GameManager.MANAGEMENT
        self.game.save()

        action = ActionTakeTram(game=self.game, player=self.player1, square=tram_square_2)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        
        # check new position
        self.assertEqual(self.game.positions[str(self.player1.pk)], tram_square_2.custom_id)
        self.assertEqual(self.game.money[str(self.player1.pk)], 1500 - tram_square_2.buy_price)

    def test_not_take_tram(self):
        """
        P1 not taking tram
        """
        tram_square_1 = TramSquare.objects.first()
        tram_square_2 = TramSquare.objects.last()
        
        if not tram_square_1 or not tram_square_2:
            raise GameLogicError("No tram squares in DB")

        self.game.positions[str(self.player1.pk)] = tram_square_1.custom_id
        self.game.phase = GameManager.MANAGEMENT
        self.game.save()

        # execute action
        action = ActionDoNotTakeTram(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        
        # verify no changes in position/money and phase advances
        self.assertEqual(self.game.positions[str(self.player1.pk)], tram_square_1.custom_id)
        self.assertEqual(self.game.money[str(self.player1.pk)], 1500)
        self.assertEqual(self.game.phase, GameManager.BUSINESS)


    ##########################
    ###### TRADING TESTS ######
    ##########################

    def test_trade_proposal_and_acceptance(self):
        """p1 and p2 exchange multiple properties and money"""
        squares = PropertySquare.objects.filter(buy_price__gt=0)[:4]
        
        rel1 = PropertyRelationship.objects.create(game=self.game, owner=self.player1, square=squares[0], houses=-1)
        rel2 = PropertyRelationship.objects.create(game=self.game, owner=self.player1, square=squares[1], houses=-1)
        
        rel3 = PropertyRelationship.objects.create(game=self.game, owner=self.player2, square=squares[2], houses=-1)
        rel4 = PropertyRelationship.objects.create(game=self.game, owner=self.player2, square=squares[3], houses=-1)
        
        self.game.phase = GameManager.BUSINESS
        self.game.save()

        # p1 offers rel1, rel2 and 200 money for rel3, rel4 and 300 money
        proposal = ActionTradeProposal.objects.create(
            game=self.game, player=self.player1, destination_user=self.player2,
            offered_money=200, asked_money=300
        )
        proposal.offered_properties.set([rel1, rel2])
        proposal.asked_properties.set([rel3, rel4])
        
        async_to_sync(GameManager.process_action)(self.game, self.player1, proposal)
        self.game.refresh_from_db()
        
        self.assertEqual(self.game.phase, GameManager.PROPOSAL_ACCEPTANCE)
        self.assertEqual(self.game.active_phase_player, self.player2)
        
        # p2 accepts trade
        answer = ActionTradeAnswer.objects.create(
            game=self.game, player=self.player2, proposal=proposal, choose=True
        )
        async_to_sync(GameManager.process_action)(self.game, self.player2, answer)
        
        self.game.refresh_from_db()
        rel1.refresh_from_db()
        rel2.refresh_from_db()
        rel3.refresh_from_db()
        rel4.refresh_from_db()
        
        # verify money exchange
        self.assertEqual(self.game.money[str(self.player1.pk)], 1500 - 200 + 300) 
        self.assertEqual(self.game.money[str(self.player2.pk)], 1500 - 300 + 200) 
        
        # verify transfer of properties
        self.assertEqual(rel1.owner, self.player2)
        self.assertEqual(rel2.owner, self.player2)
        self.assertEqual(rel3.owner, self.player1)
        self.assertEqual(rel4.owner, self.player1)
        
        # verify phase and active player reverted to p1
        self.assertEqual(self.game.phase, GameManager.BUSINESS)
        self.assertEqual(self.game.active_phase_player, self.player1)


    def test_trade_proposal_rejection(self):
        """p1 proposes a trade but p2 rejects it"""
        squares = PropertySquare.objects.filter(buy_price__gt=0)[:2]
        
        rel1 = PropertyRelationship.objects.create(game=self.game, owner=self.player1, square=squares[0], houses=-1)
        rel2 = PropertyRelationship.objects.create(game=self.game, owner=self.player2, square=squares[1], houses=-1)
        
        self.game.phase = GameManager.BUSINESS
        self.game.save()

        proposal = ActionTradeProposal.objects.create(
            game=self.game, player=self.player1, destination_user=self.player2,
            offered_money=100, asked_money=500
        )
        proposal.offered_properties.add(rel1)
        proposal.asked_properties.add(rel2)
        
        async_to_sync(GameManager.process_action)(self.game, self.player1, proposal)
        self.game.refresh_from_db()
        
        # p2 rejects trade
        answer = ActionTradeAnswer.objects.create(
            game=self.game, player=self.player2, proposal=proposal, choose=False
        )
        async_to_sync(GameManager.process_action)(self.game, self.player2, answer)
        
        self.game.refresh_from_db()
        rel1.refresh_from_db()
        rel2.refresh_from_db()
        
        # verify money is intact
        self.assertEqual(self.game.money[str(self.player1.pk)], 1500)
        self.assertEqual(self.game.money[str(self.player2.pk)], 1500)
        
        # verify ownership is intact
        self.assertEqual(rel1.owner, self.player1)
        self.assertEqual(rel2.owner, self.player2)
        
        # phase and turn return to p1 normally
        self.assertEqual(self.game.phase, GameManager.BUSINESS)
        self.assertEqual(self.game.active_phase_player, self.player1)

    
    #################################
    ###### MOVEMENT & DICE TESTS ######
    #################################

    @patch('magnate.games.random.randint')
    def test_roll_dices_bus_icon(self, mock_randint):
        """roll with bus icon (d3 > 3). player can choose between 3 paths"""
        # d1=2, d2=3, d3=6 (bus icon)
        mock_randint.side_effect = [2, 3, 6] 
        
        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.save()

        action = ActionThrowDices(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        
        # bus icon gives 3 options: d1, d2, d1+d2 -> 2, 3, 5 steps
        # multiple destinations means phase goes to CHOOSE_SQUARE
        self.assertEqual(self.game.phase, GameManager.CHOOSE_SQUARE)
        self.assertEqual(len(self.game.possible_destinations), 3)
        self.assertEqual(self.game.streak, 0)

    @patch('magnate.games.random.randint')
    def test_roll_dices_triples(self, mock_randint):
        """roll triples. player can choose any square on the board"""
        # d1=2, d2=2, d3=2 (numeric bus matching d1 and d2)
        mock_randint.side_effect = [2, 2, 2] 
        
        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.save()

        action = ActionThrowDices(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        
        # total destinations should equal total squares on the board
        if self.property_square is None:
            raise GameLogicError("no property square")
        
        total_squares = BaseSquare.objects.filter(board=self.property_square.board).count()
        
        self.assertEqual(self.game.phase, GameManager.CHOOSE_SQUARE)
        self.assertEqual(len(self.game.possible_destinations), total_squares)

    @patch('magnate.games.random.randint')
    def test_roll_dices_doubles_streak(self, mock_randint):
        """roll doubles adds to streak, third double sends to jail"""
        # first double
        mock_randint.side_effect = [4, 4, 6] # double, non-numeric bus
        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.save()

        action = ActionThrowDices(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)
        
        self.game.refresh_from_db()
        self.assertEqual(self.game.streak, 1)
        
        # force 2 doubles streak manually for test speed
        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.streak = 2
        self.game.save()

        # third double
        mock_randint.side_effect = [3, 3, 5] 
        action = ActionThrowDices(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        
        jail_square = JailSquare.objects.first()
        if not jail_square:
            raise GameLogicError("no jail square in DB")

        # streak should reset, phase to liquidation (per jail rules), and player in jail
        self.assertEqual(self.game.streak, 0)
        self.assertEqual(self.game.phase, GameManager.LIQUIDATION)
        self.assertEqual(self.game.positions[str(self.player1.pk)] if str(self.player1.pk) in self.game.positions else self.game.positions[str(self.player1.pk)], jail_square.custom_id)


    ##########################
    ###### MALICIOUS TESTS ######
    ##########################

    def test_trade_proposal_malicious_unowned_properties(self):
        """p1 tries to trade a property they don't own, raises error"""
        squares = PropertySquare.objects.filter(buy_price__gt=0)[:2]
        
        # p2 owns both properties, p1 owns nothing
        rel1 = PropertyRelationship.objects.create(game=self.game, owner=self.player2, square=squares[0], houses=-1)
        
        self.game.phase = GameManager.BUSINESS
        self.game.save()

        proposal = ActionTradeProposal.objects.create(
            game=self.game, player=self.player1, destination_user=self.player2,
            offered_money=0, asked_money=0
        )
        
        # p1 illegally tries to offer p2's property
        proposal.offered_properties.add(rel1)
        
        # process_action should catch it and raise MaliciousUserInput
        with self.assertRaises(MaliciousUserInput):
            async_to_sync(GameManager.process_action)(self.game, self.player1, proposal)