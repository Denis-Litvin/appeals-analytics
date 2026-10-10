import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.models import SpikeAlert
from analytics.spikes import check
from appeals.management.commands.generate_appeals import generate, summary
from appeals.models import Appeal
from appeals.roles import DEMO_PASSWORD, DEMO_USERS


class Command(BaseCommand):
    help = "Готовит демо-базу одной командой: миграции, справочник, роли с учётками, обращения."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=6000)
        parser.add_argument("--months", type=float, default=6)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--reset", action="store_true", help="удалить обращения и сгенерировать заново")

    def handle(self, *args, **options):
        started = time.perf_counter()
        call_command("migrate", interactive=False, verbosity=0)
        self.stdout.write("Миграции применены")
        call_command("load_dictionary", stdout=self.stdout)
        call_command("setup_roles", "--demo-users", stdout=self.stdout)

        existing = Appeal.objects.count()
        if existing and not options["reset"]:
            self.stdout.write(
                f"Обращения уже есть ({existing}), генерация пропущена. Пересоздать: setup_demo --reset"
            )
        else:
            if options["reset"]:
                SpikeAlert.objects.all().delete()
            stats = generate(options["count"], options["months"], options["seed"], clear=options["reset"])
            for line in summary(stats):
                self.stdout.write(line)

        # Всплески ищутся по всей истории. Письма не отправляются: это не новые события, а разметка демо-данных.
        first = Appeal.objects.order_by("created_at").values_list("created_at", flat=True).first()
        if first:
            found = check(timezone.localtime(first).date(), timezone.localdate())
            self.stdout.write(f"Найдено всплесков: {len(found)} новых, всего уведомлений {SpikeAlert.objects.count()}")

        logins = ", ".join(username for username, *_ in DEMO_USERS)
        self.stdout.write(f"Готово за {time.perf_counter() - started:.1f} с. Вход: {logins}, пароль {DEMO_PASSWORD}")
