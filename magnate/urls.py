"""
URL configuration for magnate project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import *

#Be careful if changing some url. We have to change
#the docs too. The same for the name, we have to change the tests
urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/',    LoginView.as_view(),    name='login'),
    path('auth/refresh/',  TokenRefreshView.as_view(), name='token_refresh'),
    
    path('user/info/',  ProfileView.as_view(),  name='profile'),
    path('user/change-piece/', ChangeUserPieceView.as_view(), name='change_piece'),
    path('user/games-played/', GetGamesPlayedView.as_view(), name='get_games_played'),

    path('info/user-name-piece/<int:pk>/', UserNamePieceView.as_view(), name='usernamepieceview'),

    path('shop/items/',    ShopItemListView.as_view(), name='shop_items'),
    path('shop/buy/',      BuyItemView.as_view(),      name='shop_buy'),
    path('shop/user-pieces/', UserPiecesView.as_view(), name='user_pieces'),
    path('shop/user-emojis/', UserEmojisView.as_view(), name='user_emojis'),

    path('lobby/check-code/<str:room_code>/', CheckPrivateRoomView.as_view(), name='check-room-code'),
    path('lobby/get-private-code', GetPrivateCodeView.as_view(), name='get_private_code'), 

    path('game/summary/<int:game_id>/', GetGameSummaryView.as_view(), name='game-summary')
    
]
