from rest_framework.exceptions import APIException
from rest_framework import status
from channels.exceptions import DenyConnection
from .models import CustomUser, Action, Game

class GameLogicError(Exception):
    def __init__(self, message=''):
        self.message = "Internal logic error: " + message
        super().__init__(self.message)

class GameDesignError(Exception):
    def __init__(self, message=''):
        self.message = "Internal logic error: " + message
        super().__init__(self.message)

class MaliciousUserInput(Exception):
    def __init__(self, user: CustomUser, message=''):
        self.message = f"[{user.id}] Potentially malicious input: " + message
        super().__init__(self.message)

class MaliciousUserInputAction(MaliciousUserInput):
    def __init__(self, game: Game, user: CustomUser, action: Action):
        self.message = f"cannot perform action {action} in phase {game.phase}"
        super().__init__(user, self.message)

