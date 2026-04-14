# Core Game Logic (games.py)

This module encapsulates the rules, state transitions, and actions of the game. It functions as the authoritative backend engine, ensuring that all moves are valid according to the game state.

---

## 🎲 Game State Machine Flow
The game operates as a finite state machine where players transition through specific phases. Any action sent by the frontend must be authorized by the `GameManager` based on the current active phase.



---

## 🛠 Utility & Data Functions
These functions handle the database-level interactions required to resolve game logic.

::: magnate.game_utils
    options:
      members:
        - _get_square_by_custom_id
        - _get_user_square
        - _get_relationship
        - _get_jail_square
        - _calculate_net_worth
        - _get_max_liquidation_value

---

## 🏠 Property & Economy Rules
Calculates financial impacts, building constraints, and mortgage status.



::: magnate.game_utils
    options:
      members:
        - _calculate_rent_price
        - _build_square
        - _demolish_square
        - _set_mortgage
        - _unset_mortgage

---

## ⚙️ GameManager
The primary gateway for all frontend actions. Every action sent via WebSocket or REST must be processed through the `process_action` method.

::: magnate.games.GameManager
    options:
      show_root_heading: true
      members:
        - process_action
        - _pay_bail_logic
        - _roll_dices_logic
        - _square_chosen_logic
        - _choose_fantasy_logic
        - _management_logic
        - _business_logic
        - _answer_trade_proposal_logic
        - _initiate_auction
        - _bid_property_auction_logic
        - _end_auction
        - _next_turn
        - _propose_trade
        - _bankrupt_player
        - _apply_end_bonuses
        - _end_game_logic
