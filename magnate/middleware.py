from urllib.parse import parse_qs
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from magnate.models import CustomUser

@database_sync_to_async
def get_user_from_jwt(token_string):
    """
    Retrieves a CustomUser instance from a provided JWT token string.

    Args:
        token_string (str): The JWT access token.

    Returns:
        CustomUser | AnonymousUser: The user instance if the token is valid, otherwise AnonymousUser.
    """
    try:
        access_token = AccessToken(token_string)
        return CustomUser.objects.get(id=access_token['user_id'])
    except Exception:
        return AnonymousUser()

class JWTAuthMiddleware(BaseMiddleware):
    """
    Middleware for authenticating WebSocket connections using JWT tokens passed in the query string.
    """
    async def __call__(self, scope, receive, send):
        """
        Intercepts the connection scope to extract and verify the JWT token.

        Args:
            scope (dict): The connection scope.
            receive (callable): The receive channel.
            send (callable): The send channel.

        Returns:
            awaitable: The result of the parent middleware call.
        """
        query_string = parse_qs(scope["query_string"].decode())
        token = query_string.get("token")
        
        if token:
            scope["user"] = await get_user_from_jwt(token[0]) #type: ignore
        else:
            scope["user"] = AnonymousUser() #type: ignore
            
        return await super().__call__(scope, receive, send)
