# Plan: Include Movement Path in Responses

This plan modifies `backend/magnate/games.py` to include the movement path in the responses of `_roll_dices_logic` and `_square_chosen_logic`, using the existing `_move_player_logic` utility.

## Objective
Update `_roll_dices_logic` and `_square_chosen_logic` to:
1.  Calculate the path traversed by the player.
2.  Include this path in `ResponseThrowDices` and `ResponseChooseSquare`.
3.  Ensure jail mechanics (landing on "Go to Jail") are correctly handled when moving.
4.  Correct the `passed_go` logic using the results from `_move_player_logic`.

## Key Files & Context
- `backend/magnate/games.py`: Contains the `GameManager` logic to be modified.
- `backend/magnate/game_utils.py`: Provides `_move_player_logic` and other utilities.
- `backend/magnate/models.py`: Defines the `ResponseMovement` and its subclasses.

## Implementation Steps

### 1. Update `_roll_dices_logic` in `backend/magnate/games.py`
- Retrieve `current_pos_square` and `current_pos_id` at the start of the function.
- Set `response.path = [current_pos_id]` when the player stays in jail.
- Set `response.path = [current_pos_id, jail_square.custom_id]` when the player goes to jail due to 3 doubles.
- For a deterministic move (only one possible destination):
    - Use `_move_player_logic` to get the `path`, `final_id`, `passed_go`, and `jailed` status.
    - Set `response.path = move_result["path"]`.
    - If `move_result["jailed"]` is True:
        - Update player position to the jail square.
        - Set `jail_remaining_turns` to 3.
        - Set game phase to `LIQUIDATION`.
    - Else:
        - Update player position normally.
        - Call `_apply_square_arrival` with `move_result["passed_go"]`.

### 2. Update `_square_chosen_logic` in `backend/magnate/games.py`
- Retrieve `current_pos_square` and `current_pos_id` before updating the position.
- Get the number of `steps` from `game.possible_destinations`.
- Call `_move_player_logic(current_pos_square, steps)`.
- If `steps == 0` (e.g., triples), manually ensure the path is `[current_pos_id, square.custom_id]`.
- Set `response.path` to the calculated path.
- Handle "Go to Jail" logic using `move_result["jailed"]`.
- Use `move_result["passed_go"]` to replace the existing FIXME and call `_apply_square_arrival`.

## Verification & Testing
- **Manual Verification**: Test a dice roll that results in a single destination and check if the `path` is present in the response.
- **Manual Verification**: Test selecting a square from multiple destinations and check the `path`.
- **Manual Verification**: Test landing on "Go to Jail" and verify the player is correctly jailed.
- **Regression Testing**: Ensure doubles/triples logic still works as expected.
