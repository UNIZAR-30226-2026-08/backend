from rest_framework.exceptions import APIException
from rest_framework import status
from channels.exceptions import DenyConnection

# class InsufficientInventoryError(Exception):
#     """Raised when an order exceeds available stock."""
#     def __init__(self, message="Not enough items in stock", inventory_count=0):
#         self.message = message
#         self.inventory_count = inventory_count
#         super().__init__(self.message)
# 
# class ServiceUnavailable(APIException):
#     status_code = 503
#     default_detail = 'Service temporarily offline, try again later.'
#     default_code = 'service_unavailable'
# 
# class UnauthenticatedConsumerError(DenyConnection):
#     """Raised when a user tries to connect without a valid token."""
#     pass
# 
# class GameLogicError(Exception):
#     """Custom error for real-time game state issues."""
#     pass

class GameLogicError(Exception):
    def __init__(self, message=''):
        self.message = "Internal logic error: " + message
        super().__init__(self.message)

class GameDesignError(Exception):
    def __init__(self, message=''):
        self.message = "Internal logic error: " + message
        super().__init__(self.message)

class MaliciousUserInput(Exception):
    def __init__(self, message=''):
        self.message = "Internal logic error: " + message
        super().__init__(self.message)

