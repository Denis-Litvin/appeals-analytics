import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from appeals.models import Category, KeywordRule, Reason, Tag

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "dictionary.json"
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def phrase_key(phrase):
    """Ключ для поиска повторов: регистр, ё и лишние пробелы не важны."""
    return " ".join(phrase.lower().replace("ё", "е").split())


def read_dictionary(path=DEFAULT_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate(data):
    """Список ошибок в справочнике. Пустой список значит, что файл можно загружать."""
    errors = []
    seen_phrases = {}
    names, slugs = set(), set()
    for cat in data.get("categories", []):
        name = cat.get("name", "")
        if not name or not cat.get("slug"):
            errors.append(f"У категории нет name или slug: {cat}")
            continue
        if name in names or cat["slug"] in slugs:
            errors.append(f"Категория повторяется: {name}")
        names.add(name)
        slugs.add(cat["slug"])
        if not COLOR_RE.match(cat.get("color", "")):
            errors.append(f"{name}: цвет должен быть в формате #RRGGBB")
        reason_names = set()
        for reason in cat.get("reasons", []):
            rname = reason.get("name", "")
            if not rname or rname in reason_names:
                errors.append(f"{name}: пустая или повторная причина {rname!r}")
            reason_names.add(rname)
            for item in reason.get("phrases", []):
                if not (isinstance(item, list) and len(item) == 2):
                    errors.append(f"{rname}: фраза должна быть парой [текст, вес]: {item}")
                    continue
                phrase, weight = item
                if weight not in (1, 2, 3):
                    errors.append(f"{rname}: у фразы {phrase!r} вес {weight}, допустимо 1-3")
                key = phrase_key(phrase)
                if not key:
                    errors.append(f"{rname}: пустая фраза")
                elif key in seen_phrases:
                    errors.append(f"Фраза {phrase!r} есть и в {seen_phrases[key]!r}, и в {rname!r}")
                else:
                    seen_phrases[key] = rname
    tag_names = set()
    for tag in data.get("tags", []):
        if not tag.get("name") or tag["name"] in tag_names:
            errors.append(f"Пустой или повторный тег: {tag}")
        tag_names.add(tag.get("name"))
    return errors


@transaction.atomic
def load(data, prune=False):
    """Создаёт и обновляет записи справочника по названиям. Возвращает число записей каждого вида в файле."""
    kept_rule_ids = []
    counts = {"categories": 0, "reasons": 0, "phrases": 0, "tags": 0}
    for position, cat in enumerate(data["categories"], start=1):
        category, _ = Category.objects.update_or_create(
            name=cat["name"],
            defaults={
                "slug": cat["slug"],
                "color": cat["color"],
                "description": cat.get("description", ""),
                "sort": position * 10,
                "is_active": True,
            },
        )
        counts["categories"] += 1
        for item in cat["reasons"]:
            reason, _ = Reason.objects.update_or_create(
                category=category, name=item["name"], defaults={"is_active": True}
            )
            counts["reasons"] += 1
            for phrase, weight in item["phrases"]:
                rule, _ = KeywordRule.objects.update_or_create(
                    reason=reason, phrase=phrase.strip(), defaults={"weight": weight}
                )
                kept_rule_ids.append(rule.pk)
                counts["phrases"] += 1
    for tag in data.get("tags", []):
        Tag.objects.update_or_create(name=tag["name"], defaults={"color": tag.get("color", "#6a737d")})
        counts["tags"] += 1
    if prune:
        # Только фразы. Категории и причины могут быть связаны с обращениями, их выключают в админке.
        counts["pruned"] = KeywordRule.objects.exclude(pk__in=kept_rule_ids).delete()[0]
    return counts


class Command(BaseCommand):
    help = "Загружает категории, причины, ключевые фразы и теги из JSON. Повторный запуск обновляет записи."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(DEFAULT_PATH), help="путь к JSON-файлу справочника")
        parser.add_argument(
            "--prune", action="store_true", help="удалить ключевые фразы, которых нет в файле"
        )

    def handle(self, *args, **options):
        try:
            data = read_dictionary(options["path"])
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Не удалось прочитать справочник: {exc}") from exc
        errors = validate(data)
        if errors:
            raise CommandError("Справочник не загружен:\n" + "\n".join(errors))
        counts = load(data, prune=options["prune"])
        self.stdout.write(
            f"Категорий: {counts['categories']}, причин: {counts['reasons']}, "
            f"фраз: {counts['phrases']}, тегов: {counts['tags']}"
        )
        if "pruned" in counts:
            self.stdout.write(f"Удалено фраз, которых нет в файле: {counts['pruned']}")
