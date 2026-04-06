from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser
from .serializers import LoginSerializer, RegisterSerializer, UserProfileSerializer


def get_tokens_for_user(user: CustomUser):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user   = serializer.save()
            assert isinstance(user, CustomUser)
            tokens = get_tokens_for_user(user)
            return Response({
                'message': 'Usuario registrado correctamente.',
                'user':    UserProfileSerializer(user).data,
                'tokens':  tokens,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
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
                {'error': 'Credenciales inválidas.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        assert isinstance(auth_user, CustomUser)

        if auth_user.is_bot:
            return Response(
                {'error': 'Los bots no pueden iniciar sesión.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        tokens = get_tokens_for_user(auth_user)
        return Response({
            'message': 'Login exitoso.',
            'user':    UserProfileSerializer(auth_user).data,
            'tokens':  tokens,
        }, status=status.HTTP_200_OK)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)