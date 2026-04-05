## This file has the logic of an AI agent based on the calculation of
## the expected value (EV) of a move.
from unittest.mock import Base

from magnate.exceptions import *
from magnate.models import *
from magnate.game_utils import _get_relationship, _get_user_square, _get_square_by_custom_id
import random

from magnate.game_utils import _get_possible_destinations_ids, _compute_dice_combinations

################################################################################
############################### CONSTANTS ######################################
################################################################################

EPSILON = {
    "very_easy": 1.0,   #  random
    "easy":      0.8,
    "medium":    0.6,
    "hard":      0.4,
    "very_hard": 0.2,
    "expert":    0.0,   #  EV
}

# Tuning knobs — adjust without touching logic
SAFETY_CASH_PER_PLAYER   = 500     # minimum liquid cash to keep after any purchase
LANDING_PROB_SCALE       = 144     # total dice combinations (6x6x4)
EV_UNKNOWN_SQUARE        = 50.0    # fallback EV for squares we can't evaluate
EV_FANTASY_SQUARE        = 0.0     # fantasy cards treated as neutral in EV
EV_JAIL_FREE_WEIGHT      = 2.0     # weight per unowned buyable when deciding jail exit
EV_JAIL_OPPONENT_WEIGHT  = 2.0     # weight per opponent-owned buyable when deciding jail exit
EV_TRAM_FARE_PENALTY     = 30.0    # flat cost of paying a tram fare
LANDING_PROBABILITY = 1 / 36 # FIXME: How many squares
PAYBACK_HORIZON_TURNS = 10

class Agent:
    def __init__(self, game: Game, user: CustomUser, level: str):
        if level not in EPSILON:
            raise InvalidBotLevel(game, level)
        self.epsilon = EPSILON[level]
        self.game = game
        self.user = user

    def choose_action(self) -> Action | None:
        possible_actions = self._get_possible_actions()
        if len(possible_actions) == 0:
            return None
        elif random.random() < self.epsilon:
            return random.choice(possible_actions)
        else:
            return max(possible_actions, key=self._ev_action)

################################################################################
########################## possible actions ####################################
################################################################################

    def _get_possible_actions(self) -> list[Action]:
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
    
        raise GameLogicError(f"Agent: unrecognised phase {phase}")

    def _get_possible_actions_roll_the_dices(self) -> list[Action]:
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
        destinations = self.game.possible_destinations
        if not destinations:
            raise GameLogicError("Agent: choose_square phase but no possible_destinations")
    
        return [
            ActionMoveTo(game=self.game, player=self.user, square=_get_square_by_custom_id(d))
            for d in destinations
        ]
    
    
    def _get_possible_actions_choose_fantasy(self) -> list[Action]:
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
        actions = []
        current_square = _get_user_square(self.game, self.user).get_real_instance()
        prop_rel = _get_relationship(self.game, current_square)
        money = self.game.money[str(self.user.pk)]
    
        if isinstance(current_square, TramSquare):
            # Taking a tram is mandatory — no ActionNextPhase here.
            # Always include the current tram square itself.
            actions.append(ActionTakeTram(game=self.game, player=self.user, square=current_square))
            # Also offer any other affordable trams.
            other_trams = TramSquare.objects.exclude(custom_id=current_square.custom_id)
            for tram in other_trams:
                if money >= tram.buy_price:
                    actions.append(ActionTakeTram(game=self.game, player=self.user, square=tram))
            return actions
    
        is_buyable = isinstance(current_square, (PropertySquare, ServerSquare, BridgeSquare))
        is_unowned = prop_rel is None
    
        if is_buyable and is_unowned:
            if money >= current_square.buy_price:
                actions.append(ActionBuySquare(game=self.game, player=self.user, square=current_square))
            # Dropping triggers an auction; always a valid alternative to buying.
            actions.append(ActionDropPurchase(game=self.game, player=self.user, square=current_square))
        else:
            # Owned square or non-buyable square — nothing to decide, just move on.
            actions.append(ActionNextPhase(game=self.game, player=self.user))
    
        return actions

    def _get_possible_actions_business(self) -> list[Action]:
        actions = []
        money = self.game.money[str(self.user.pk)]
    
        owned = PropertyRelationship.objects.filter(game=self.game, owner=self.user).select_related('square')
    
        for rel in owned:
            square = rel.square.get_real_instance()
    
            if (isinstance(square, PropertySquare)
                    and rel.houses >= 0
                    and rel.houses < 5
                    and not rel.mortgage
                    and hasattr(square, 'build_price')
                    and money >= square.build_price):
                group_min = (PropertyRelationship.objects
                    .filter(game=self.game, owner=self.user, square__propertysquare__group=square.group)
                    .exclude(square=rel.square)
                    .order_by('houses')
                    .values_list('houses', flat=True)
                    .first())
                if group_min is None or rel.houses <= group_min:
                    actions.append(ActionBuild(game=self.game, player=self.user, square=rel.square, houses=1))
    
            if isinstance(square, PropertySquare) and rel.houses > 0 and not rel.mortgage:
                group_max = (PropertyRelationship.objects
                    .filter(game=self.game, owner=self.user, square__propertysquare__group=square.group)
                    .exclude(square=rel.square)
                    .order_by('-houses')
                    .values_list('houses', flat=True)
                    .first())
                if group_max is None or rel.houses >= group_max:
                    actions.append(ActionDemolish(game=self.game, player=self.user, square=rel.square, houses=1))
    
            if (not rel.mortgage
                    and isinstance(square, (PropertySquare, BridgeSquare, ServerSquare))
                    and (not isinstance(square, PropertySquare) or rel.houses <= 0)):
                actions.append(ActionMortgageSet(game=self.game, player=self.user, square=rel.square))
    
            if (rel.mortgage
                    and hasattr(square, 'buy_price')
                    and money >= square.buy_price // 2):
                actions.append(ActionMortgageUnset(game=self.game, player=self.user, square=rel.square))
    
        # FIXME: add trades
        # trade = self._get_random_trade_proposal(money)
        # if trade is not None:
        #     actions.append(trade)
    
        # Passing is always valid in business phase.
        actions.append(ActionNextPhase(game=self.game, player=self.user))
        return actions
    
    
    def _get_possible_actions_liquidation(self) -> list[Action]:
        actions = []
    
        owned = PropertyRelationship.objects.filter(game=self.game, owner=self.user).select_related('square')
    
        for rel in owned:
            square = rel.square.get_real_instance()
    
            if isinstance(square, PropertySquare) and rel.houses > 0:
                actions.append(ActionDemolish(game=self.game, player=self.user, square=rel.square, houses=1))
    
            if (not rel.mortgage
                    and isinstance(square, (PropertySquare, BridgeSquare, ServerSquare))
                    and (not isinstance(square, PropertySquare) or rel.houses <= 0)):
                actions.append(ActionMortgageSet(game=self.game, player=self.user, square=rel.square))
    
        money = self.game.money[str(self.user.pk)]
    
        if not actions:
            actions.append(ActionSurrender(game=self.game, player=self.user))
        elif money > 0:
            # Only offer NextPhase if solvent and there are still things left to sell.
            actions.append(ActionNextPhase(game=self.game, player=self.user))
    
        return actions
   
    def _get_possible_actions_proposal_acceptance(self) -> list[Action]:
        actions = []
        proposal = self.game.proposal
        money = self.game.money[str(self.user.pk)]
        offering_money = self.game.money[str(proposal.player.pk)]
    
        # Can only accept if both sides can actually cover their side of the deal.
        if proposal.asked_money <= money and proposal.offered_money <= offering_money:
            actions.append(ActionTradeAnswer(
                game=self.game, player=self.user, choose=True, proposal=proposal
            ))
    
        actions.append(ActionTradeAnswer(
            game=self.game, player=self.user, choose=False, proposal=proposal
        ))
        return actions
    
    
    def _get_possible_actions_auction(self) -> list[Action]:
        auction = self.game.current_auction
        if auction is None:
            raise GameLogicError("Agent: auction phase but no current_auction")
    
        money = self.game.money[str(self.user.pk)]
        is_jailed = self.game.jail_remaining_turns.get(str(self.user.pk), 0) > 0
        already_bid = str(self.user.pk) in auction.bids
        dropped = ActionDropPurchase.objects.filter(
            game=self.game, player=self.user, square=auction.square
        ).exists()
    
        # Pass (amount=0) is always an option.
        pass_bid = ActionBid(game=self.game, player=self.user, amount=0)
    
        if dropped or money <= 0 or is_jailed or already_bid:
            return [pass_bid]
    
        # Spread 3 bids across low / mid / high thirds of available money.
        low  = max(1, money * 1 // 3)
        mid  = max(1, money * 2 // 3)
        high = max(1, money)
    
        return [
            pass_bid,
            ActionBid(game=self.game, player=self.user, amount=low),
            ActionBid(game=self.game, player=self.user, amount=mid),
            ActionBid(game=self.game, player=self.user, amount=high),
        ]

################################################################################
################################ heuristics ####################################
################################################################################

    ################################################################################
    ############################### EV CORE ########################################
    ################################################################################
    
    def _ev_action(self, action: Action) -> float:
        """
        Top-level dispatcher. Returns the expected value of taking a given action
        from the current game state. Higher is better for this agent.
        """
        if isinstance(action, ActionThrowDices):
            # No choice involved — EV is neutral.
            return 0.0
    
        elif isinstance(action, ActionPayBail):
            # Paying bail is worthwhile when exiting jail has positive EV.
            # The cost is already spent; what matters is freedom to act.
            return self._ev_exit_jail()
    
        elif isinstance(action, ActionMoveTo):
            return self._ev_square(action.square.get_real_instance())
    
        elif isinstance(action, ActionChooseCard):
            # Fantasy cards are opaque at decision time — treat as neutral.
            return EV_FANTASY_SQUARE
    
        elif isinstance(action, ActionTakeTram):
            # EV = value of destination square minus the fare penalty.
            destination = action.square.get_real_instance()
            return self._ev_square(destination) - EV_TRAM_FARE_PENALTY
    
        elif isinstance(action, ActionBuySquare):
            return self._ev_buying(action.square.get_real_instance())
    
        elif isinstance(action, ActionDropPurchase):
            # Dropping means going to auction; we might still win it, but
            # for simplicity treat as 0 (we model the auction phase separately).
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
    
        elif isinstance(action, ActionNextPhase):
            return 0.0
    
        elif isinstance(action, ActionSurrender):
            return -float('inf')
    
        elif isinstance(action, ActionTradeAnswer):
            return 0.0
    
        return 0.0
    
    
    ################################################################################
    ########################### SQUARE EV ##########################################
    ################################################################################
    
    def _ev_square(self, square: BaseSquare) -> float:
        """
        Expected value of landing on a given square for this agent.
        Positive = good for us, negative = bad for us.
        """
        if isinstance(square, (PropertySquare, ServerSquare, BridgeSquare)):
            return self._ev_landing_on_buyable(square)
    
        elif isinstance(square, TramSquare):
            # Landing on a tram triggers the tram phase; no direct rent effect.
            return 0.0
    
        elif isinstance(square, FantasySquare):
            return EV_FANTASY_SQUARE
    
        elif isinstance(square, GoToJailSquare):
            return self._ev_stay_in_jail()
    
        elif isinstance(square, ParkingSquare):
            # We collect the accumulated parking pot.
            return float(self.game.parking_money)
    
        elif isinstance(square, ExitSquare):
            # Passing go — collect init_money.
            return float(square.init_money)
    
        else:
            # JailVisitSquare, JailSquare (visiting), unknown — neutral.
            return 0.0
    
    
    def _ev_landing_on_buyable(self, square: BaseSquare) -> float:
        """
        EV of landing on a buyable square (Property, Server, Bridge).
    
        - Unowned:           buying opportunity → positive EV
        - Owned by us:       no rent paid → neutral
        - Owned by opponent: we pay rent → negative EV
        - Mortgaged:         no rent → neutral
        """
        rel = _get_relationship(self.game, square)
    
        if rel is None:
            # Unowned — we get to buy it (or send it to auction).
            return self._ev_buying(square)
    
        if rel.mortgage:
            return 0.0
    
        if rel.owner == self.user:
            return 0.0
    
        # Opponent owns it — we pay rent.
        rent = self._get_current_rent(square, rel)
        return -float(rent)
    
    
    ################################################################################
    ########################### RENT HELPERS #######################################
    ################################################################################
    
    def _get_current_rent(self, square: BaseSquare, rel: PropertyRelationship) -> int:
        """
        Returns the rent amount currently owed if a player lands on this square.
        Uses the house level stored in the relationship for PropertySquare,
        and the number of same-type squares owned for Server/Bridge.
        """
        if isinstance(square, PropertySquare):
            houses = rel.houses
            if houses < 0 or rel.mortgage:
                return 0
            rent_prices = square.rent_prices or []
            idx = min(houses, len(rent_prices) - 1)
            return rent_prices[idx] if rent_prices else 0
    
        elif isinstance(square, ServerSquare):
            owned_count = PropertyRelationship.objects.filter(
                game=self.game,
                owner=rel.owner,
                square__in=ServerSquare.objects.all()
            ).count()
            rent_prices = square.rent_prices or []
            idx = min(owned_count - 1, len(rent_prices) - 1)
            return rent_prices[idx] if rent_prices and idx >= 0 else 0
    
        elif isinstance(square, BridgeSquare):
            owned_count = PropertyRelationship.objects.filter(
                game=self.game,
                owner=rel.owner,
                square__in=BridgeSquare.objects.all()
            ).count()
            rent_prices = square.rent_prices or []
            idx = min(owned_count - 1, len(rent_prices) - 1)
            return rent_prices[idx] if rent_prices and idx >= 0 else 0
    
        return 0
    
    
    def _get_base_rent(self, square: BaseSquare) -> int:
        """
        Returns the base rent (0 houses / 1 server or bridge owned) for a square.
        Used for ROI calculations when evaluating whether to buy.
        """
        if isinstance(square, PropertySquare):
            rent_prices = square.rent_prices or []
            # Index 0 = complete group with no houses
            return rent_prices[0] if rent_prices else 0
    
        elif isinstance(square, (ServerSquare, BridgeSquare)):
            rent_prices = square.rent_prices or []
            return rent_prices[0] if rent_prices else 0
    
        return 0
    
    
    ################################################################################
    ########################### BUYING EV ##########################################
    ################################################################################
    
    def _ev_buying(self, square: BaseSquare) -> float:
        """
        Expected value of purchasing a square.
    
        Heuristic: compare the stream of rent income (base rent scaled by
        landing probability) against the purchase price.
        A positive value means the investment is worthwhile relative to its cost.
    
        We use base rent (no houses yet) as a conservative estimate.
        """
        if not hasattr(square, 'buy_price'):
            return 0.0
    
        buy_price = square.buy_price
        if buy_price <= 0:
            return 0.0
    
        base_rent    = self._get_base_rent(square)
        landing_prob = self._landing_probability(square)
    
        # Expected rent income per turn × a payback horizon (in turns),
        # minus the purchase price. Constants are collected at the top.
        expected_income_per_turn = base_rent * landing_prob
        payback_turns            = PAYBACK_HORIZON_TURNS
        total_expected_income    = expected_income_per_turn * payback_turns
    
        return total_expected_income - buy_price
    
    
    def _minimum_safety_cash(self) -> float:
        """
        Minimum liquid cash we want to keep on hand after any transaction.
        Scales with number of players (more players = more risk of paying rent).
        """
        n_players = self.game.players.count()
        return float(SAFETY_CASH_PER_PLAYER * n_players)
    
    
    def _max_willing_to_pay(self, square: BaseSquare) -> int:
        """
        Maximum amount we're willing to bid for a square at auction.
        Caps at available money minus safety buffer, and only up to
        what the square is worth to us.
        """
        money        = self.game.money[str(self.user.pk)]
        safety       = self._minimum_safety_cash()
        budget       = max(0, money - int(safety))
        square_worth = max(0, int(self._ev_buying(square) + square.buy_price))
        return min(budget, square_worth)
    
    
    ################################################################################
    ########################### BUILD / DEMOLISH EV ################################
    ################################################################################
    
    def _ev_build(self, square: BaseSquare) -> float:
        """
        Expected value of building one house on a PropertySquare.
    
        Heuristic: rent increase after building × landing probability,
        projected over a horizon, minus the build cost.
        Relative to doing nothing (ActionNextPhase EV = 0).
        """
        if not isinstance(square, PropertySquare):
            return 0.0
    
        rel = _get_relationship(self.game, square)
        if rel is None or rel.mortgage:
            return 0.0
    
        rent_prices = square.rent_prices or []
        current_idx = max(rel.houses, 0)
        next_idx     = current_idx + 1
    
        if next_idx >= len(rent_prices):
            return 0.0
    
        current_rent = rent_prices[current_idx]
        next_rent    = rent_prices[next_idx]
        rent_delta   = next_rent - current_rent
    
        landing_prob             = self._landing_probability(square)
        expected_gain_per_turn   = rent_delta * landing_prob
        total_expected_gain      = expected_gain_per_turn * PAYBACK_HORIZON_TURNS
    
        return total_expected_gain - square.build_price
    
    
    def _ev_demolish(self, square: BaseSquare) -> float:
        """
        Expected value of demolishing one house (liquidation context).
    
        In liquidation we need cash; the value is the refund (build_price // 2)
        minus the lost rent income stream.
        Positive when we're cash-strapped and the rent loss is acceptable.
        """
        if not isinstance(square, PropertySquare):
            return 0.0
    
        rel = _get_relationship(self.game, square)
        if rel is None or rel.houses <= 0:
            return 0.0
    
        rent_prices = square.rent_prices or []
        current_idx = max(rel.houses, 0)
        prev_idx    = current_idx - 1
    
        if prev_idx < 0 or current_idx >= len(rent_prices):
            return 0.0
    
        current_rent = rent_prices[current_idx]
        prev_rent    = rent_prices[prev_idx]
        rent_delta   = current_rent - prev_rent  # what we lose
    
        landing_prob           = self._landing_probability(square)
        lost_income_per_turn   = rent_delta * landing_prob
        total_lost_income      = lost_income_per_turn * PAYBACK_HORIZON_TURNS
    
        refund = square.build_price // 2
        return float(refund) - total_lost_income
    
    
    ################################################################################
    ########################### MORTGAGE EV ########################################
    ################################################################################
    
    def _ev_mortgage_set(self, square: BaseSquare) -> float:
        """
        Expected value of mortgaging a square.
    
        Gain: immediate cash = buy_price // 2.
        Cost: lost rent income stream until unmortgaged.
        Relative to doing nothing (EV = 0).
        """
        if not hasattr(square, 'buy_price'):
            return 0.0
    
        rel = _get_relationship(self.game, square)
        if rel is None or rel.mortgage:
            return 0.0
    
        payout      = square.buy_price // 2
        base_rent   = self._get_current_rent(square, rel)
        landing_prob = self._landing_probability(square)
    
        lost_income = base_rent * landing_prob * PAYBACK_HORIZON_TURNS
        return float(payout) - lost_income
    
    
    def _ev_mortgage_unset(self, square: BaseSquare) -> float:
        """
        Expected value of lifting a mortgage.
    
        Cost: buy_price // 2 paid now.
        Gain: restored rent income stream.
        Relative to doing nothing (EV = 0).
        """
        if not hasattr(square, 'buy_price'):
            return 0.0
    
        rel = _get_relationship(self.game, square)
        if rel is None or not rel.mortgage:
            return 0.0
    
        cost        = square.buy_price // 2
        base_rent   = self._get_base_rent(square)
        landing_prob = self._landing_probability(square)
    
        recovered_income = base_rent * landing_prob * PAYBACK_HORIZON_TURNS
        return recovered_income - float(cost)
    
    
    ################################################################################
    ########################### AUCTION EV #########################################
    ################################################################################
    
    def _ev_bid(self, amount: int) -> float:
        """
        Expected value of placing a bid of `amount` in the current auction.
    
        We don't model win probability (would require knowing other bids),
        so EV is simply the square's worth minus what we pay,
        floored at 0 for a pass bid.
        """
        if amount == 0:
            return 0.0
    
        auction = self.game.current_auction
        if auction is None:
            return 0.0
    
        square = auction.square.get_real_instance()
        worth  = self._ev_buying(square) + (square.buy_price if hasattr(square, 'buy_price') else 0)
        return worth - float(amount)
    
    
    ################################################################################
    ########################### JAIL EV ############################################
    ################################################################################
    
    def _ev_exit_jail(self) -> float:
        """
        EV of being free to move vs staying in jail.
    
        More unowned squares = more buying opportunities (good to be free).
        More opponent squares = more rent exposure (bad to be free).
        """
        num_free     = float(self._get_all_unowned_buyables().count())
        num_opponent = float(self._get_buyables_owned_by_others().count())
        return EV_JAIL_FREE_WEIGHT * num_free - EV_JAIL_OPPONENT_WEIGHT * num_opponent
    
    
    def _ev_stay_in_jail(self) -> float:
        return -self._ev_exit_jail()
    
    
    ################################################################################
    ########################### LANDING PROBABILITY ################################
    ################################################################################
    
    def _landing_probability(self, square: BaseSquare) -> float:
        return LANDING_PROBABILITY
    
