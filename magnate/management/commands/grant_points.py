from django.core.management.base import BaseCommand, CommandError
from magnate.models import CustomUser


class Command(BaseCommand):
    help = "Asigna (o quita) puntos a jugadores por username."

    def add_arguments(self, parser):
        parser.add_argument(
            "usernames",
            nargs="+",
            type=str,
            help="Uno o más usernames separados por espacios",
        )
        parser.add_argument(
            "--points",
            type=int,
            required=True,
            help="Puntos a añadir (negativo para quitar). Ej: --points 500 o --points -200",
        )
        parser.add_argument(
            "--set",
            action="store_true",
            help="En vez de sumar, establece el valor exacto indicado en --points",
        )

    def handle(self, *args, **options):
        points = options["points"]
        mode_set = options["set"]

        for username in options["usernames"]:
            try:
                user = CustomUser.objects.get(username=username)
            except CustomUser.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"✗ '{username}' no encontrado"))
                continue

            before = user.points
            if mode_set:
                user.points = points
            else:
                user.points += points
            user.save(update_fields=["points"])

            if mode_set:
                self.stdout.write(self.style.SUCCESS(
                    f"✓ {username}: {before} → {user.points} (fijado)"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"✓ {username}: {before} {points:+} → {user.points}"
                ))