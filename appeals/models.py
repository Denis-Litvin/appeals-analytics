from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .classify import Classifier
from .text import normalize

color_validator = RegexValidator(r"^#[0-9a-fA-F]{6}$", "Цвет в формате #RRGGBB.")


class Category(models.Model):
    name = models.CharField("название", max_length=100, unique=True)
    slug = models.SlugField("код", max_length=50, unique=True)
    description = models.TextField("описание", blank=True)
    color = models.CharField("цвет на графиках", max_length=7, default="#6a737d", validators=[color_validator])
    sort = models.PositiveSmallIntegerField("порядок", default=100)
    is_active = models.BooleanField("используется", default=True)

    class Meta:
        verbose_name = "категория"
        verbose_name_plural = "категории"
        ordering = ["sort", "name"]

    def __str__(self):
        return self.name


class Reason(models.Model):
    category = models.ForeignKey(Category, models.PROTECT, related_name="reasons", verbose_name="категория")
    name = models.CharField("название", max_length=150)
    is_active = models.BooleanField("используется", default=True)

    class Meta:
        verbose_name = "причина"
        verbose_name_plural = "причины"
        ordering = ["category__sort", "category__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["category", "name"], name="reason_unique_in_category"),
        ]

    def __str__(self):
        return self.name


class KeywordRule(models.Model):
    WEIGHTS = [(1, "1 - слабый признак"), (2, "2 - обычный"), (3, "3 - сильный признак")]

    reason = models.ForeignKey(Reason, models.CASCADE, related_name="rules", verbose_name="причина")
    phrase = models.CharField("ключевая фраза", max_length=200)
    weight = models.PositiveSmallIntegerField(
        "вес", choices=WEIGHTS, default=2, validators=[MinValueValidator(1), MaxValueValidator(3)]
    )

    class Meta:
        verbose_name = "ключевая фраза"
        verbose_name_plural = "ключевые фразы"
        ordering = ["reason", "phrase"]
        constraints = [
            models.UniqueConstraint(fields=["reason", "phrase"], name="rule_unique_in_reason"),
        ]

    def __str__(self):
        return self.phrase


class Tag(models.Model):
    name = models.CharField("название", max_length=50, unique=True)
    color = models.CharField("цвет", max_length=7, default="#6a737d", validators=[color_validator])

    class Meta:
        verbose_name = "тег"
        verbose_name_plural = "теги"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Appeal(models.Model):
    class Channel(models.TextChoices):
        APP = "app", "Приложение"
        WEB = "web", "Сайт"
        EMAIL = "email", "Email"
        PHONE = "phone", "Телефон"
        CHAT = "chat", "Чат"

    class Status(models.TextChoices):
        NEW = "new", "Новое"
        IN_WORK = "in_work", "В работе"
        RESOLVED = "resolved", "Решено"
        CLOSED = "closed", "Закрыто"

    class Source(models.TextChoices):
        AUTO = "auto", "Автоматически"
        MANUAL = "manual", "Вручную"
        NONE = "none", "Не определена"

    created_at = models.DateTimeField("поступило", default=timezone.now)
    channel = models.CharField("канал", max_length=10, choices=Channel.choices, default=Channel.WEB)
    author_name = models.CharField("автор", max_length=150, blank=True)
    author_email = models.EmailField("email автора", blank=True)
    subject = models.CharField("тема", max_length=200, blank=True)
    text = models.TextField("текст")
    # Основы слов через пробел, заполняется при сохранении, по нему идёт поиск.
    text_norm = models.TextField("нормализованный текст", blank=True, editable=False)

    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.NEW)
    category = models.ForeignKey(
        Category, models.PROTECT, null=True, blank=True, related_name="appeals", verbose_name="категория"
    )
    reason = models.ForeignKey(
        Reason, models.PROTECT, null=True, blank=True, related_name="appeals", verbose_name="причина"
    )
    category_source = models.CharField(
        "источник категории", max_length=10, choices=Source.choices, default=Source.NONE
    )
    category_score = models.FloatField("баллы автокатегории", default=0)
    # Ключевые фразы, которые сработали: [{"reason": id, "phrase": "...", "weight": 2}, ...]
    category_matches = models.JSONField("найденные фразы", default=list, blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="appeals", verbose_name="теги")

    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_appeals",
        verbose_name="исполнитель",
    )
    resolved_at = models.DateTimeField("решено", null=True, blank=True)
    updated_at = models.DateTimeField("изменено", auto_now=True)

    class Meta:
        verbose_name = "обращение"
        verbose_name_plural = "обращения"
        ordering = ["-created_at", "-id"]
        # Права ролей (Д10), раздаются группам командой setup_roles.
        permissions = [
            ("view_personal_data", "Видеть имя и email автора"),
            ("view_analytics", "Смотреть статистику, дашборд и уведомления"),
            ("export_reports", "Выгружать отчёты и списки"),
            ("manage_dictionary", "Вести справочники и пересчитывать категории"),
        ]
        indexes = [
            models.Index(fields=["created_at"], name="appeal_created_idx"),
            models.Index(fields=["category", "created_at"], name="appeal_category_created_idx"),
            models.Index(fields=["reason", "created_at"], name="appeal_reason_created_idx"),
            models.Index(fields=["status"], name="appeal_status_idx"),
            models.Index(fields=["channel"], name="appeal_channel_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(reason__isnull=True) | Q(category__isnull=False),
                name="appeal_reason_needs_category",
            ),
            # auto бывает только с категорией, none только без неё; manual возможен в обоих случаях.
            models.CheckConstraint(
                condition=~Q(category__isnull=True, category_source="auto")
                & ~Q(category__isnull=False, category_source="none"),
                name="appeal_source_matches_category",
            ),
        ]

    # Текст на момент загрузки из базы, по нему save() понимает, что текст изменился.
    _saved_text = None

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._saved_text = (instance.__dict__.get("subject"), instance.__dict__.get("text"))
        return instance

    def __str__(self):
        return f"#{self.pk} {self.subject or self.text[:60]}"

    @property
    def full_text(self):
        return f"{self.subject}\n{self.text}" if self.subject else self.text

    def apply_classification(self, result):
        self.category_id = result.category_id
        self.reason_id = result.reason_id
        self.category_source = self.Source.AUTO if result.category_id else self.Source.NONE
        self.category_score = result.score
        self.category_matches = result.matches

    def save(self, *args, **kwargs):
        # Пересчитываем только новый или изменённый текст, чтобы смена статуса не меняла категорию.
        if (self.subject, self.text) != self._saved_text:
            self.text_norm = normalize(self.full_text)
            if self.category_source != self.Source.MANUAL:
                self.apply_classification(Classifier.from_db().classify(self.full_text))
        super().save(*args, **kwargs)
        self._saved_text = (self.subject, self.text)

    def clean(self):
        if self.reason_id and self.category_id and self.reason.category_id != self.category_id:
            raise ValidationError({"reason": "Причина относится к другой категории."})
        if self.reason_id and not self.category_id:
            raise ValidationError({"category": "Укажите категорию для выбранной причины."})
