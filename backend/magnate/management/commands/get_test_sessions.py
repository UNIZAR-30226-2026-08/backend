from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from django.conf import settings

class Command(BaseCommand):
    help = 'Generates valid session IDs for two test users'

    def handle(self, *args, **kwargs):
        User = get_user_model()
        
        user1, _ = User.objects.get_or_create(username='user1', email='u1@test.com')
        user2, _ = User.objects.get_or_create(username='user2', email='u2@test.com')
        
        user1.set_password('1234')
        user1.save()
        user2.set_password('1234')
        user2.save()

        def create_session(user):
            session = SessionStore()
            session[SESSION_KEY] = user._meta.pk.value_to_string(user)
            session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
            session[HASH_SESSION_KEY] = user.get_session_auth_hash()
            session.save()
            return session.session_key

        s1 = create_session(user1)
        s2 = create_session(user2)

        self.stdout.write(self.style.SUCCESS('Sessions Generated!'))
        self.stdout.write(f'User1 (ID: {user1.pk}) Session: {s1}')
        self.stdout.write(f'User2 (ID: {user2.pk}) Session: {s2}')
        self.stdout.write('\nRUN THIS:')
        self.stdout.write(f'python scripts/run_test.py --session1 {s1} --player_id1 {user1.pk} --session2 {s2} --player_id2 {user2.pk}')

