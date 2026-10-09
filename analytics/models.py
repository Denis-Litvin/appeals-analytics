from django.conf import settings
from django.db import models
from django.db.models import Q

from appeals.models import Category, Reason


class SpikeAlert(models.Model):
    """Резкий рост обращений по категории (reason пустой) или по причине за один день."""

    category = models.ForeignKey(Category, models.CASCADE, related_name="spike_alerts", verbose_name="категория")
    reason = models.ForeignKey(
        Reason, models.CASCADE, null=True, blank=True, related_name="spike_alerts", verbose_name="причина"
    )
    day = models.DateField("день")
    count = models.PositiveIntegerField("обращений за день")
    baseline = models.FloatField("обычный уровень")
    ratio = models.FloatField("рост, раз")
    created_at = models.DateTimeField("найдено", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)
    read_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="read_alerts", verbose_name="прочитали"
    )

    class Meta:
        verbose_name = "уведомление о росте"
        verbose_name_plural = "уведомления о росте"
        ordering = ["-day", "-ratio"]
        indexes = [models.Index(fields=["day"], name="spike_day_idx")]
        # NULL в reason не участвует в обычной уникальности, поэтому два условных ограничения.
        constraints = [
            models.UniqueConstraint(
                fields=["category", "day"],
                condition=Q(reason__isnull=True),
                name="spike_unique_category_day",
            ),
            models.UniqueConstraint(
                fields=["category", "reason", "day"],
                condition=Q(reason__isnull=False),
                name="spike_unique_reason_day",
            ),
        ]

    def __str__(self):
        target = self.reason or self.category
        return f"{self.day:%d.%m.%Y} {target}: {self.count} при норме {self.baseline:g}"
