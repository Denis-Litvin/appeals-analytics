from django.core.management.base import BaseCommand

from appeals.roles import DEMO_PASSWORD, ROLES, create_demo_users, setup_roles


class Command(BaseCommand):
    help = "Создаёт группы Оператор, Аналитик, Администратор с их правами. С --demo-users ещё и демо-учётки."

    def add_arguments(self, parser):
        parser.add_argument("--demo-users", action="store_true", help="создать демо-учётки трёх операторов, аналитика и администратора")

    def handle(self, *args, **options):
        groups = setup_roles()
        for name, perms in ROLES.items():
            self.stdout.write(f"{name}, прав: {len(perms)}")
        if options["demo_users"]:
            created = create_demo_users(groups)
            if created:
                self.stdout.write(f"Созданы учётки {', '.join(created)} с паролем {DEMO_PASSWORD}")
            else:
                self.stdout.write("Демо-учётки уже есть, пароли не менялись, группы обновлены")
