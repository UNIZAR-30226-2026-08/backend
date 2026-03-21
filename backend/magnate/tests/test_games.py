from django.test import TestCase
from django.core.management import call_command
from magnate.exceptions import *
from magnate.models import *
from magnate.games import *
from magnate.game_utils import _calculate_rent_price, _get_user_square, _build_square, _demolish_square, _calculate_net_worth
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
            phase=GameManager.ROLL_THE_DICES
        )

        self.game.players.set([self.player1, self.player2, self.player3])
        self.game.ordered_players = [self.player1.pk, self.player2.pk, self.player3.pk]
        self.game.save()

        # Create statistics for each player
        for player in [self.player1, self.player2, self.player3]:
            PlayerGameStatistic.objects.create(user=player, game=self.game)

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
            str(self.player2.pk): "001",
            str(self.player3.pk): "001"
        }
        self.game.save()
    ##########################
    ###### JAIL TESTS ##########
    ##########################

    @patch('magnate.games.random.randint')
    def test_jail_entry_on_third_double(self, mock_randint):
        self.game.streak = 2
        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.save()

        # 3 rd double
        mock_randint.side_effect = [4, 4, 5]
        
        action = ActionThrowDices(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        jail_sq = JailSquare.objects.first()
        if not jail_sq:
            raise GameLogicError("no jail square in DB")
        
        self.assertEqual(self.game.positions[str(self.player1.pk)], jail_sq.custom_id)
        self.assertEqual(self.game.jail_remaining_turns[str(self.player1.pk)], 3)
        
        self.assertEqual(self.game.active_turn_player, self.player1)
        self.assertEqual(self.game.phase, GameManager.LIQUIDATION)

    @patch('magnate.games.random.randint')
    def test_jail_exit_via_doubles(self, mock_randint):
        jail_sq = JailSquare.objects.first()

        if not jail_sq:
            raise GameLogicError("no jail square in DB")

       
        self.game.positions[str(self.player1.pk)] = jail_sq.custom_id
        self.game.jail_remaining_turns[str(self.player1.pk)] = 2
        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.save()

        # doubles and bus
        mock_randint.side_effect = [2, 2, 6]
        
        action = ActionThrowDices(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        self.assertEqual(self.game.jail_remaining_turns.get(str(self.player1.pk)), 0)
        self.assertEqual(self.game.streak, 0) 
        self.assertEqual(self.game.phase, GameManager.CHOOSE_SQUARE)

    @patch('magnate.games.random.randint')
    def test_jail_stay_on_no_doubles(self, mock_randint):
        
        jail_sq = JailSquare.objects.first()
        if not jail_sq:
            raise GameLogicError("no jail square in DB")

        self.game.positions[str(self.player1.pk)] = jail_sq.custom_id
        self.game.jail_remaining_turns[str(self.player1.pk)] = 2
        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.save()

        # no doubles
        mock_randint.side_effect = [1, 2, 3]
        
        action = ActionThrowDices(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        self.assertEqual(self.game.jail_remaining_turns[str(self.player1.pk)], 1)
        self.assertEqual(self.game.positions[str(self.player1.pk)], jail_sq.custom_id)
        # Stays in jail, phase goes to BUSINESS for management
        self.assertEqual(self.game.phase, GameManager.BUSINESS)

    @patch('magnate.games.random.randint')
    def test_jail_forced_payment_on_third_turn(self, mock_randint):
        
        jail_sq = JailSquare.objects.first()

        if not jail_sq:
            raise GameLogicError("no jail square in DB")

        self.game.positions[str(self.player1.pk)] = jail_sq.custom_id
        self.game.jail_remaining_turns[str(self.player1.pk)] = 1
        self.game.phase = GameManager.ROLL_THE_DICES
        initial_money = self.game.money[str(self.player1.pk)]
        self.game.save()

        # roll
        mock_randint.side_effect = [1, 2, 3]
        
        action = ActionThrowDices(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        self.assertEqual(self.game.money[str(self.player1.pk)], initial_money - jail_sq.bail_price)
        self.assertEqual(self.game.jail_remaining_turns[str(self.player1.pk)], 0)
        self.assertEqual(self.game.phase, GameManager.MANAGEMENT) # Moved out

    def test_jail_manual_bail_payment(self):
        
        jail_sq = JailSquare.objects.first()
        if not jail_sq:
            raise GameLogicError("no jail square in DB")

        self.game.positions[str(self.player1.pk)] = jail_sq.custom_id
        self.game.jail_remaining_turns[str(self.player1.pk)] = 2
        self.game.phase = GameManager.ROLL_THE_DICES
        initial_money = self.game.money[str(self.player1.pk)]
        self.game.save()

        action = ActionPayBail(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        self.assertEqual(self.game.money[str(self.player1.pk)], initial_money - jail_sq.bail_price)
        self.assertEqual(self.game.jail_remaining_turns[str(self.player1.pk)], 0)
        self.assertEqual(self.game.phase, GameManager.ROLL_THE_DICES) # Ready to roll free

    ##########################
    ###### BUSINESS TESTS ######
    ##########################

    def test_buy_property(self):
        self.game.phase = GameManager.MANAGEMENT
        self.game.save()
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

        self.game.phase = GameManager.MANAGEMENT
        self.game.save()

        drop_action = ActionDropPurchase(game=self.game, player=self.player1, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player1, drop_action)

        self.game.refresh_from_db()
        self.assertEqual(self.game.phase, GameManager.AUCTION)
        self.assertEqual(self.game.current_auction.square, self.property_square)

        # 2. Pujas ocultas de los jugadores
        bid_p1 = ActionBid(game=self.game, player=self.player1, amount=100)
        bid_p2 = ActionBid(game=self.game, player=self.player2, amount=300) # <- Ganador
        bid_p3 = ActionBid(game=self.game, player=self.player3, amount=250)

        async_to_sync(GameManager.process_action)(self.game, self.player1, bid_p1)
        async_to_sync(GameManager.process_action)(self.game, self.player2, bid_p2)
        async_to_sync(GameManager.process_action)(self.game, self.player3, bid_p3)

        self.game.refresh_from_db()
        auction = self.game.current_auction
        bids = auction.bids.all()
        self.assertEqual(bids.count(), 3)
        self.assertEqual(auction.bids.get(player=self.player2).amount, 300)

        result = async_to_sync(GameManager._end_auction)(self.game)

        if not isinstance(result, ResponseAuction):
            raise GameLogicError("Wrong type")
        
        self.assertEqual(result.winner.pk, self.player2.pk)
        self.assertEqual(result.final_amount, 300)

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

        result = async_to_sync(GameManager._end_auction)(self.game)

        if not isinstance(result, ResponseAuction):
            raise GameLogicError("Wrong type")
        
        self.assertIsNone(result.winner)
        self.assertEqual(result.final_amount, 0)

        self.game.refresh_from_db()
        self.assertEqual(self.game.phase, GameManager.BUSINESS)
        self.assertIsNone(self.game.current_auction)

        
        with self.assertRaises(PropertyRelationship.DoesNotExist):
            PropertyRelationship.objects.get(game=self.game, square=self.server_square)

    def test_auction_tie(self):
        if not self.property_square:
            raise GameLogicError("no property square")

        GameManager._initiate_auction(self.game, self.property_square)
        self.game.refresh_from_db()

        bid_p1 = ActionBid(game=self.game, player=self.player1, amount=300)
        bid_p2 = ActionBid(game=self.game, player=self.player2, amount=300) # Tie

        async_to_sync(GameManager.process_action)(self.game, self.player1, bid_p1)
        async_to_sync(GameManager.process_action)(self.game, self.player2, bid_p2)

        result = async_to_sync(GameManager._end_auction)(self.game)

        if not isinstance(result, ResponseAuction):
            raise GameLogicError("Wrong type")
        
        self.assertIsNone(result.winner)
        self.assertTrue(result.is_tie)
        
        with self.assertRaises(PropertyRelationship.DoesNotExist):
            PropertyRelationship.objects.get(game=self.game, square=self.property_square)

    ##################################
    ###### MOVEMENT & RENT TESTS ######
    ##################################

    def test_bridge_rent(self):
        bridges = BridgeSquare.objects.all()[:2]
        PropertyRelationship.objects.create(game=self.game, owner=self.player1, square=bridges[0])
        PropertyRelationship.objects.create(game=self.game, owner=self.player1, square=bridges[1])

        rent = _calculate_rent_price(self.game, self.player2, bridges[0])
        self.assertEqual(rent, bridges[0].rent_prices[1]) # price for 2 bridges

    def test_trade_restriction_with_houses(self):
        
        if not self.property_square:
            raise GameLogicError("no property square")

        group_squares = PropertySquare.objects.filter(group=self.property_square.group)
        rel1 = PropertyRelationship.objects.create(game=self.game, owner=self.player1, square=group_squares[0], houses=1) # Has house
        rel2 = PropertyRelationship.objects.create(game=self.game, owner=self.player2, square=self.server_square)

        self.game.phase = GameManager.BUSINESS
        self.game.save()

        proposal = ActionTradeProposal.objects.create(
            game=self.game, player=self.player1, destination_user=self.player2,
            offered_money=0, asked_money=0
        )
        proposal.offered_properties.add(rel1)
        proposal.asked_properties.add(rel2)

        with self.assertRaises(MaliciousUserInput):
            async_to_sync(GameManager.process_action)(self.game, self.player1, proposal)

    def test_calculate_net_worth(self):
        if self.property_square is None:
            raise GameLogicError("no property square")
            
        # P1 has 1000 cash, 1 property (buy_price 100), 2 houses (build_price 50 each)
        self.game.money[str(self.player1.pk)] = 1000
        PropertyRelationship.objects.create(
            game=self.game, owner=self.player1, square=self.property_square, houses=2
        )
        self.game.save()
        
        # Expected: 1000 + 100 + (2 * 50) = 1200
        nw = _calculate_net_worth(self.game, self.player1)
        expected = 1000 + self.property_square.buy_price + (2 * self.property_square.build_price)
        self.assertEqual(nw, expected)

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
        self.game.possible_destinations = {str(self.property_square.custom_id): 0}
        self.game.save()

        # movement
        action_move = ActionMoveTo(game=self.game, player=self.player2, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player2, action_move)
        
        self.game.refresh_from_db()

        # expected rent: 1 house is index 1
        expected_rent = self.property_square.rent_prices[1]
        
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
        self.assertEqual(len(self.game.possible_destinations), total_squares-1)

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

        # streak should reset, phase to roll_the_dices (next player turn), and player in jail
        self.assertEqual(self.game.streak, 0)
        self.assertEqual(self.game.phase, GameManager.LIQUIDATION)
        self.assertEqual(self.game.active_turn_player, self.player1)
        self.assertEqual(self.game.positions[str(self.player1.pk)], jail_square.custom_id)

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

    @patch('magnate.games.random.randint')
    def test_doubles_streak_full_flow(self, mock_randint):
        """
        1. P1 rolls doubles (streak 0 -> 1)
        2. P1 buys the square (MANAGEMENT -> BUSINESS)
        3. P1 ends business phase, should go back to ROLL_THE_DICES (same player)
        4. P1 rolls doubles again (streak 1 -> 2)
        5. P1 buys another square
        6. P1 ends business, back to ROLL_THE_DICES
        7. P1 rolls NO doubles (streak 2 -> 0)
        8. P1 buys, ends turn -> P2 turn
        """
        # --- FIRST ROLL: DOUBLES ---
        # d1=1, d2=1, d3=2. 1+1+2 = 4 steps. 0 -> 4 is PropertySquare (003)
        mock_randint.side_effect = [1, 1, 2] # 4 steps. Numeric bus.

        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.save()

        action = ActionThrowDices(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        self.assertEqual(self.game.streak, 1)
        self.assertEqual(self.game.phase, GameManager.MANAGEMENT)
        self.assertEqual(self.game.active_turn_player, self.player1)

        # Buy the square. Because streak > 0, it should return to ROLL_THE_DICES for P1
        current_sq = _get_user_square(self.game, self.player1).get_real_instance()
        buy_action = ActionBuySquare(game=self.game, player=self.player1, square=current_sq)
        async_to_sync(GameManager.process_action)(self.game, self.player1, buy_action)

        self.game.refresh_from_db()
        self.assertEqual(self.game.phase, GameManager.ROLL_THE_DICES)
        self.assertEqual(self.game.active_turn_player, self.player1)
        self.assertEqual(self.game.streak, 1)

        # --- SECOND ROLL: DOUBLES ---
        mock_randint.side_effect = [1, 1, 2] # 2+2+0 = 4 steps. 4 -> 8 (PropertySquare 008)

        action = ActionThrowDices(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        self.assertEqual(self.game.streak, 2)
        self.assertEqual(self.game.phase, GameManager.MANAGEMENT)

        # Drop purchase to go to Auction (or just NextPhase)
        current_sq = _get_user_square(self.game, self.player1).get_real_instance()
        drop_action = ActionDropPurchase(game=self.game, player=self.player1, square=current_sq)
        async_to_sync(GameManager.process_action)(self.game, self.player1, drop_action)

        # After auction, it goes back to ROLL_THE_DICES directly if streak > 0
        self.assertEqual(self.game.phase, GameManager.AUCTION)
        async_to_sync(GameManager._end_auction)(self.game)

        self.game.refresh_from_db()
        self.assertEqual(self.game.streak, 2)
        self.assertEqual(self.game.phase, GameManager.ROLL_THE_DICES)
        self.assertEqual(self.game.active_turn_player, self.player1)
        

        # --- THIRD ROLL: NO DOUBLES ---
        mock_randint.side_effect = [1, 3, 2] # 1+3+2 = 6 steps. 8 -> 14 (PropertySquare 014)

        action = ActionThrowDices(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        self.game.refresh_from_db()
        self.assertEqual(self.game.streak, 0)
        self.assertEqual(self.game.phase, GameManager.MANAGEMENT)

        # End turn
        next_phase_action = ActionNextPhase(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, next_phase_action) # MANAGEMENT -> BUSINESS
        self.game.refresh_from_db()
        self.assertEqual(self.game.phase, GameManager.BUSINESS)

        async_to_sync(GameManager.process_action)(self.game, self.player1, next_phase_action) # BUSINESS -> NEXT PLAYER

        self.game.refresh_from_db()
        self.assertEqual(self.game.active_turn_player, self.player2)
        self.assertEqual(self.game.phase, GameManager.ROLL_THE_DICES)
        self.assertEqual(self.game.streak, 0)

    ##########################
    ###### FANTASY TESTS ######
    ##########################

    @patch('magnate.games.FantasyEventFactory.generate')
    def test_fantasy_choose_first(self, mock_generate):
        """Landa on fantasy square and choose the first card offered"""
        # Setup initial event
        initial_event = FantasyEvent.objects.create(
            fantasy_type='winPlainMoney', 
            values={'money': 100}, 
            card_cost=50
        )
        
        self.game.phase = GameManager.CHOOSE_FANTASY
        self.game.fantasy_event = initial_event
        self.game.save()
        
        initial_money = self.game.money[str(self.player1.pk)]
        
        # Action: choose the first card (chosen_card=True)
        action = ActionChooseCard.objects.create(game=self.game, player=self.player1, chosen_card=True)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)
        
        self.game.refresh_from_db()
        self.assertEqual(self.game.money[str(self.player1.pk)], initial_money + 100)
        self.assertEqual(self.game.phase, GameManager.BUSINESS)
        self.assertIsNone(self.game.fantasy_event)

    @patch('magnate.games.FantasyEventFactory.generate')
    def test_fantasy_choose_other(self, mock_generate):
        """Land on fantasy square and choose to get another card"""
        # Setup initial event (this one should NOT be applied)
        initial_event = FantasyEvent.objects.create(
            fantasy_type='losePlainMoney', 
            values={'money': 100}, 
            card_cost=50
        )
        
        # Mock the "other" event that will be generated
        other_event = FantasyEvent(
            fantasy_type='winPlainMoney', 
            values={'money': 200}, 
            card_cost=50
        )
        mock_generate.return_value = other_event
        
        self.game.phase = GameManager.CHOOSE_FANTASY
        self.game.fantasy_event = initial_event
        self.game.save()
        
        initial_money = self.game.money[str(self.player1.pk)]
        
        # Action: choose the other card (chosen_card=False)
        action = ActionChooseCard.objects.create(game=self.game, player=self.player1, chosen_card=False)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)
        
        self.game.refresh_from_db()
        # Should have applied other_event (win 200) instead of initial_event (lose 100)
        self.assertEqual(self.game.money[str(self.player1.pk)], initial_money + 200)
        self.assertEqual(self.game.phase, GameManager.BUSINESS)
        self.assertIsNone(self.game.fantasy_event)


    ##########################
    ###### STATS TESTS ######
    ##########################

    def test_stats_walked_squares(self):
        """P1 moves to a square, walked_squares should increment"""
        self.game.phase = GameManager.CHOOSE_SQUARE
        self.game.possible_destinations = {str(self.property_square.custom_id): 5}
        self.game.save()

        action = ActionMoveTo(game=self.game, player=self.player1, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        stats = PlayerGameStatistic.objects.get(user=self.player1, game=self.game)
        self.assertEqual(stats.walked_squares, 5)

    def test_stats_lost_money_on_buy(self):
        """P1 buys a property, lost_money should increment by buy_price"""
        self.game.phase = GameManager.MANAGEMENT
        self.game.save()

        action = ActionBuySquare(game=self.game, player=self.player1, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        stats = PlayerGameStatistic.objects.get(user=self.player1, game=self.game)
        self.assertEqual(stats.lost_money, self.property_square.buy_price)

    def test_stats_rent_paid_and_received(self):
        """P2 lands on P1 property: P2 lost_money and num_paid_rents increment, P1 won_money increments"""
        PropertyRelationship.objects.create(
            game=self.game, owner=self.player1, square=self.property_square, houses=-1
        )
        self.game.phase = GameManager.CHOOSE_SQUARE
        self.game.active_phase_player = self.player2
        self.game.possible_destinations = {str(self.property_square.custom_id): 0}
        self.game.save()

        action = ActionMoveTo(game=self.game, player=self.player2, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player2, action)

        expected_rent = self.property_square.rent_prices[0]

        stats_p2 = PlayerGameStatistic.objects.get(user=self.player2, game=self.game)
        stats_p1 = PlayerGameStatistic.objects.get(user=self.player1, game=self.game)

        self.assertEqual(stats_p2.lost_money, expected_rent)
        self.assertEqual(stats_p2.num_paid_rents, 1)
        self.assertEqual(stats_p1.won_money, expected_rent)

    def test_stats_built_and_demolished_houses(self):
        """P1 builds 1 house then demolishes it: built_houses=1, demolished_houses=1"""
        group_squares = PropertySquare.objects.filter(group=self.property_square.group)
        for sq in group_squares:
            PropertyRelationship.objects.create(game=self.game, owner=self.player1, square=sq, houses=0)

        self.game.phase = GameManager.BUSINESS
        self.game.save()

        build_action = ActionBuild(game=self.game, player=self.player1, square=self.property_square, houses=1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, build_action)

        stats = PlayerGameStatistic.objects.get(user=self.player1, game=self.game)
        self.assertEqual(stats.built_houses, 1)

        demolish_action = ActionDemolish(game=self.game, player=self.player1, square=self.property_square, houses=1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, demolish_action)

        stats.refresh_from_db()
        self.assertEqual(stats.demolished_houses, 1)

    def test_stats_times_and_turns_in_jail(self):
        """P1 goes to jail via third double: times_in_jail=1. Then stays one turn: turns_in_jail=1"""
        self.game.streak = 2
        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.save()

        with patch('magnate.games.random.randint', side_effect=[4, 4, 5]):
            action = ActionThrowDices(game=self.game, player=self.player1)
            async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        stats = PlayerGameStatistic.objects.get(user=self.player1, game=self.game)
        self.assertEqual(stats.times_in_jail, 1)

        # Now stays in jail one turn (no doubles)
        self.game.refresh_from_db()
        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.save()

        with patch('magnate.games.random.randint', side_effect=[1, 2, 3]):
            action = ActionThrowDices(game=self.game, player=self.player1)
            async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        stats.refresh_from_db()
        self.assertEqual(stats.turns_in_jail, 1)

    def test_stats_turns_in_jail_forced_payment(self):
        """P1 on last jail turn pays bail: turns_in_jail increments"""
        jail_sq = JailSquare.objects.first()
        if not jail_sq:
            raise GameLogicError("no jail square in DB")

        self.game.positions[str(self.player1.pk)] = jail_sq.custom_id
        self.game.jail_remaining_turns[str(self.player1.pk)] = 1
        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.save()

        with patch('magnate.games.random.randint', side_effect=[1, 2, 3]):
            action = ActionThrowDices(game=self.game, player=self.player1)
            async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        stats = PlayerGameStatistic.objects.get(user=self.player1, game=self.game)
        self.assertEqual(stats.turns_in_jail, 1)
        self.assertEqual(stats.lost_money, jail_sq.bail_price)

    def test_stats_lost_money_on_bail_payment(self):
        """P1 manually pays bail: lost_money increments by bail_price"""
        jail_sq = JailSquare.objects.first()
        if not jail_sq:
            raise GameLogicError("no jail square in DB")

        self.game.positions[str(self.player1.pk)] = jail_sq.custom_id
        self.game.jail_remaining_turns[str(self.player1.pk)] = 2
        self.game.phase = GameManager.ROLL_THE_DICES
        self.game.save()

        action = ActionPayBail(game=self.game, player=self.player1)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        stats = PlayerGameStatistic.objects.get(user=self.player1, game=self.game)
        self.assertEqual(stats.lost_money, jail_sq.bail_price)

    def test_stats_trades(self):
        """P1 and P2 complete a trade: num_trades increments for both"""
        squares = PropertySquare.objects.filter(buy_price__gt=0)[:2]
        rel1 = PropertyRelationship.objects.create(game=self.game, owner=self.player1, square=squares[0], houses=-1)
        rel2 = PropertyRelationship.objects.create(game=self.game, owner=self.player2, square=squares[1], houses=-1)

        self.game.phase = GameManager.BUSINESS
        self.game.save()

        proposal = ActionTradeProposal.objects.create(
            game=self.game, player=self.player1, destination_user=self.player2,
            offered_money=10, asked_money=50
        )
        proposal.offered_properties.add(rel1)
        proposal.asked_properties.add(rel2)

        async_to_sync(GameManager.process_action)(self.game, self.player1, proposal)
        self.game.refresh_from_db()

        answer = ActionTradeAnswer.objects.create(
            game=self.game, player=self.player2, proposal=proposal, choose=True
        )
        async_to_sync(GameManager.process_action)(self.game, self.player2, answer)

        stats_p1 = PlayerGameStatistic.objects.get(user=self.player1, game=self.game)
        stats_p2 = PlayerGameStatistic.objects.get(user=self.player2, game=self.game)
        self.assertEqual(stats_p1.num_trades, 1)
        self.assertEqual(stats_p2.num_trades, 1)
        self.assertEqual(stats_p1.lost_money, 10)
        self.assertEqual(stats_p1.won_money, 50)
        self.assertEqual(stats_p2.lost_money, 50)
        self.assertEqual(stats_p2.won_money, 10)
    
    def test_stats_num_mortgages(self):
        """P1 sets and unsets mortgage: num_mortgages=2"""
        PropertyRelationship.objects.create(
            game=self.game, owner=self.player1, square=self.property_square, houses=-1
        )
        self.game.phase = GameManager.BUSINESS
        self.game.save()

        action_set = ActionMortgageSet(game=self.game, player=self.player1, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action_set)

        action_unset = ActionMortgageUnset(game=self.game, player=self.player1, square=self.property_square)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action_unset)

        stats = PlayerGameStatistic.objects.get(user=self.player1, game=self.game)
        self.assertEqual(stats.num_mortgages, 1)

    def test_stats_num_fantasy_events(self):
        """P1 triggers a fantasy event: num_fantasy_events increments"""
        event = FantasyEvent.objects.create(
            fantasy_type='winPlainMoney',
            values={'money': 100},
            card_cost=50
        )
        self.game.phase = GameManager.CHOOSE_FANTASY
        self.game.fantasy_event = event
        self.game.save()

        action = ActionChooseCard.objects.create(game=self.game, player=self.player1, chosen_card=True)
        async_to_sync(GameManager.process_action)(self.game, self.player1, action)

        stats = PlayerGameStatistic.objects.get(user=self.player1, game=self.game)
        self.assertEqual(stats.num_fantasy_events, 1)

