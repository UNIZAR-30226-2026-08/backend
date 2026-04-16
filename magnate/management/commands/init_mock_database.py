from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from magnate.models import *


class Command(BaseCommand):
    """
    Management command to initialize the database with test data.
    """

    def handle(self, *args, **kwargs):
        """
        Loads database elements for testing.
        Clears existing data and repopulates with a consistent test state.
        """
        # ------------------------------------------------------------------
        # Board pre-check  (init_boards must have run first)
        # ------------------------------------------------------------------
        if not Board.objects.exists():
            self.stdout.write(self.style.ERROR(
                "No board found. Run 'python manage.py init_boards' before this command."
            ))
            return

        board = Board.objects.first()

        # Resolve the two squares we need for the test game state.
        # Adjust these custom_ids to match whatever board1.json defines.
        try:
            exit_sq = ExitSquare.objects.get(board=board)
            any_property = PropertySquare.objects.filter(board=board).first()
            assert isinstance(any_property,PropertySquare)
            jail_sq = JailSquare.objects.get(board=board)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Could not resolve required squares: {e}"))
            return

        with transaction.atomic():
            # ------------------------------------------------------------------
            # Cleanup  (leave Board / BaseSquare intact — managed by init_boards)
            # ------------------------------------------------------------------
            Game.objects.all().delete()
            FantasyEvent.objects.all().delete()
            BonusCategory.objects.all().delete()
            Item.objects.all().delete()
            PrivateRoom.objects.all().delete()
            CustomUser.objects.all().delete()

            # ------------------------------------------------------------------
            # Ensure fixture items are available after cleanup
            # ------------------------------------------------------------------
            call_command('loaddata', 'items')

            # ------------------------------------------------------------------
            # Users
            # ------------------------------------------------------------------
            user1 = CustomUser.objects.create_user(username='user1', password='password1')
            user2 = CustomUser.objects.create_user(username='user2', password='password2')
            user3 = CustomUser.objects.create_user(username='user3', password='password3')
            user4 = CustomUser.objects.create_user(username='user4', password='password4')
            admin = CustomUser.objects.create_superuser(username='admin', password='adminpass')
            admin.role = CustomUser.Roles.admin
            admin.points = 9999
            admin.elo = 1500
            admin.save()

            # Bot
            bot1 = Bot.objects.create_user(username='bot_easy', password='botpass')
            bot1.bot_level = 'easy'
            bot1.save()

            # ------------------------------------------------------------------
            # Items  (loaded automatically as a fixture — just fetch them)
            # ------------------------------------------------------------------
            items = list(Item.objects.order_by('custom_id'))
            if not items:
                self.stdout.write(self.style.WARNING(
                    "No items found. Make sure the items fixture is loaded."
                ))

            # Give user1 the cheapest piece and the cheapest emoji (if they exist)
            pieces = [i for i in items if i.itemType == 'piece']
            emojis = [i for i in items if i.itemType == 'emoji']
            if pieces:
                user1.owned_items.add(pieces[0])
                user1.user_piece = pieces[0].custom_id
            if emojis:
                user1.owned_items.add(emojis[0])
            user1.points = 500
            user1.save()

            # ------------------------------------------------------------------
            # Fantasy events
            # ------------------------------------------------------------------
            fantasy_events_data = [
                {'fantasy_type': 'winPlainMoney',   'value': 200,  'card_cost': 50},
                {'fantasy_type': 'losePlainMoney',  'value': 150,  'card_cost': 0},
                {'fantasy_type': 'goToJail',        'value': None, 'card_cost': 0},
                {'fantasy_type': 'doubleOrNothing', 'value': None, 'card_cost': 75},
                {'fantasy_type': 'getParkingMoney', 'value': None, 'card_cost': 100},
                {'fantasy_type': 'goToStart',       'value': None, 'card_cost': 0},
                {'fantasy_type': 'everybodySendsYouMoney', 'value': 50, 'card_cost': 150},
                {'fantasy_type': 'earthquake',      'value': None, 'card_cost': 0},
            ]
            for fe_data in fantasy_events_data:
                FantasyEvent.objects.create(**fe_data)

            # ------------------------------------------------------------------
            # Bonus categories
            # ------------------------------------------------------------------
            bonus_data = [
                {'stat_field': 'walked_squares',    'bonus_amount': 200},
                {'stat_field': 'won_money',         'bonus_amount': 300},
                {'stat_field': 'built_houses',      'bonus_amount': 250},
                {'stat_field': 'times_in_jail',     'bonus_amount': 100},
                {'stat_field': 'num_trades',        'bonus_amount': 150},
                {'stat_field': 'end_game',          'bonus_amount': 500},
            ]
            for bd in bonus_data:
                BonusCategory.objects.create(**bd)

            # ------------------------------------------------------------------
            # Private room (lobby)
            # ------------------------------------------------------------------
            room = PrivateRoom.objects.create(
                owner=user1,
                room_code='TEST01',
                target_players=4,
                bot_level='easy',
            )
            user1.current_private_room = room
            user1.ready_to_play = True
            user1.save()
            user2.current_private_room = room
            user2.ready_to_play = False
            user2.save()

            # ------------------------------------------------------------------
            # Active game (user3 vs user4)
            # ------------------------------------------------------------------
            now = timezone.now()
            game = Game.objects.create(
                datetime=now,
                phase=Game.GamePhase.roll_the_dices,
                ordered_players=[user3.pk, user4.pk],
                positions={
                    str(user3.pk): exit_sq.custom_id,
                    str(user4.pk): any_property.custom_id,
                },
                money={
                    str(user3.pk): 1500,
                    str(user4.pk): 1200,
                },
                jail_remaining_turns={},
                parking_money=100,
                active_phase_player=user3,
                active_turn_player=user3,
                finished=False,
            )
            game.players.add(user3, user4)

            user3.active_game = game
            user3.save()
            user4.active_game = game
            user4.save()

            # Ownership: user4 owns a property (incomplete group → houses=-1)
            PropertyRelationship.objects.create(game=game, owner=user4, square=any_property, houses=-1, mortgage=False)

            # PlayerGameStatistic for both players
            PlayerGameStatistic.objects.create(user=user3, game=game)
            PlayerGameStatistic.objects.create(user=user4, game=game, walked_squares=4, won_money=200)

            # ------------------------------------------------------------------
            # Finished game with summary (user1 vs user2)
            # ------------------------------------------------------------------
            old_game = Game.objects.create(
                datetime=now,
                phase=Game.GamePhase.end_game,
                ordered_players=[user1.pk, user2.pk],
                positions={str(user1.pk): exit_sq.custom_id, str(user2.pk): exit_sq.custom_id},
                money={str(user1.pk): 2000, str(user2.pk): 800},
                jail_remaining_turns={},
                active_phase_player=user1,
                active_turn_player=user1,
                finished=True,
            )
            old_game.players.add(user1, user2)
            PlayerGameStatistic.objects.create(
                user=user1, game=old_game,
                walked_squares=42, won_money=800, lost_money=300,
                built_houses=3, num_trades=2,
            )
            PlayerGameStatistic.objects.create(
                user=user2, game=old_game,
                walked_squares=38, won_money=300, lost_money=700,
                times_in_jail=1, turns_in_jail=2,
            )
            GameSummary.objects.create(
                game=old_game,
                start_date=now,
                end_date=now,
                final_money={user1.username: 2000, user2.username: 800},
            )

            user1.num_played_games = 1
            user1.num_won_games = 1
            user1.exp = 120
            user1.elo = 1050
            user1.save()
            user2.num_played_games = 1
            user2.exp = 80
            user2.elo = 950
            user2.save()

            self.stdout.write('Mock database created')