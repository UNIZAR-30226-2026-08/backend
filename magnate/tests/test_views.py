from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.response import Response as DRFResponse

from magnate.models import CustomUser, Item


class AuthTestCase(TestCase):
    """Base class with shared setup for all tests."""

    client: APIClient

    def setUp(self):
        self.client = APIClient()

        # create a test user with enough points
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Segura123!',
        )
        self.user.points = 1000
        self.user.save()

        # create test items
        self.piece = Item.objects.create(custom_id=1, itemType='piece',  price=100)
        self.emoji = Item.objects.create(custom_id=2, itemType='emoji', price=200)

    def get_token(self, username='testuser', password='Segura123!'):
        """Helper to log in and return the access token."""
        response: DRFResponse = self.client.post(reverse('login'), {  # type: ignore
            'username': username,
            'password': password,
        }, format='json')
        assert response.data is not None
        return response.data['tokens']['access']

    def auth_client(self):
        """Helper to return an authenticated APIClient."""
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return self.client


class RegisterViewTest(AuthTestCase):

    def test_register_success(self):
        response: DRFResponse = self.client.post(reverse('register'), {  # type: ignore
            'username':  'newuser',
            'email':     'new@example.com',
            'password':  'Segura123!',
            'password2': 'Segura123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        assert response.data is not None
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])

    def test_register_passwords_dont_match(self):
        response: DRFResponse = self.client.post(reverse('register'), {  # type: ignore
            'username':  'newuser',
            'email':     'new@example.com',
            'password':  'Segura123!',
            'password2': 'Diferente123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        assert response.data is not None
        self.assertIn('password', response.data)

    def test_register_duplicate_email(self):
        response: DRFResponse = self.client.post(reverse('register'), {  # type: ignore
            'username':  'otheruser',
            'email':     'test@example.com',
            'password':  'Segura123!',
            'password2': 'Segura123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        assert response.data is not None
        self.assertIn('email', response.data)

    def test_register_weak_password(self):
        response: DRFResponse = self.client.post(reverse('register'), {  # type: ignore
            'username':  'newuser',
            'email':     'new@example.com',
            'password':  '1234',
            'password2': '1234',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginViewTest(AuthTestCase):

    def test_login_success(self):
        response: DRFResponse = self.client.post(reverse('login'), {  # type: ignore
            'username': 'testuser',
            'password': 'Segura123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertIn('tokens', response.data)

    def test_login_wrong_password(self):
        response: DRFResponse = self.client.post(reverse('login'), {  # type: ignore
            'username': 'testuser',
            'password': 'wrongpassword',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_bot_forbidden(self):
        CustomUser.objects.create_user(
            username='bot1',
            email='bot@example.com',
            password='Segura123!',
            is_bot=True,
        )
        response: DRFResponse = self.client.post(reverse('login'), {  # type: ignore
            'username': 'bot1',
            'password': 'Segura123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_login_nonexistent_user(self):
        response: DRFResponse = self.client.post(reverse('login'), {  # type: ignore
            'username': 'noexiste',
            'password': 'Segura123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ProfileViewTest(AuthTestCase):

    def test_profile_authenticated(self):
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('profile'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(response.data['username'], 'testuser')

    def test_profile_unauthenticated(self):
        response: DRFResponse = self.client.get(reverse('profile'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ShopItemListViewTest(AuthTestCase):

    def test_list_items_authenticated(self):
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('shop_items'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(len(response.data), 2)

    def test_list_items_owned_flag(self):
        self.user.owned_items.add(self.piece)
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('shop_items'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        piece = next(i for i in response.data if i['custom_id'] == 1)
        emoji = next(i for i in response.data if i['custom_id'] == 2)
        self.assertTrue(piece['owned'])
        self.assertFalse(emoji['owned'])

    def test_list_items_unauthenticated(self):
        response: DRFResponse = self.client.get(reverse('shop_items'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class BuyItemViewTest(AuthTestCase):

    def test_buy_success(self):
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('shop_buy'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(response.data['points_remaining'], 900)
        self.assertTrue(response.data['item']['owned'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.points, 900)
        self.assertTrue(self.user.owned_items.filter(custom_id=1).exists())

    def test_buy_already_owned(self):
        self.user.owned_items.add(self.piece)
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('shop_buy'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_buy_insufficient_points(self):
        self.user.points = 50
        self.user.save()
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('shop_buy'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_buy_nonexistent_item(self):
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('shop_buy'), {'custom_id': 999}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_buy_unauthenticated(self):
        response: DRFResponse = self.client.post(reverse('shop_buy'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserPiecesViewTest(AuthTestCase):

    def test_list_user_pieces_authenticated_with_pieces(self):
        # Add a piece to the user
        self.user.owned_items.add(self.piece)
        # Also add an emoji, but it should not appear
        self.user.owned_items.add(self.emoji)
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('user_pieces'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(len(response.data), 1)  # Only the piece
        piece = response.data[0]
        self.assertEqual(piece['custom_id'], 1)
        self.assertEqual(piece['itemType'], 'piece')
        self.assertTrue(piece['owned'])

    def test_list_user_pieces_authenticated_no_pieces(self):
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('user_pieces'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(len(response.data), 0)  # No pieces owned

    def test_list_user_pieces_unauthenticated(self):
        response: DRFResponse = self.client.get(reverse('user_pieces'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ChangeUserPieceViewTest(AuthTestCase):

    def test_change_piece_success(self):
        # Add a piece to the user
        self.user.owned_items.add(self.piece)
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('change_piece'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(response.data['user_piece'], 1)
        self.user.refresh_from_db()
        self.assertEqual(self.user.user_piece, 1)

    def test_change_piece_not_owned(self):
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('change_piece'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_piece_not_piece_type(self):
        # Add an emoji to the user
        self.user.owned_items.add(self.emoji)
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('change_piece'), {'custom_id': 2}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_piece_nonexistent_item(self):
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('change_piece'), {'custom_id': 999}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_piece_unauthenticated(self):
        response: DRFResponse = self.client.post(reverse('change_piece'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserEmojisViewTest(AuthTestCase):

    def test_list_user_emojis_authenticated_with_emojis(self):
        # Add an emoji to the user
        self.user.owned_items.add(self.emoji)
        # Also add a piece, but it should not appear
        self.user.owned_items.add(self.piece)
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('user_emojis'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(len(response.data), 1)  # Only the emoji
        emoji = response.data[0]
        self.assertEqual(emoji['custom_id'], 2)
        self.assertEqual(emoji['itemType'], 'emoji')
        self.assertTrue(emoji['owned'])

    def test_list_user_emojis_authenticated_no_emojis(self):
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('user_emojis'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(len(response.data), 0)  # No emojis owned

    def test_list_user_emojis_unauthenticated(self):
        response: DRFResponse = self.client.get(reverse('user_emojis'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)