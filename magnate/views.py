from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser
from .serializers import LoginSerializer, RegisterSerializer, UserProfileSerializer, ItemSerializer, PurchaseSerializer
from .models import CustomUser, Item


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
            "email": "mario@example.com",
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

        assert isinstance(auth_user, CustomUser)

        if auth_user.is_bot:
            return Response(
                {'error': 'bots cant login'},
                status=status.HTTP_403_FORBIDDEN,
            )

        tokens = get_tokens_for_user(auth_user)
        return Response({
            'message': 'succesful login',
            'user':    UserProfileSerializer(auth_user).data,
            'tokens':  tokens,
        }, status=status.HTTP_200_OK)


class ProfileView(APIView):
    """
    Endpoint for retrieving the authenticated user's profile.

    GET /auth/profile/

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
########################### shop ###########################################
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
        user.points -= item.price
        user.save()
        user.owned_items.add(item)

        return Response({
            'message': 'Purchase successful.',
            'item':    ItemSerializer(item, context={'request': request}).data,
            'points_remaining': user.points,
        }, status=status.HTTP_200_OK)