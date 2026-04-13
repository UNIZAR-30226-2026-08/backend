from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

class Command(BaseCommand):
    help = 'Generates valid JWT access tokens for two test users'

    def handle(self, *args, **kwargs):
        User = get_user_model()
        
        user1, _ = User.objects.get_or_create(username='user1', email='u1@test.com')
        user2, _ = User.objects.get_or_create(username='user2', email='u2@test.com')
        
        user1.set_password('1234')
        user1.save()
        user2.set_password('1234')
        user2.save()

        def create_token(user):
            refresh = RefreshToken.for_user(user)
            return str(refresh.access_token)

        t1 = create_token(user1)
        t2 = create_token(user2)

        self.stdout.write(self.style.SUCCESS('Sessions Generated!'))
        self.stdout.write(f'User1 (ID: {user1.pk}) Session: {t1}')
        self.stdout.write(f'User2 (ID: {user2.pk}) Session: {t2}')
        self.stdout.write('\nRUN THIS:')
        self.stdout.write(f'python scripts/run_test.py --token1 {t1} --player_id1 {user1.pk} --token2 {t2} --player_id2 {user2.pk}')