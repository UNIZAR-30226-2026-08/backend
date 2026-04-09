## This file contains the logic of an AI agent based on the calculation of
## the expected value (EV) of a move.
from unittest.mock import Base
from redis.retry import T
import random
from .serializers import *

from magnate.exceptions import *
from magnate.models import *
from magnate.game_utils import (
    _get_relationship, _get_user_square, _get_square_by_custom_id,
    _get_possible_destinations_ids, _compute_dice_combinations
)

################################################################################
############################### CONSTANTS ######################################
################################################################################

EPSILON = {
    "very_easy": 1.0,   # 100% random
    "easy":      0.8,
    "medium":    0.6,
    "hard":      0.4,
    "very_hard": 0.2,
    "expert":    0.0,   # 100% EV-based
}

PROB_CAER = 1 / 54       # Probability of landing on a square (excluding jail)
CTE_FANTASIA = 0.0       # Default neutral value for unknown fantasy cards
CTE_SUBASTA_ROI = 0.75   # Maximum bid capped at 75% of EV to ensure ROI
TOTAL_TURNS = 500         # Dynamic baseline, multiplied by other players

class Agent:
    """
    AI Agent that calculates the Expected Value (EV) of possible actions 
    and chooses the optimal move based on its assigned difficulty level (epsilon).
    Bot level options are "very_easy", "easy", "medium", "hard", "very_hard", and "expert".
    """

    ################################################################################
    ############################### CORE LOGIC #####################################
    ################################################################################

    def __init__(self, game: Game, user: Bot, level: str):
        if level not in EPSILON:
            raise InvalidBotLevel(game, level)
        self.epsilon = EPSILON[level]
        self.game = game
        self.user = user

    def choose_action(self) -> Action | None:
        """
        Retrieves all valid actions for the current phase and selects one.
        Uses epsilon-greedy strategy: random action or the one with the highest EV.
        """
        possible_actions = self._get_possible_actions()
        if len(possible_actions) == 0:
            return None
        #elif random.random() < self.epsilon:
        #    return random.choice(possible_actions)
        #else:
        #    return max(possible_actions, key=self._ev_action)
        
        print(f"\n[DEBUG] Fase: {self.game.phase} | Jugador: {self.user.username}")
        for action in possible_actions:
            ev = self._ev_action(action)
            # Imprime el tipo de acción y su valor esperado
            datos_bonitos = GeneralActionSerializer(action).data
            print(f"-> {action.__class__.__name__} | EV: {ev:.2f} | Datos: {datos_bonitos}")
        
        if random.random() < self.epsilon:
            chosen = random.choice(possible_actions)
            print(f"[DEBUG] Elegida por RANDOM: {type(chosen).__name__}\n")
            return chosen
        else:
            chosen = max(possible_actions, key=self._ev_action)
            print(f"[DEBUG] Elegida por MEJOR EV: {type(chosen).__name__} (EV: {self._ev_action(chosen):.2f})\n")
            return chosen

    ################################################################################
    ########################## ACTION GENERATORS ###################################
    ################################################################################

    def _get_possible_actions(self) -> list[Action]:
        """
        Dispatches to the specific action generator based on the current game phase.
        """
        phase = self.game.phase
        if phase == Game.GamePhase.roll_the_dices:
            return self._get_possible_actions_roll_the_dices()
        elif phase == Game.GamePhase.choose_square:
            return self._get_possible_actions_choose_square()
        elif phase == Game.GamePhase.choose_fantasy:
            return self._get_possible_actions_choose_fantasy()
        elif phase == Game.GamePhase.management:
            return self._get_possible_actions_management()
        elif phase == Game.GamePhase.business:
            return self._get_possible_actions_business()
        elif phase == Game.GamePhase.liquidation:
            return self._get_possible_actions_liquidation()
        elif phase == Game.GamePhase.proposal_acceptance:
            return self._get_possible_actions_proposal_acceptance()
        elif phase == Game.GamePhase.auction:
            return self._get_possible_actions_auction()
        elif phase == Game.GamePhase.end_game:
            return []
    
        raise GameLogicError(f"Agent: unrecognised phase {phase}")

    def _get_possible_actions_roll_the_dices(self) -> list[Action]:
        """Generates actions for the dice rolling phase, including paying bail if in jail."""
        actions = []
        remaining = self.game.jail_remaining_turns.get(str(self.user.pk), 0)
    
        if remaining > 0:
            jail_sq = _get_user_square(self.game, self.user).get_real_instance()
            money = self.game.money[str(self.user.pk)]
            if isinstance(jail_sq, JailSquare) and money >= jail_sq.bail_price:
                actions.append(ActionPayBail(game=self.game, player=self.user))
    
        actions.append(ActionThrowDices(game=self.game, player=self.user))
        return actions

    def _get_possible_actions_choose_square(self) -> list[Action]:
        """Generates movement actions for the available destinations."""
        destinations = self.game.possible_destinations
        if not destinations:
            raise GameLogicError("Agent: choose_square phase but no possible_destinations")
    
        return [
            ActionMoveTo(game=self.game, player=self.user, square=_get_square_by_custom_id(d))
            for d in destinations
        ]
    
    def _get_possible_actions_choose_fantasy(self) -> list[Action]:
        """Generates actions to choose a fantasy card (revealed if affordable, or hidden)."""
        actions = []
        fantasy_event = self.game.fantasy_event
        money = self.game.money[str(self.user.pk)]
    
        can_afford_shown = (
            fantasy_event is not None
            and fantasy_event.card_cost is not None
            and money >= fantasy_event.card_cost
        )
    
        if can_afford_shown:
            actions.append(ActionChooseCard(game=self.game, player=self.user, chosen_revealed_card=True))
    
        actions.append(ActionChooseCard(game=self.game, player=self.user, chosen_revealed_card=False))
        return actions
    
    def _get_possible_actions_management(self) -> list[Action]:
        """Generates actions for the management phase (buy, drop, or take tram)."""
        actions = []
        current_square = _get_user_square(self.game, self.user).get_real_instance()
        prop_rel = _get_relationship(self.game, current_square)
        money = self.game.money[str(self.user.pk)]
    
        if isinstance(current_square, TramSquare):
            actions.append(ActionNextPhase(game=self.game, player=self.user))
            other_trams = TramSquare.objects.exclude(custom_id=current_square.custom_id)
            if money >= current_square.buy_price:
                for tram in other_trams:
                        actions.append(ActionTakeTram(game=self.game, player=self.user, square=tram))
            return actions
    
        is_buyable = isinstance(current_square, (PropertySquare, ServerSquare, BridgeSquare))
        is_unowned = prop_rel is None
    
        if is_buyable and is_unowned:
            if money >= current_square.buy_price:
                actions.append(ActionBuySquare(game=self.game, player=self.user, square=current_square))
            actions.append(ActionDropPurchase(game=self.game, player=self.user, square=current_square))
        else:
            actions.append(ActionNextPhase(game=self.game, player=self.user))
    
        return actions

    def _get_possible_actions_business(self) -> list[Action]:
        """Generates actions for the business phase (build, demolish, mortgage, trade)."""
        actions = []
        money = self.game.money[str(self.user.pk)]
        owned = PropertyRelationship.objects.filter(game=self.game, owner=self.user).select_related('square')
    
        for rel in owned:
            square = rel.square.get_real_instance()
    
            if (isinstance(square, PropertySquare) and 0 <= rel.houses < 5 
                and not rel.mortgage and square.build_price and money >= square.build_price):

                user_group_rels = PropertyRelationship.objects.filter(
                    game=self.game, 
                    owner=self.user, 
                    square__propertysquare__group=square.group
                )

                group_squares_count = PropertySquare.objects.filter(
                    board=square.board, 
                    group=square.group
                ).count()

                if user_group_rels.count() == group_squares_count and not user_group_rels.filter(mortgage=True).exists(): # check user has full group and none of em are mortgaged

                    group_min = (PropertyRelationship.objects
                        .filter(game=self.game, owner=self.user, square__propertysquare__group=square.group)
                        .exclude(square=rel.square).order_by('houses').values_list('houses', flat=True).first())
                    if group_min is None or rel.houses <= group_min:
                        actions.append(ActionBuild(game=self.game, player=self.user, square=rel.square, houses=1))
    
            if isinstance(square, PropertySquare) and rel.houses > 0 and not rel.mortgage:
                group_max = (PropertyRelationship.objects
                    .filter(game=self.game, owner=self.user, square__propertysquare__group=square.group)
                    .exclude(square=rel.square).order_by('-houses').values_list('houses', flat=True).first())
                if group_max is None or rel.houses >= group_max:
                    actions.append(ActionDemolish(game=self.game, player=self.user, square=rel.square, houses=1))
    
            if not rel.mortgage and isinstance(square, (PropertySquare, BridgeSquare, ServerSquare)):
                can_mortgage = True
                
                if isinstance(square, PropertySquare):
                    group_has_houses = PropertyRelationship.objects.filter(
                        game=self.game, 
                        owner=self.user, 
                        square__propertysquare__group=square.group,
                        houses__gt=0
                    ).exists()  # check if some of the group has houses built
                    
                    if group_has_houses:
                        can_mortgage = False
                
                if can_mortgage:
                    actions.append(ActionMortgageSet(game=self.game, player=self.user, square=rel.square))
    
            if rel.mortgage and square.buy_price and money >= square.buy_price // 2:
                actions.append(ActionMortgageUnset(game=self.game, player=self.user, square=rel.square))
    

        bot_db = Bot.objects.get(pk=self.user.pk)
        if not bot_db.has_proposed_trade:
            trade = self._get_random_trade_proposal(money)
            if trade is not None:
                actions.append(trade)
    
        actions.append(ActionNextPhase(game=self.game, player=self.user))
        return actions
        
    def _get_possible_actions_liquidation(self) -> list[Action]:
        """Generates actions to raise funds during liquidation (demolish, mortgage, or surrender)."""
        actions = []
        owned = PropertyRelationship.objects.filter(game=self.game, owner=self.user).select_related('square')
    
        for rel in owned:
            square = rel.square.get_real_instance()
    
            if isinstance(square, PropertySquare) and rel.houses > 0:
                actions.append(ActionDemolish(game=self.game, player=self.user, square=rel.square, houses=1))
    
            if (not rel.mortgage and isinstance(square, (PropertySquare, BridgeSquare, ServerSquare))
                and (not isinstance(square, PropertySquare) or rel.houses <= 0)):
                actions.append(ActionMortgageSet(game=self.game, player=self.user, square=rel.square))
    
        money = self.game.money[str(self.user.pk)]
    
        if not actions:
            actions.append(ActionSurrender(game=self.game, player=self.user))
        elif money > 0:
            actions.append(ActionNextPhase(game=self.game, player=self.user))
    
        return actions
   
    def _get_possible_actions_proposal_acceptance(self) -> list[Action]:
        """Generates actions to either accept or reject a trade proposal."""
        actions = []
        proposal = self.game.proposal
        money = self.game.money[str(self.user.pk)]
        offering_money = self.game.money[str(proposal.player.pk)]
    
        if proposal.asked_money <= money and proposal.offered_money <= offering_money:
            actions.append(ActionTradeAnswer(game=self.game, player=self.user, choose=True, ))
    
        actions.append(ActionTradeAnswer(game=self.game, player=self.user, choose=False))
        return actions
    
    def _get_possible_actions_auction(self) -> list[Action]:
        """Generates strategic bid actions respecting the maximum willing to pay and safety reserve."""
        auction = self.game.current_auction
        if auction is None:
            raise GameLogicError("Agent: auction phase but no current_auction")
    
        money = self.game.money[str(self.user.pk)]
        is_jailed = self.game.jail_remaining_turns.get(str(self.user.pk), 0) > 0
        already_bid = str(self.user.pk) in auction.bids
        dropped = ActionDropPurchase.objects.filter(game=self.game, player=self.user, square=auction.square).exists()
    
        pass_bid = ActionBid(game=self.game, player=self.user, amount=0)
    
        if dropped or money <= 0 or is_jailed or already_bid:
            return [pass_bid]
    
        square_instance = auction.square.get_real_instance()
        max_bid = self._max_willing_to_pay(square_instance)

        if max_bid <= 0:
            return [pass_bid]

        high = max(1, max_bid)
    
        unique_bids = {0, high}

        return [ActionBid(game=self.game, player=self.user, amount=amt) for amt in sorted(unique_bids)]

    def _get_random_trade_proposal(self, money: int) -> Action | None:
        """Helper to generate and evaluate up to 5 random trade proposals."""
        def is_tradable(rel):
            sq = rel.square.get_real_instance()
            if not isinstance(sq, PropertySquare):
                return True
            return not PropertyRelationship.objects.filter(
                game=self.game, 
                square__propertysquare__group=sq.group, 
                houses__gt=0
            ).exists()
        
        opponents = self.game.players.exclude(pk=self.user.pk)
        if not opponents.exists():
            return None

        my_properties = [rel for rel in PropertyRelationship.objects.filter(game=self.game, owner=self.user).select_related('square') if is_tradable(rel)]        
        best_trade_params = None
        
        best_ev = float('-inf')
        max_offer = 0
        for _ in range(5):
            target = random.choice(opponents)
            their_properties = [rel for rel in PropertyRelationship.objects.filter(game=self.game, owner=target).select_related('square') if is_tradable(rel)]
            if not their_properties:
                continue

            wanted_rel = random.choice(their_properties)
            wanted_sq = wanted_rel.square.get_real_instance()

            offered_sqs = []
            offer_rel = None
            offered_money = 0
            
            if my_properties and random.choice([True, False]):
                offer_rel = random.choice(my_properties)
                offered_sqs.append(offer_rel.square.get_real_instance())
            else:
                max_offer = int(self._ev_buying(wanted_sq) * 0.8)
                if max_offer > 0 and money > 0:
                    offered_money = random.randint(min(max_offer, money)//2, min(max_offer, money))
                else:
                    offered_money = 0

            if not offered_sqs and offered_money == 0:
                continue

            my_benefit = self._evaluate_trade_net_benefit(self.user, [wanted_sq], offered_sqs, 0, offered_money)
            rival_benefit = self._evaluate_trade_net_benefit(target, offered_sqs, [wanted_sq], offered_money, 0)

            ev_intercambio = my_benefit - (rival_benefit / opponents.count())

            if ev_intercambio > best_ev:
                best_ev = ev_intercambio
                best_trade_params = {
                    'target': target,
                    'wanted_rel': wanted_rel,
                    'offer_rel': offer_rel,
                    'offered_money': offered_money
                }
                
        if not best_trade_params:
            return None
        
        final_trade = ActionTradeProposal.objects.create(
            game=self.game, 
            player=self.user, 
            destination_user=best_trade_params['target'], 
            offered_money=best_trade_params['offered_money'], 
            asked_money=0
        )
        final_trade.asked_properties.add(best_trade_params['wanted_rel'])
        if best_trade_params['offer_rel']:
            final_trade.offered_properties.add(best_trade_params['offer_rel'])
            
        return final_trade
        
        
    ################################################################################
    ############################### EV DISPATCHER ##################################
    ################################################################################
    
    def _ev_action(self, action: Action) -> float:
        """
        Top-level EV dispatcher. Routes the action to its specific expected value calculator.
        Higher return value indicates a better strategic move.
        """
        if isinstance(action, ActionThrowDices):
            return 0.0
        elif isinstance(action, ActionPayBail):
            jail_sq = _get_user_square(self.game, self.user).get_real_instance()
            coste = float(jail_sq.bail_price) if isinstance(jail_sq, JailSquare) and jail_sq.bail_price else 0.0
            return self._ev_exit_jail() - coste
        elif isinstance(action, ActionMoveTo):
            return self._ev_square(action.square.get_real_instance())
        elif isinstance(action, ActionChooseCard):
            return CTE_FANTASIA
        elif isinstance(action, ActionTakeTram):
            dest = action.square.get_real_instance()
            coste = dest.buy_price if dest.buy_price else 0
            return self._ev_next_12_squares(dest) - float(coste)
        elif isinstance(action, ActionNextPhase):
            current_sq = _get_user_square(self.game, self.user).get_real_instance()
            return self._ev_next_12_squares(current_sq) if isinstance(current_sq, TramSquare) else 0.0
        elif isinstance(action, ActionBuySquare):
            return self._ev_buying(action.square.get_real_instance())
        elif isinstance(action, ActionDropPurchase):
            return 0.0
        elif isinstance(action, ActionBuild):
            return self._ev_build(action.square.get_real_instance())
        elif isinstance(action, ActionDemolish):
            return self._ev_demolish(action.square.get_real_instance())
        elif isinstance(action, ActionMortgageSet):
            return self._ev_mortgage_set(action.square.get_real_instance())
        elif isinstance(action, ActionMortgageUnset):
            return self._ev_mortgage_unset(action.square.get_real_instance())
        elif isinstance(action, ActionBid):
            return self._ev_bid(action.amount)
        elif isinstance(action, ActionSurrender):
            return -float('inf')
        elif isinstance(action, ActionTradeAnswer):
            return self._ev_trade_answer(action.choose)
        elif isinstance(action, ActionTradeProposal):
            return self._ev_trade_proposal(action)
    
        return 0.0

    ################################################################################
    ############################### EV CALCULATORS #################################
    ################################################################################

    def _ev_square(self, square: BaseSquare) -> float:
        """Expected value of landing on a given square. Positive is good, negative is bad."""
        if isinstance(square, (PropertySquare, ServerSquare, BridgeSquare)):
            return self._ev_landing_on_buyable(square)
        elif isinstance(square, TramSquare):
            return 0.0
        elif isinstance(square, FantasySquare):
            return CTE_FANTASIA
        elif isinstance(square, GoToJailSquare):
            return self._ev_stay_in_jail()
        elif isinstance(square, ParkingSquare):
            return float(self.game.parking_money)
        elif isinstance(square, ExitSquare):
            return float(square.init_money)
        else:
            return 0.0
    
    def _ev_landing_on_buyable(self, square: BaseSquare) -> float:
        """EV of landing on a buyable square (Opportunity to buy vs paying rent)."""
        rel = _get_relationship(self.game, square)
        if rel is None:
            return self._ev_buying(square)
        if rel.mortgage or rel.owner == self.user:
            return 0.0
        
        rent = self._get_current_rent(square, rel)
        return -float(rent)

    def _ev_buying(self, square: BaseSquare) -> float:
        """
        Expected value of purchasing a square. Compares projected rent income 
        (and blockade value) against the purchase price.
        """
        if not isinstance(square, (PropertySquare, ServerSquare, BridgeSquare)):
            raise ValueError("EV buying only applies to buyable squares")
        
        if not square.buy_price or square.buy_price <= 0:
            return 0.0

        # 1. Own benefit
        rent_increase = self._calculate_rent_delta(square, self.user, gaining=True)
        ev_propiedad = rent_increase * self._expected_visits()
        
        # 2. Block value (ONLY if opponent has cards of this group)
        ev_bloqueo = 0.0
        opponents = self.game.players.exclude(pk=self.user.pk)
        num_opponents = max(1, opponents.count())
        
        max_rival_delta = 0.0
        for opp in opponents:
            tiene_sinergia = False
            if isinstance(square, PropertySquare):
                tiene_sinergia = PropertyRelationship.objects.filter(game=self.game, owner=opp, square__propertysquare__group=square.group).exists()
            elif isinstance(square, ServerSquare):
                tiene_sinergia = PropertyRelationship.objects.filter(game=self.game, owner=opp, square__serversquare__isnull=False).exists()
            elif isinstance(square, BridgeSquare):
                tiene_sinergia = PropertyRelationship.objects.filter(game=self.game, owner=opp, square__bridgesquare__isnull=False).exists()

            if tiene_sinergia:
                rival_delta = self._calculate_rent_delta(square, opp, gaining=True)
                if rival_delta > max_rival_delta:
                    max_rival_delta = rival_delta
                
        if max_rival_delta > 0:
            ev_bloqueo = (max_rival_delta * self._expected_visits()) / num_opponents

        return (ev_propiedad + ev_bloqueo) - float(square.buy_price) + float(square.buy_price)//2 #residual value

    def _ev_bid(self, amount: int) -> float:
        """EV of placing a bid in an auction (Square worth minus bid amount)."""
        if amount == 0:
            return 0.0
    
        auction = self.game.current_auction
        if auction is None:
            return 0.0
    
        square = auction.square.get_real_instance()
        worth  = self._ev_buying(square) + (square.buy_price if square.buy_price else 0)
        return worth - float(amount)

    def _ev_build(self, square: BaseSquare) -> float:
        """EV of building a house (Projected rent increase minus build cost)."""
        if not isinstance(square, PropertySquare):
            return 0.0
    
        rel = _get_relationship(self.game, square)
        if rel is None or rel.mortgage:
            return 0.0
    
        rent_prices = square.rent_prices or []
        current_idx = max(rel.houses, 0)
        next_idx = current_idx + 1
    
        if next_idx >= len(rent_prices):
            return 0.0
    
        rent_delta = rent_prices[next_idx] - rent_prices[current_idx]
        return (rent_delta * self._expected_visits()) - square.build_price
    
    def _ev_demolish(self, square: BaseSquare) -> float:
        """EV of demolishing a house (Refund cash minus projected lost rent)."""
        if not isinstance(square, PropertySquare):
            return 0.0
    
        rel = _get_relationship(self.game, square)
        if rel is None or rel.houses <= 0:
            return 0.0
    
        rent_prices = square.rent_prices or []
        current_idx = max(rel.houses, 0)
        prev_idx = current_idx - 1
    
        if prev_idx < 0 or current_idx >= len(rent_prices):
            return 0.0
    
        rent_delta = rent_prices[current_idx] - rent_prices[prev_idx]
        total_lost_income = rent_delta * self._expected_visits()
    
        return float(square.build_price // 2) - total_lost_income

    def _ev_mortgage_set(self, square: BaseSquare) -> float:
        """EV of mortgaging a square (Immediate cash minus lost rent stream)."""
        if not isinstance(square, (PropertySquare, BridgeSquare, ServerSquare)):
            raise ValueError("EV mortgage only applies to buyable squares")
        
        if not square.buy_price:
            raise ValueError("Cannot mortgage a square with no buy price")
    
        rel = _get_relationship(self.game, square)
        if rel is None or rel.mortgage:
            return 0.0
    
        payout = float(square.buy_price // 2)
        rent_loss = self._calculate_rent_delta(square, self.user, gaining=False)
        total_lost_income = rent_loss * self._expected_visits()
        
        return payout - total_lost_income
    
    def _ev_mortgage_unset(self, square: BaseSquare) -> float:
        """EV of lifting a mortgage (Restored rent stream minus payout cost)."""
        if not isinstance(square, (PropertySquare, BridgeSquare, ServerSquare)):
            raise ValueError("EV mortgage only applies to buyable squares")
        
        if not square.buy_price:
            raise ValueError("Cannot unset mortgage on a square with no buy price")
    
        rel = _get_relationship(self.game, square)
        if rel is None or not rel.mortgage:
            return 0.0
    
        cost = float(square.buy_price // 2)
        rent_gain = self._calculate_rent_delta(square, self.user, gaining=True)
        total_recovered_income = rent_gain * self._expected_visits()
        
        return total_recovered_income - cost

    def _ev_trade_answer(self, choose: bool) -> float:
        """EV of accepting a trade (Net benefit differential against the proposer)."""
        if not choose:
            return 0.0

        proposal = self.game.proposal
            
        opponents = max(1, self.game.players.count() - 1)
        my_props_gained = [rel.square.get_real_instance() for rel in proposal.offered_properties.all()]
        my_props_lost = [rel.square.get_real_instance() for rel in proposal.asked_properties.all()]
        
        my_benefit = self._evaluate_trade_net_benefit(
            player=self.user, properties_gained=my_props_gained,
            properties_lost=my_props_lost, money_gained=proposal.offered_money,
            money_lost=proposal.asked_money
        )
        
        rival_benefit = self._evaluate_trade_net_benefit(
            player=proposal.player, properties_gained=my_props_lost,
            properties_lost=my_props_gained, money_gained=proposal.asked_money,
            money_lost=proposal.offered_money
        )
        
        return my_benefit - (rival_benefit / opponents)

    def _evaluate_trade_net_benefit(self, player, properties_gained, properties_lost, money_gained, money_lost) -> float:
        """Helper to compute the net EV gain/loss of a trade payload for a specific player."""
        gain = float(money_gained)
        for sq in properties_gained:
            gain += self._calculate_rent_delta(sq, player, gaining=True) * self._expected_visits() + sq.buy_price//2 #residual value
            
        loss = float(money_lost)
        for sq in properties_lost:
            loss += self._calculate_rent_delta(sq, player, gaining=False) * self._expected_visits() + sq.buy_price//2 #residual value
            
        return gain - loss

    def _ev_exit_jail(self) -> float:
        """EV of exiting jail (Value of free movement minus risk of paying rent)."""
        unowned = self._get_all_unowned_buyables()
        owned_by_others = self._get_buyables_owned_by_others()

        ev_unowned = sum(self._ev_buying(sq) for sq in unowned) 
        ev_rent = 0.0
        for sq in owned_by_others:
            rel = _get_relationship(self.game, sq)
            if rel is None:
                raise GameLogicError("Owned square with no relationship?")
            ev_rent += self._get_current_rent(sq, rel) * self._expected_visits()

        return ev_unowned - ev_rent
    
    def _ev_stay_in_jail(self) -> float:
        """EV of staying in jail (Inverse of exiting jail)."""
        return -self._ev_exit_jail()

    def _ev_next_12_squares(self, start_square: BaseSquare) -> float:
        """Calculates the uniform EV of the next 12 squares in linear path (Tram heuristic)."""
        ev_sum = 0.0
        curr = start_square
        for _ in range(12):
            if curr.in_successor:
                curr = curr.in_successor.get_real_instance()
                ev_sum += self._ev_square(curr)
            else:
                break
        return ev_sum / 12.0
    
    def _ev_trade_proposal(self, action: ActionTradeProposal) -> float:
        """EV of proposing a trade (Net benefit differential against the target)."""
        opponents = max(1, self.game.players.exclude(pk=self.user.pk).count())
        
        # Extraemos las instancias reales de las propiedades
        my_props_gained = [rel.square.get_real_instance() for rel in action.asked_properties.all()]
        my_props_lost = [rel.square.get_real_instance() for rel in action.offered_properties.all()]
        
        # Beneficio para nuestro agente
        my_benefit = self._evaluate_trade_net_benefit(
            player=self.user, 
            properties_gained=my_props_gained,
            properties_lost=my_props_lost, 
            money_gained=action.asked_money,
            money_lost=action.offered_money
        )
        
        # Beneficio para el rival
        rival_benefit = self._evaluate_trade_net_benefit(
            player=action.destination_user, 
            properties_gained=my_props_lost,
            properties_lost=my_props_gained, 
            money_gained=action.offered_money,
            money_lost=action.asked_money
        )
        
        return my_benefit - (rival_benefit / opponents)

    ################################################################################
    ########################## STATE & MATH HELPERS ################################
    ################################################################################

    def _expected_visits(self) -> float:
        """Expected visits calculation based on heuristic: Probability * Opponents * Turns."""
        opponents = max(1, self.game.players.count() - 1)
        turns_left = max(1, TOTAL_TURNS - self.game.current_turn)
        return PROB_CAER * opponents * turns_left

    def _get_current_rent(self, square: BaseSquare, rel: PropertyRelationship) -> int:
        """Returns the specific rent amount currently owed to the owner of this square."""
        if isinstance(square, PropertySquare):
            houses = rel.houses
            if houses < 0 or rel.mortgage:
                return 0
            rent_prices = square.rent_prices or []
            idx = min(houses, len(rent_prices) - 1)
            return rent_prices[idx] if rent_prices else 0
    
        elif isinstance(square, ServerSquare):
            owned_count = PropertyRelationship.objects.filter(game=self.game, owner=rel.owner, square__in=ServerSquare.objects.all()).count()
            rent_prices = square.rent_prices or []
            idx = min(owned_count - 1, len(rent_prices) - 1)
            return rent_prices[idx] if rent_prices and idx >= 0 else 0
    
        elif isinstance(square, BridgeSquare):
            owned_count = PropertyRelationship.objects.filter(game=self.game, owner=rel.owner, square__in=BridgeSquare.objects.all()).count()
            rent_prices = square.rent_prices or []
            idx = min(owned_count - 1, len(rent_prices) - 1)
            return rent_prices[idx] if rent_prices and idx >= 0 else 0
    
        return 0
    
    def _get_base_rent(self, square: BaseSquare) -> int:
        """Returns the base rent (0 houses, 1 server/bridge) for a square."""
        if isinstance(square, PropertySquare):
            rent_prices = square.rent_prices or []
            return rent_prices[0] if rent_prices else 0
        elif isinstance(square, (ServerSquare, BridgeSquare)):
            rent_prices = square.rent_prices or []
            return rent_prices[0] if rent_prices else 0
        return 0

    def _calculate_rent_delta(self, square: BaseSquare, player, gaining: bool) -> float:
        """Calculates the gross delta in rent income dynamically adjusting for monopoly/group synergies."""
        sq = square.get_real_instance()
        
        if isinstance(sq, PropertySquare):
            owned = PropertyRelationship.objects.filter(game=self.game, owner=player, square__propertysquare__group=sq.group).count()
            total = PropertySquare.objects.filter(board=sq.board, group=sq.group).count()
            base_rent = float(sq.rent_prices[0] if sq.rent_prices else 0)
            
            if gaining:
                return base_rent * (owned + 1) if owned == total - 1 else base_rent
            else:
                return base_rent * (owned + 1) if owned == total else base_rent
                
        elif isinstance(sq, (ServerSquare, BridgeSquare)):
            is_server = isinstance(sq, ServerSquare)
            filter_kw = {'square__serversquare__isnull': False} if is_server else {'square__bridgesquare__isnull': False}
            owned = PropertyRelationship.objects.filter(game=self.game, owner=player, **filter_kw).count()
            rents = sq.rent_prices or []
            if not rents: return 0.0
            
            if gaining:
                new_r = rents[min(owned, len(rents) - 1)]
                old_r = rents[max(0, owned - 1)] if owned > 0 else 0
                return float(new_r - old_r)
            else:
                old_r = rents[min(owned - 1, len(rents) - 1)] if owned > 0 else 0
                new_r = rents[max(0, owned - 2)] if owned > 1 else 0
                return float(old_r - new_r)
                
        return 0.0

    def _calculate_dynamic_reserve(self) -> int:
        """Calculates the maximum possible rent currently owed on the board to establish a safety reserve."""
        owned_by_others = self._get_buyables_owned_by_others()
        if not owned_by_others:
            return 0
        
        max_rent = 0
        for sq in owned_by_others:
            rel = _get_relationship(self.game, sq)
            if rel is None:
                raise GameLogicError("Owned square with no relationship?")
            rent = self._get_current_rent(sq, rel)
            if rent > max_rent:
                max_rent = rent
                
        return max_rent

    def _minimum_safety_cash(self) -> float:
        """Minimum liquid cash to retain, scaled by the number of players and maximum board rent."""
        n_players = self.game.players.count()
        return float(self._calculate_dynamic_reserve() * n_players)

    def _max_willing_to_pay(self, square: BaseSquare) -> int:
        """Calculates the maximum auction bid ensuring ROI and protecting the dynamic cash reserve."""
        if not isinstance(square, (PropertySquare, ServerSquare, BridgeSquare)):
            raise ValueError("Max bid only applies to buyable squares")
        
        money = self.game.money[str(self.user.pk)]
        reserva = self._calculate_dynamic_reserve()
        budget = max(0, money - reserva)
        
        ev_propiedad = self._ev_buying(square) + float(square.buy_price)
        puja_maxima = int(ev_propiedad * CTE_SUBASTA_ROI)
        
        return min(budget, puja_maxima)

    def _get_all_unowned_buyables(self) -> list[BaseSquare]:
        """Fetches all Property, Server, and Bridge squares currently unowned in the game."""
        owned_ids = PropertyRelationship.objects.filter(game=self.game).values_list('square_id', flat=True)
        unowned_ids = []
        for model in (PropertySquare, ServerSquare, BridgeSquare):
            ids = model.objects.exclude(basesquare_ptr_id__in=owned_ids).values_list('basesquare_ptr_id', flat=True)
            unowned_ids.extend(ids)
        return list(BaseSquare.objects.filter(id__in=unowned_ids))

    def _get_buyables_owned_by_others(self) -> list[BaseSquare]:
        """Fetches all Property, Server, and Bridge squares owned by opponent players."""
        rels = PropertyRelationship.objects.filter(game=self.game).exclude(owner=self.user).select_related('square')
        return [rel.square.get_real_instance() for rel in rels]
