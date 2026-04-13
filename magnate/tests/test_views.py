from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.response import Response as DRFResponse
import string
import re

from magnate.models import CustomUser, Item, PrivateRoom


class AuthTestCase(TestCase):
    """
    Base class providing shared setup and authentication helpers for API view tests.
    """

    client: APIClient

    def setUp(self):
        """
        Sets up a test user with points and some initial items.

        Args:
            None

        Returns:
            None
        """
        self.client = APIClient()

        # create a test user with enough points
        self.user = CustomUser.objects.create_user(
            username='testuser',
            password='Segura123!',
        )
        self.user.points = 1000
        self.user.save()

        # create test items
        self.piece = Item.objects.create(custom_id=1, itemType='piece',  price=100)
        self.emoji = Item.objects.create(custom_id=2, itemType='emoji', price=200)

    def get_token(self, username='testuser', password='Segura123!') -> str:
        """
        Helper to log in a user and return their access token string.

        Args:
            username (str): The username.
            password (str): The password.

        Returns:
            str: The JWT access token.
        """
        response: DRFResponse = self.client.post(reverse('login'), {  # type: ignore
            'username': username,
            'password': password,
        }, format='json')
        assert response.data is not None
        return response.data['tokens']['access']

    def auth_client(self) -> APIClient:
        """
        Helper to return an APIClient configured with authentication headers.

        Args:
            None

        Returns:
            APIClient: The authenticated client.
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return self.client


class RegisterViewTest(AuthTestCase):
    """
    Test suite for the user registration endpoint.
    """

    def test_register_success(self):
        """
        Tests successful user registration.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.post(reverse('register'), {  # type: ignore
            'username':  'newuser',
            'password':  'Segura123!',
            'password2': 'Segura123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        assert response.data is not None
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])

    def test_register_passwords_dont_match(self):
        """
        Tests registration failure when passwords do not match.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.post(reverse('register'), {  # type: ignore
            'username':  'newuser',
            'password':  'Segura123!',
            'password2': 'Diferente123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        assert response.data is not None
        self.assertIn('password', response.data)



    def test_register_weak_password(self):
        """
        Tests registration failure with a weak password.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.post(reverse('register'), {  # type: ignore
            'username':  'newuser',
            'password':  '1234',
            'password2': '1234',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginViewTest(AuthTestCase):
    """
    Test suite for the user login endpoint.
    """

    def test_login_success(self):
        """
        Tests successful user login.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.post(reverse('login'), {  # type: ignore
            'username': 'testuser',
            'password': 'Segura123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertIn('tokens', response.data)

    def test_login_wrong_password(self):
        """
        Tests login failure with an incorrect password.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.post(reverse('login'), {  # type: ignore
            'username': 'testuser',
            'password': 'wrongpassword',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_nonexistent_user(self):
        """
        Tests login failure for a non-existent user.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.post(reverse('login'), {  # type: ignore
            'username': 'noexiste',
            'password': 'Segura123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ProfileViewTest(AuthTestCase):
    """
    Test suite for the user profile information endpoint.
    """

    def test_profile_authenticated(self):
        """
        Tests retrieving profile data for an authenticated user.

        Args:
            None

        Returns:
            None
        """
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('profile'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(response.data['username'], 'testuser')

    def test_profile_unauthenticated(self):
        """
        Tests that unauthenticated users cannot access the profile endpoint.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.get(reverse('profile'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ShopItemListViewTest(AuthTestCase):
    """
    Test suite for listing shop items.
    """

    def test_list_items_authenticated(self):
        """
        Tests listing items for an authenticated user.

        Args:
            None

        Returns:
            None
        """
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('shop_items'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(len(response.data), 2)

    def test_list_items_owned_flag(self):
        """
        Tests that items already owned by the user are correctly flagged.

        Args:
            None

        Returns:
            None
        """
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
        """
        Tests that unauthenticated users cannot list shop items.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.get(reverse('shop_items'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class BuyItemViewTest(AuthTestCase):
    """
    Test suite for the item purchase endpoint.
    """

    def test_buy_success(self):
        """
        Tests a successful item purchase.

        Args:
            None

        Returns:
            None
        """
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
        """
        Tests that a user cannot buy an item they already own.

        Args:
            None

        Returns:
            None
        """
        self.user.owned_items.add(self.piece)
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('shop_buy'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_buy_insufficient_points(self):
        """
        Tests that a user cannot buy an item if they have insufficient points.

        Args:
            None

        Returns:
            None
        """
        self.user.points = 50
        self.user.save()
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('shop_buy'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_buy_nonexistent_item(self):
        """
        Tests purchase failure for a non-existent item.

        Args:
            None

        Returns:
            None
        """
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('shop_buy'), {'custom_id': 999}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_buy_unauthenticated(self):
        """
        Tests that unauthenticated users cannot buy items.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.post(reverse('shop_buy'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserPiecesViewTest(AuthTestCase):
    """
    Test suite for the endpoint listing pieces owned by the user.
    """

    def test_list_user_pieces_authenticated_with_pieces(self):
        """
        Tests listing pieces for an authenticated user with owned items.

        Args:
            None

        Returns:
            None
        """
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
        """
        Tests the case where a user owns no pieces.

        Args:
            None

        Returns:
            None
        """
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('user_pieces'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(len(response.data), 0)  # No pieces owned

    def test_list_user_pieces_unauthenticated(self):
        """
        Tests that unauthenticated users cannot list their pieces.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.get(reverse('user_pieces'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class UsernamePieceViewTest(AuthTestCase):
    """
    Test suite for retrieving a specific user's username and active piece.
    """

    def test_get_username_piece_by_pk(self):
        """
        Tests retrieving name and piece by primary key.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.get(reverse('usernamepieceview', kwargs={'pk': self.user.pk}))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(response.data['username'], 'testuser')
        self.assertEqual(response.data['piece'], self.user.user_piece)

    def test_get_username_piece_not_found(self):
        """
        Tests retrieval failure for a non-existent user PK.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.get(reverse('usernamepieceview', kwargs={'pk': 999}))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class ChangeUserPieceViewTest(AuthTestCase):
    """
    Test suite for the active piece change endpoint.
    """

    def test_change_piece_success(self):
        """
        Tests a successful piece change.

        Args:
            None

        Returns:
            None
        """
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
        """
        Tests that a user cannot change their active piece to one they don't own.

        Args:
            None

        Returns:
            None
        """
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('change_piece'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_piece_not_piece_type(self):
        """
        Tests that only items of type 'piece' can be equipped as the active piece.

        Args:
            None

        Returns:
            None
        """
        # Add an emoji to the user
        self.user.owned_items.add(self.emoji)
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('change_piece'), {'custom_id': 2}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_piece_nonexistent_item(self):
        """
        Tests piece change failure for a non-existent item.

        Args:
            None

        Returns:
            None
        """
        client = self.auth_client()
        response: DRFResponse = client.post(reverse('change_piece'), {'custom_id': 999}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_piece_unauthenticated(self):
        """
        Tests that unauthenticated users cannot change their active piece.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.post(reverse('change_piece'), {'custom_id': 1}, format='json')  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserEmojisViewTest(AuthTestCase):
    """
    Test suite for listing emojis owned by the user.
    """

    def test_list_user_emojis_authenticated_with_emojis(self):
        """
        Tests listing emojis for an authenticated user with owned emojis.

        Args:
            None

        Returns:
            None
        """
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
        """
        Tests the case where a user owns no emojis.

        Args:
            None

        Returns:
            None
        """
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('user_emojis'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertEqual(len(response.data), 0)  # No emojis owned

    def test_list_user_emojis_unauthenticated(self):
        """
        Tests that unauthenticated users cannot list their emojis.

        Args:
            None

        Returns:
            None
        """
        response: DRFResponse = self.client.get(reverse('user_emojis'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class GetPrivateCodeViewTest(AuthTestCase):
    """
    Test suite for the private room code generation endpoint.
    """

    def test_get_private_code_authenticated(self):
        """
        Tests that authenticated users can successfully generate a private room code.

        Args:
            None

        Returns:
            None
        """
        """Test that authenticated users can get a private room code."""
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('get_private_code'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assert response.data is not None
        self.assertIn('code', response.data)
        self.assertIn('message', response.data)
        self.assertEqual(response.data['message'], 'Private room code generated successfully.')

    def test_get_private_code_unauthenticated(self):
        """
        Tests that unauthenticated users cannot generate private room codes.

        Args:
            None

        Returns:
            None
        """
        """Test that unauthenticated users cannot get a private room code."""
        response: DRFResponse = self.client.get(reverse('get_private_code'))  # type: ignore
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_private_code_format(self):
        """
        Tests that the generated code adheres to the 6-character alphanumeric uppercase format.

        Args:
            None

        Returns:
            None
        """
        """Test that the generated code has the correct format (6 alphanumeric uppercase chars)."""
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('get_private_code'))  # type: ignore
        assert response.data is not None
        code = response.data['code']
        
        # Check length
        self.assertEqual(len(code), 6)
        
        # Check it's alphanumeric and uppercase
        self.assertTrue(re.match(r'^[A-Z0-9]{6}$', code))
        
        # Check all characters are uppercase letters or digits
        valid_chars = set(string.ascii_uppercase + string.digits)
        for char in code:
            self.assertIn(char, valid_chars)

    def test_private_code_uniqueness(self):
        """
        Tests that multiple calls generate unique codes.

        Args:
            None

        Returns:
            None
        """
        """Test that different calls generate different codes."""
        client = self.auth_client()
        
        codes = set()
        for _ in range(5):
            response: DRFResponse = client.get(reverse('get_private_code'))  # type: ignore
            assert response.data is not None
            code = response.data['code']
            codes.add(code)
        
        # All codes should be unique
        self.assertEqual(len(codes), 5)

    def test_private_code_not_in_existing_rooms(self):
        """
        Tests that the generated code does not conflict with existing active rooms.

        Args:
            None

        Returns:
            None
        """
        """Test that generated code doesn't match any existing PrivateRoom code."""
        # Create a PrivateRoom with a specific code
        existing_code = 'ABC123'
        PrivateRoom.objects.create(
            owner=self.user,
            room_code=existing_code,
        )
        
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('get_private_code'))  # type: ignore
        assert response.data is not None
        code = response.data['code']
        
        # The generated code should not match the existing one
        self.assertNotEqual(code, existing_code)

    def test_private_code_response_structure(self):
        """
        Tests the JSON response structure of the private code endpoint.

        Args:
            None

        Returns:
            None
        """
        """Test that the response has the correct structure."""
        client = self.auth_client()
        response: DRFResponse = client.get(reverse('get_private_code'))  # type: ignore
        
        assert response.data is not None
        self.assertIsInstance(response.data, dict)
        self.assertEqual(set(response.data.keys()), {'code', 'message'})
        self.assertIsInstance(response.data['code'], str)
        self.assertIsInstance(response.data['message'], str)
