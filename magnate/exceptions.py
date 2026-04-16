"""
Game Exceptions Module.

This module defines custom exceptions used throughout the game logic
to handle internal errors, board configuration issues, and invalid
or malicious actions performed by users.
"""

from rest_framework.exceptions import APIException
from rest_framework import status
from channels.exceptions import DenyConnection
from .models import *

class GameLogicError(Exception):
    """
    Exception raised for errors in the internal game logic.

    This is typically thrown when the game reaches an impossible state
    or encounters an unexpected condition during normal execution.

    Attributes:
        message (str): Explanation of the internal logic error.
    """
    def __init__(self, message=''):
        """
        Initializes the GameLogicError.

        Args:
            message (str, optional): Specific details about the logic error. Defaults to ''.

        Returns:
            None
        """
        self.message = "Internal logic error: " + message
        super().__init__(self.message)

class GameDesignError(Exception):
    """
    Exception raised for errors in the game's design or board configuration.

    This is used when a square lacks required data (like rent prices) or
    when the board is fundamentally misconfigured (e.g., missing a Jail square).

    Attributes:
        message (str): Explanation of the design error.
    """
    def __init__(self, message=''):
        """
        Initializes the GameDesignError.

        Args:
            message (str, optional): Specific details about the configuration or design error. Defaults to ''.

        Returns:
            None
        """
        self.message = "Internal logic error: " + message
        super().__init__(self.message)

class MaliciousUserInput(Exception):
    """
    Exception raised when a user provides invalid, unauthorized, or potentially malicious input.

    This acts as a security and validation layer, thrown when a user attempts
    to manipulate assets they do not own, or tries to exploit the game mechanics.

    Attributes:
        message (str): Explanation of the malicious input, tagged with the user's primary key.
    """
    def __init__(self, user: CustomUser, message=''):
        """
        Initializes the MaliciousUserInput exception.

        Args:
            user (CustomUser): The user who triggered the exception.
            message (str, optional): Specific details about what the user attempted to do. Defaults to ''.

        Returns:
            None
        """
        self.message = f"[{user.pk}] Potentially malicious input: " + message
        super().__init__(self.message)

class MaliciousUserInputAction(MaliciousUserInput):
    """
    Exception raised when a user attempts an action that is not allowed in the current game phase.

    This is a specialized form of MaliciousUserInput used heavily in the GameManager
    to enforce strict phase-based state machine transitions.

    Attributes:
        message (str): Detailed message including the invalid action and the current game phase.
    """
    def __init__(self, game: Game, user: CustomUser, action: Action):
        """
        Initializes the MaliciousUserInputAction exception.

        Args:
            game (Game): The current game instance where the violation occurred.
            user (CustomUser): The user attempting the invalid action.
            action (Action): The forbidden action the user attempted to perform.

        Returns:
            None
        """
        self.message = f"cannot perform action {action} in phase {game.phase}"
        super().__init__(user, self.message)

class InvalidBotLevel(Exception):
    """
    Exception raised when an invalid difficulty level is provided for a bot.
    """
    def __init__(self, game: Game, level: str):
        """
        Initializes the InvalidBotLevel exception.

        Args:
            game (Game): Th current game intance where the violation ocurred.
            level (str): The invalid bot level.

        Returns:
            None
        """
        self.message = f"invalid bot level {level} in game {game.pk}"
        super().__init__(self.message)

class CheatException(Exception):
    """Raised when a cheat command is invalid or used outside DEBUG mode."""
    pass
