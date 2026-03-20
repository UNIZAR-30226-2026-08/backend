## This file has the logic of an AI agent based on the calculation of
## the expected value (EV) of a move.
from unittest.mock import Base

from magnate.exceptions import *
from magnate.models import *
from magnate.game_utils import _get_relationship, _get_user_square, _get_square_by_custom_id
import random

EPSILON = {
    "very_easy": 1.0,   #  random
    "easy":      0.8,
    "medium":    0.6,
    "hard":      0.4,
    "very_hard": 0.2,
    "expert":    0.0,   #  EV
}

class Agent:
    def __init__(self, game: Game, user: CustomUser, level: str):
        if level not in EPSILON:
            raise InvalidBotLevel(game, level)
        self.epsilon = EPSILON[level]
        self.user = user

    def choose_action(self, game: Game) -> Action | None:
        if random.random() < self.epsilon:
            return self._random_action(game)
        return self._heuristic_action(game)


    def _random_action(self, game: Game) -> Action | None:
        phase = game.phase

        if phase == Game.GamePhase.roll_the_dices:
            return self._random_roll_the_dices(game)

        elif phase == Game.GamePhase.choose_square:
            return self._random_choose_square(game)

        elif phase == Game.GamePhase.choose_fantasy:
            return self._random_choose_fantasy(game)

        elif phase == Game.GamePhase.management:
            return self._random_management(game)

        elif phase == Game.GamePhase.business:
            return self._random_business(game)

        elif phase == Game.GamePhase.liquidation:
            return self._random_liquidation(game)

        elif phase == Game.GamePhase.proposal_acceptance:
            return self._random_proposal_acceptance(game)

        elif phase == Game.GamePhase.auction:
            return self._random_auction(game)

        raise GameLogicError(f"Agent: unrecognised phase {phase}")


    def _random_roll_the_dices(self, game: Game) -> Action:
        # if in jail and can afford bail, random
        remaining = game.jail_remaining_turns.get(str(self.user.pk), 0)
        if remaining > 0:
            jail_sq = _get_user_square(game, self.user).get_real_instance()
            if (isinstance(jail_sq, JailSquare)
                    and game.money[str(self.user.pk)] >= jail_sq.bail_price
                    and random.random() < 0.5):
                return ActionPayBail(game=game, player=self.user)

        action = ActionThrowDices(game=game, player=self.user)
        action.save()
        return action
    
    def _random_choose_square(self, game: Game) -> Action:
        destinations = game.possible_destinations
        if not destinations:
            raise GameLogicError("Agent: choose_square phase but no possible_destinations")

        chosen_id = random.choice(destinations)
        square = _get_square_by_custom_id(chosen_id)
        return ActionMoveTo(game=game, player=self.user, square=square)


    def _random_choose_fantasy(self, game: Game) -> Action:
        # chosen_card=True  -> keep the shown card and pay
        # chosen_card=False -> new card
        fantasy_event = game.fantasy_event
        money = game.money[str(self.user.pk)]

        # only consider if we can afford it
        can_afford_shown = (fantasy_event is not None and fantasy_event.card_cost is not None and money >= fantasy_event.card_cost)

        if can_afford_shown:
            return ActionChooseCard(game=game, player=self.user, chosen_card=random.choice([True, False]))

        # if we can't afford
        return ActionChooseCard(game=game, player=self.user, chosen_card=False)


    def _random_management(self, game: Game) -> Action:
        current_square = _get_user_square(game, self.user).get_real_instance()
        prop_rel = _get_relationship(game, current_square)
        money = game.money[str(self.user.pk)]

        # random take or not if we can afford it
        if isinstance(current_square, TramSquare):
            if random.random() < 0.5:
                other_trams = list(TramSquare.objects.exclude(custom_id=current_square.custom_id))
                if other_trams:
                    destination = random.choice(other_trams)
                    if money >= destination.buy_price:
                        return ActionTakeTram(game=game, player=self.user, square=destination)
            return ActionDoNotTakeTram(game=game, player=self.user)

        # buyable squares with no current owner
        is_buyable = isinstance(current_square, (PropertySquare, ServerSquare, BridgeSquare))
        is_unowned = prop_rel is None

        if is_buyable and is_unowned:
            can_afford = money >= current_square.buy_price
            if can_afford and random.random() < 0.5:
                return ActionBuySquare(game=game, player=self.user, square=current_square)
            else:
                # auction -> bot cannot bid
                action = ActionDropPurchase(game=game, player=self.user, square=current_square)
                action.save()
                return action

        # TODO: can't think if there's something missing here -> review
        return ActionNextPhase(game=game, player=self.user)


    def _random_business(self, game: Game) -> Action:
        money = game.money[str(self.user.pk)]

        options = self._get_legal_business_actions(game, money)

        # pass
        options.append(ActionNextPhase(game=game, player=self.user))

        return random.choice(options)

    def _get_legal_business_actions(self, game: Game, money: int) -> list:
        actions = []

        owned = PropertyRelationship.objects.filter( game=game, owner=self.user).select_related('square')

        for rel in owned:
            square = rel.square.get_real_instance()

            # build: complete group, not hotel, not mortgaged, can afford
            if (isinstance(square, PropertySquare)
                    and rel.houses >= 0
                    and rel.houses < 5
                    and not rel.mortgage
                    and hasattr(square, 'build_price')
                    and money >= square.build_price):
                group_min = PropertyRelationship.objects.filter(game=game, owner=self.user, square__propertysquare__group=square.group).exclude(square=rel.square).order_by('houses').values_list('houses', flat=True).first()

                if group_min is None or rel.houses <= group_min:
                    actions.append(ActionBuild(game=game, player=self.user, square=rel.square, houses=1))

                # demolish: at least house
            if isinstance(square, PropertySquare) and rel.houses > 0 and not rel.mortgage:

                group_max = PropertyRelationship.objects.filter(
                    game=game,
                    owner=self.user,
                    square__propertysquare__group=square.group
                ).exclude(
                    square=rel.square
                ).order_by('-houses').values_list('houses', flat=True).first()

                if group_max is None or rel.houses >= group_max:
                    actions.append(ActionDemolish(game=game, player=self.user, square=rel.square, houses=1))

            # mortgage: unmortgaged, no houses on it
            if (not rel.mortgage
                    and isinstance(square, (PropertySquare, BridgeSquare, ServerSquare))
                    and (not isinstance(square, PropertySquare) or rel.houses <= 0)):
                actions.append(ActionMortgageSet(game=game, player=self.user, square=rel.square))

            # unmortgage: mortgaged, can afford
            if (rel.mortgage
                    and hasattr(square, 'buy_price')
                    and money >= square.buy_price // 2):
                actions.append(ActionMortgageUnset(game=game, player=self.user, square=rel.square))

        # trade proposals: random propose -> for now only money
        trade = self._get_random_trade_proposal(game, money)
        if trade is not None:
            actions.append(trade)

        return actions

    def _get_random_trade_proposal(self, game: Game, money: int) -> ActionTradeProposal | None:
        # TODO: for now only money proposals -> include properties
        if random.random() > 0.2:
            return None

        opponents = list(game.players.exclude(pk=self.user.pk))
        if not opponents:
            return None

        target = random.choice(opponents)

        max_offer = min(money, 100)
        if max_offer <= 0:
            return None

        offered_money = random.randint(0, max_offer)
        asked_money  = random.randint(0, 100)

        proposal = ActionTradeProposal(game=game, player=self.user, destination_user=target, offered_money=offered_money, asked_money=asked_money)
        proposal.save()

        return proposal


    def _random_liquidation(self, game: Game) -> Action:
        options = self._get_legal_liquidation_actions(game)

        if options:
            return random.choice(options)

        # No liquidation moves left and still in debt → surrender
        return ActionSurrender(game=game, player=self.user)

    def _get_legal_liquidation_actions(self, game: Game) -> list:
        actions = []

        owned = PropertyRelationship.objects.filter(game=game, owner=self.user).select_related('square')

        for rel in owned:
            square = rel.square.get_real_instance()

            # demolish -> build_price // 2
            if isinstance(square, PropertySquare) and rel.houses > 0:
                actions.append(ActionDemolish(game=game, player=self.user, square=rel.square, houses=1))

            # mortgage -> buy_price // 2
            if (not rel.mortgage
                    and isinstance(square, (PropertySquare, BridgeSquare, ServerSquare))
                    and (not isinstance(square, PropertySquare) or rel.houses <= 0)):
                actions.append(ActionMortgageSet(game=game, player=self.user, square=rel.square))

        return actions


    def _random_proposal_acceptance(self, game: Game) -> Action:
        proposal = game.proposal
        money    = game.money[str(self.user.pk)]

        offering_money = game.money[str(proposal.player.pk)]
        if proposal.asked_money > money or proposal.offered_money > offering_money:
            accept = False
        else:
            accept = random.choice([True, False])

        return ActionTradeAnswer(
            game=game,
            player=self.user,
            choose=accept,
            proposal=proposal
        )


    def _random_auction(self, game: Game) -> Action | None:
        auction = game.current_auction
        # checking
        if auction is None:
            raise GameLogicError("Agent: auction phase but no current_auction")

        money = game.money[str(self.user.pk)]

        is_jailed = game.jail_remaining_turns.get(str(self.user.pk), 0) > 0

        already_bid = auction.bids.filter(player=self.user).exists()

        dropped = ActionDropPurchase.objects.filter(game=game, player=self.user, square=auction.square).exists()

        if dropped or money <= 0 or is_jailed or already_bid:
            # bid 0 not to raise exception
            return None

        if random.random() < 0.5:
            # bid 0 not to raise exception
            return ActionBid(game=game, player=self.user, auction=auction, amount=0)

        amount = random.randint(1, money)
        return ActionBid(game=game, player=self.user, auction=auction, amount=amount)


    def _heuristic_action(self, game: Game) -> Action | None:
        phase = game.phase

        if phase == Game.GamePhase.roll_the_dices:
            return self._ev_roll_the_dices(game)
        elif phase == Game.GamePhase.choose_square:
            return self._ev_choose_square(game)
        elif phase == Game.GamePhase.management:
            return self._ev_management(game)
        elif phase == Game.GamePhase.business:
            return self._ev_business(game)
        elif phase == Game.GamePhase.liquidation:
            return self._ev_liquidation(game)
        elif phase == Game.GamePhase.auction:
            return self._ev_auction(game)
        elif phase == Game.GamePhase.proposal_acceptance:
            return self._ev_proposal_acceptance(game)
        elif phase == Game.GamePhase.choose_fantasy:
            return self._random_choose_fantasy(game)  # opcional, ver nota

        raise GameLogicError(f"Agent EV: unrecognised phase {phase}")
    
    def _ev_roll_the_dices(self, game: Game) -> Action:
        remaining = game.jail_remaining_turns.get(str(self.user.pk), 0)
        if remaining > 0:
            jail_sq = _get_user_square(game, self.user).get_real_instance()
            if isinstance(jail_sq, JailSquare):
                money = game.money[str(self.user.pk)]
                if money >= jail_sq.bail_price:
                    #only thing that changes -> compare th benefits
                    ev_free = self._ev_being_free(game)
                    ev_jailed = self._ev_being_jailed(game)
                    if ev_free > ev_jailed:
                        return ActionPayBail(game=game, player=self.user)

        return ActionThrowDices(game=game, player=self.user)
    
    def _ev_being_free(self, game: Game) -> float:
        return 0.0
    
    def _ev_being_jailed(self, game: Game) -> float:
        return 0.0
    
  
    def _ev_choose_square(self, game: Game) -> Action:
        destinations = game.possible_destinations
        if not destinations:
            raise GameLogicError("Agent EV: no possible_destinations")

        best_id = None
        best_ev = float('-inf')
        for sid in destinations:
            ev = self._ev_square(game, sid)
            if ev > best_ev:
                best_ev = ev
                best_id = sid

        square = _get_square_by_custom_id(best_id) #type: ignore -> never gon be none
        return ActionMoveTo(game=game, player=self.user, square=square)
    
    def _ev_square(self, game: Game, square_id: str) -> float:
        return 0.0
    
    def _ev_management(self, game: Game) -> Action:
        current_square = _get_user_square(game, self.user).get_real_instance()
        rel = _get_relationship(game, current_square)
        money = game.money[str(self.user.pk)]

        if isinstance(current_square, TramSquare):
            # TODO: esta es jodida creo yo
            return self._ev_move_tram(game)

        is_buyable = isinstance(current_square, (PropertySquare, ServerSquare, BridgeSquare))
        if is_buyable and rel is None and money >= current_square.buy_price:
            ev_buy = self._ev_buying(game, current_square) #return of investment

            safety_cash = self._minimum_safety_cash(game) # depending on the game situation (start is 0 then more)

            if ev_buy > 0 and (money - current_square.buy_price) >= safety_cash:
                return ActionBuySquare(game=game, player=self.user, square=current_square)

            action = ActionDropPurchase(game=game, player=self.user, square=current_square)
            action.save()
            return action

        return ActionNextPhase(game=game, player=self.user)
    
    def _ev_move_tram(self, game: Game) -> Action:
        return ActionNextPhase(game=game, player=self.user)
    
    def _ev_buying(self, game: Game, square: BaseSquare) -> float:
        return 0.0
    
    def _minimum_safety_cash(self, game: Game) -> int:
        return 0
    
    def _ev_business(self, game: Game) -> Action:
        money = game.money[str(self.user.pk)]
        options = self._get_legal_business_actions(game, money)

        if not options:
            return ActionNextPhase(game=game, player=self.user)

        best_action = None
        best_ev = -float('inf')

        for action in options:
            ev = self._ev_business_action(game, action, money)
            if ev > best_ev:
                best_ev = ev
                best_action = action

        # Solo actuar si hay EV positivo respecto a pasar
        if best_ev > 0:
            return best_action #type: ignore

        return ActionNextPhase(game=game, player=self.user)
    
    def _ev_business_action(self, game: Game, action: Action, money: int) -> float:
        return 0.0

    
    def _ev_auction(self, game: Game) -> Action | None:
        auction = game.current_auction
        if auction is None:
            raise GameLogicError("Agent EV: auction phase but no current_auction")

        money = game.money[str(self.user.pk)]
        is_jailed = game.jail_remaining_turns.get(str(self.user.pk), 0) > 0
        already_bid = auction.bids.filter(player=self.user).exists()
        dropped = ActionDropPurchase.objects.filter(
            game=game, player=self.user, square=auction.square
        ).exists()

        if dropped or money <= 0 or is_jailed or already_bid:
            return None

        square = auction.square.get_real_instance()
        ev = self._ev_buying(game, square)

        if ev <= 0: # no vale la pena
            return ActionBid(game=game, player=self.user, auction=auction, amount=0)

        max_willing = self._max_willing_to_pay(game, square, money)
        if max_willing <= 0:
            return ActionBid(game=game, player=self.user, auction=auction, amount=0)

        bid = random.randint(max_willing *2 // 3, max_willing) # para que no siempre pague lo mismo

        bid = max(bid, 1)

        return ActionBid(game=game, player=self.user, auction=auction, amount=bid)

    def _max_willing_to_pay(self, game: Game, square: BaseSquare, money: int) -> int:
        return 0
    
    def _ev_liquidation(self, game: Game) -> Action:
        options = self._get_legal_liquidation_actions(game)

        if not options:
            return ActionSurrender(game=game, player=self.user)

        best_action = None
        best_ev = float('-inf')

        for action in options:
            ev = self._ev_liquidation_action(game, action)
            if ev > best_ev:
                best_ev = ev
                best_action = action

        return best_action  # type: ignore

    def _ev_liquidation_action(self, game: Game, action: Action) -> float:
        # demolish > mortgage 
        # mortgage > surrender
        # calcular cual merece mas la pena quedarte
        return 0.0
    
    def _ev_proposal_acceptance(self, game: Game) -> Action:
        proposal = game.proposal
        money = game.money[str(self.user.pk)]
        offering_money = game.money[str(proposal.player.pk)]

        if proposal.asked_money > money or proposal.offered_money > offering_money:
            return ActionTradeAnswer(game=game, player=self.user, choose=False, proposal=proposal)

        ev = self._ev_trade(game, proposal)
        accept = ev > 0

        return ActionTradeAnswer(game=game, player=self.user, choose=accept, proposal=proposal)

    def _ev_trade(self, game: Game, proposal: ActionTradeProposal) -> float:
        # tener en cuenta que te da y que pierdes
        return 0.0