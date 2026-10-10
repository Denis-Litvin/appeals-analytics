from rest_framework import serializers

from analytics.models import SpikeAlert
from appeals.models import Appeal, Tag
from appeals.roles import author_for


class AppealSerializer(serializers.ModelSerializer):
    """Обращение для чтения. Имя и email автора в том виде, в каком их можно показать пользователю токена."""

    author_name = serializers.SerializerMethodField()
    author_email = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()
    tags = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    assignee = serializers.SlugRelatedField(read_only=True, slug_field="username")

    class Meta:
        model = Appeal
        fields = [
            "id", "created_at", "channel", "author_name", "author_email", "subject", "text", "status",
            "category", "reason", "category_source", "category_score", "tags", "assignee", "resolved_at",
            "updated_at",
        ]

    def author(self, appeal):
        # Имя и email считаются один раз на обращение, а нужны двум полям.
        cache = self.context.setdefault("authors", {})
        if appeal.pk not in cache:
            cache[appeal.pk] = author_for(self.context["request"].user, appeal)
        return cache[appeal.pk]

    def get_author_name(self, appeal):
        return self.author(appeal)[0]

    def get_author_email(self, appeal):
        return self.author(appeal)[1]

    def get_category(self, appeal):
        if not appeal.category_id:
            return None
        return {"id": appeal.category_id, "slug": appeal.category.slug, "name": appeal.category.name}

    def get_reason(self, appeal):
        if not appeal.reason_id:
            return None
        return {"id": appeal.reason_id, "name": appeal.reason.name}


class AppealCreateSerializer(serializers.ModelSerializer):
    """Новое обращение. Категория и причина определяются по словарю при сохранении, их передавать не нужно."""

    tags = serializers.SlugRelatedField(many=True, required=False, slug_field="name", queryset=Tag.objects.all())

    class Meta:
        model = Appeal
        fields = ["channel", "author_name", "author_email", "subject", "text", "tags"]


class SpikeAlertSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    category_name = serializers.CharField(source="category.name", read_only=True)
    reason = serializers.SerializerMethodField()
    read = serializers.SerializerMethodField()

    class Meta:
        model = SpikeAlert
        fields = ["id", "day", "category", "category_name", "reason", "count", "baseline", "ratio", "read",
                  "updated_at"]

    def get_reason(self, alert):
        return {"id": alert.reason_id, "name": alert.reason.name} if alert.reason_id else None

    def get_read(self, alert):
        return alert.pk in self.context["read_ids"]
