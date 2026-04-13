import random
import string

from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser, PrivateRoom
from .serializers import LoginSerializer, RegisterSerializer, UserProfileSerializer, ItemSerializer, PurchaseSerializer, ChangePieceSerializer, GameSummarySerializer
from .models import CustomUser, Item, GameSummary


def get_tokens_for_user(user: CustomUser):
    """
    Generates a JWT token pair for the given user.

    Args:
        user: The authenticated CustomUser instance.

    Returns:
        A dict with 'access' and 'refresh' JWT tokens as strings.
    """
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }


class RegisterView(APIView):
    """
    Endpoint for registering a new user.

    POST /auth/register/

    Request body:
        {
            "username": "mario",
            "password": "Segura123!",
            "password2": "Segura123!"
        }

    Responses:
        201: User created successfully. Returns user data and JWT tokens.
        400: Validation error (passwords don't match, email already exists, etc).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user   = serializer.save()
            assert isinstance(user, CustomUser)
            tokens = get_tokens_for_user(user)
            return Response({
                'message': 'correctly registered user',
                'user':    UserProfileSerializer(user).data,
                'tokens':  tokens,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """
    Endpoint for authenticating an existing user.

    POST /auth/login/

    Request body:
        {
            "username": "mario",
            "password": "Segura123!"
        }

    Responses:
        200: Login successful. Returns user data and JWT tokens.
        400: Missing or malformed fields.
        401: Invalid credentials.
        403: Bots are not allowed to log in.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data: dict = serializer.validated_data  # type: ignore

        auth_user = authenticate(
            username=data['username'],
            password=data['password'],
        )
        if auth_user is None:
            return Response(
                {'error': 'bad credentials'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        assert isinstance(auth_user, CustomUser) ### can't be bot




        tokens = get_tokens_for_user(auth_user)
        return Response({
            'message': 'succesful login',
            'user':    UserProfileSerializer(auth_user).data,
            'tokens':  tokens,
        }, status=status.HTTP_200_OK)


###################################################################
#################### general info #################################
###################################################################

class ProfileView(APIView):
    """
    Endpoint for retrieving the authenticated user's profile.

    GET /user/info/

    Headers:
        Authorization: Bearer <access_token>

    Responses:
        200: Returns the user's profile data.
        401: Missing or invalid access token.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)
    

############################################################################
########################### shop and items ###########################################
############################################################################
class ShopItemListView(APIView):
    """
    Returns the full list of available shop items.
    Each item includes an 'owned' flag for the requesting user.

    GET /shop/items/

    Headers:
        Authorization: Bearer <access_token>

    Responses:
        200: List of all items with id, itemType, price and owned flag.
        401: Missing or invalid token.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = Item.objects.all()
        serializer = ItemSerializer(items, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class BuyItemView(APIView):
    """
    Purchases an item for the authenticated user.
    Deducts the item price from the user's points and adds it to owned_items.

    POST /shop/buy/

    Headers:
        Authorization: Bearer <access_token>

    Request body:
        { "item_id": 1 }

    Responses:
        200: Purchase successful. Returns updated points and item data.
        400: Item not found, already owned, or insufficient points.
        401: Missing or invalid token.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PurchaseSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data: dict = serializer.validated_data  # type: ignore
        item = Item.objects.get(id=data['custom_id'])

        user: CustomUser = request.user  # type: ignore
        user.points -= item.price # money check already done in serializer
        user.save()
        user.owned_items.add(item)

        return Response({
            'message': 'Purchase successful.',
            'item':    ItemSerializer(item, context={'request': request}).data,
            'points_remaining': user.points,
        }, status=status.HTTP_200_OK)


class UserPiecesView(APIView):
    """
    Returns the list of pieces owned by the authenticated user.

    GET /shop/user-pieces/

    Headers:
        Authorization: Bearer <access_token>

    Responses:
        200: List of owned pieces with id, itemType, price and owned flag (always true).
        401: Missing or invalid token.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user: CustomUser = request.user  # type: ignore
        pieces = user.owned_items.filter(itemType='piece')
        serializer = ItemSerializer(pieces, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserNamePieceView(APIView):
    """
    Returns the username and active piece of the requested user.

    GET /info/user-name-piece/<pk>/

    Responses:
        200: Returns username and piece.
        404: User not found.
    """

    permission_classes = [AllowAny]

    def get(self, request, pk):
        user = get_object_or_404(CustomUser, pk=pk)
        return Response({
            'username': user.username,
            'piece':    user.user_piece,
        }, status=status.HTTP_200_OK)


class ChangeUserPieceView(APIView):
    """
    Changes the user's active piece to one they own.

    POST /user/change-piece/

    Headers:
        Authorization: Bearer <access_token>

    Request body:
        { "custom_id": 1 }

    Responses:
        200: Piece changed successfully. Returns the new user_piece value.
        400: Validation error (item not found, not owned, not a piece).
        401: Missing or invalid token.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePieceSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data: dict = serializer.validated_data  # type: ignore
        user: CustomUser = request.user  # type: ignore
        user.user_piece = data['custom_id']
        user.save()

        return Response({
            'message': 'Piece changed successfully.',
            'user_piece': user.user_piece,
        }, status=status.HTTP_200_OK)


class UserEmojisView(APIView):
    """
    Returns the list of emojis owned by the authenticated user.

    GET /shop/user-emojis/

    Headers:
        Authorization: Bearer <access_token>

    Responses:
        200: List of owned emojis with id, itemType, price and owned flag (always true).
        401: Missing or invalid token.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user: CustomUser = request.user  # type: ignore
        emojis = user.owned_items.filter(itemType='emoji')
        serializer = ItemSerializer(emojis, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class GetPrivateCodeView(APIView):
    """
    Generates a unique 6-character alphanumeric private room code.

    GET /lobby/get-private-code

    Headers:
        Authorization: Bearer <access_token>

    Responses:
        200: Returns a unique private room code.
        401: Missing or invalid token.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        code = self._generate_unique_code()
        return Response({
            'code': code,
            'message': 'Private room code generated successfully.'
        }, status=status.HTTP_200_OK)

    #Existe una pequeña y despreciable posibilidad de que lleguen
    #2 peticiones muy seguidas y por mala suerte les dé el mismo número
    #aleatorio. En fin, srand() es mi pastor nada me falta.
    @staticmethod
    def _generate_unique_code():
        """
        Generates a unique 6-character alphanumeric code in uppercase.
        Ensures no existing PrivateRoom has this code.
        """
        characters = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(random.choices(characters, k=6))
            if not PrivateRoom.objects.filter(room_code=code).exists():
                return code
            

class CheckPrivateRoomView(APIView):
    """
    Checks if a private room with the given code exists.

    GET /lobby/check-code/<room_code>/
    
    Headers:
        Authorization: Bearer <access_token>

    Responses:
        200: Returns a boolean indicating if the room exists ({'exists': true/false}).
        401: Missing or invalid token.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, room_code):
        exists = PrivateRoom.objects.filter(room_code=room_code).exists()
        return Response({'exists': exists}, status=status.HTTP_200_OK)
      
class GetGamesPlayedView(APIView):
    """
    Returns a list of IDs for all games played by the authenticated user.

    GET /user/games-played/

    Headers:
        Authorization: Bearer <access_token>

    Responses:
        200: Returns a list of game IDs (e.g., {"games": [1, 5, 12]}).
        401: Missing or invalid token.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        game_ids = list(request.user.played_games.values_list('id', flat=True))
        
        return Response({'games': game_ids}, status=status.HTTP_200_OK)
    


class GetGameSummaryView(APIView):
    """
    Returns a summary of a completed game, including start/end times and final money for each player.

    GET /game/summary/<game_id>/

    Headers:
        Authorization: Bearer <access_token>

    Responses:
        200: Returns game summary with start_date, end_date, and final_money dict.
        401: Missing or invalid token.
        403: User did not participate in this game.
        404: Game summary not found.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, game_id):
        summary = get_object_or_404(GameSummary, game_id=game_id)

        if not request.user.played_games.filter(id=game_id).exists():
             return Response(
                 {'error': 'No tienes permiso para ver el resumen de una partida en la que no participaste.'}, 
                 status=status.HTTP_403_FORBIDDEN
             )

        serializer = GameSummarySerializer(summary)
        return Response(serializer.data, status=status.HTTP_200_OK)
