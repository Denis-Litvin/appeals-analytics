from django.core.management.base import BaseCommand

from appeals.classify import recategorize
from appeals.models import Appeal


class Command(BaseCommand):
    help = "Пересчитывает автокатегории по текущему словарю. Обращения с ручной категорией не меняются."

    def handle(self, *args, **options):
        appeals = Appeal.objects.all()
        total = appeals.exclude(category_source=Appeal.Source.MANUAL).count()
        changed = recategorize(appeals)
        empty = Appeal.objects.filter(category__isnull=True).count()
        manual = Appeal.objects.filter(category_source=Appeal.Source.MANUAL).count()
        self.stdout.write(
            f"Пересчитано: {total}, категория изменилась у {changed}, "
            f"без категории: {empty}, ручных не трогали: {manual}"
        )
