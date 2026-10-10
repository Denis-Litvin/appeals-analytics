from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from analytics.spikes import check


class Command(BaseCommand):
    help = "Ищет резкий рост обращений за дни с --from по --to (по умолчанию сегодня) и записывает уведомления."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", type=date.fromisoformat, help="первый день, ГГГГ-ММ-ДД")
        parser.add_argument("--to", dest="end", type=date.fromisoformat, help="последний день, ГГГГ-ММ-ДД")
        parser.add_argument("--notify", action="store_true", help="отправить аналитикам письмо о новых уведомлениях")

    def handle(self, *args, **options):
        end = options["end"] or timezone.localdate()
        start = options["start"] or end
        if start > end:
            raise CommandError("--from позже --to")
        new = check(start, end, notify_new=options["notify"])
        self.stdout.write(f"Проверены дни {start:%d.%m.%Y} - {end:%d.%m.%Y}, новых уведомлений: {len(new)}")
        for alert in new:
            target = f"{alert.category}: {alert.reason}" if alert.reason_id else alert.category
            self.stdout.write(f"  {alert.day:%d.%m.%Y} {target}: {alert.count} при обычных {alert.baseline:g}")
