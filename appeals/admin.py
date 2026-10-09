from django.contrib import admin

from .models import Appeal, Category, KeywordRule, Reason, Tag


class ReasonInline(admin.TabularInline):
    model = Reason
    extra = 0
    fields = ["name", "is_active"]
    show_change_link = True


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "color", "sort", "is_active"]
    list_editable = ["sort", "is_active"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [ReasonInline]


class KeywordRuleInline(admin.TabularInline):
    model = KeywordRule
    extra = 1
    fields = ["phrase", "weight"]


@admin.register(Reason)
class ReasonAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name"]
    list_select_related = ["category"]
    inlines = [KeywordRuleInline]


@admin.register(KeywordRule)
class KeywordRuleAdmin(admin.ModelAdmin):
    list_display = ["phrase", "weight", "reason", "category"]
    list_filter = ["weight", "reason__category"]
    search_fields = ["phrase", "reason__name"]
    list_select_related = ["reason__category"]
    autocomplete_fields = ["reason"]

    @admin.display(description="категория", ordering="reason__category__name")
    def category(self, obj):
        return obj.reason.category


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "color"]
    search_fields = ["name"]


@admin.register(Appeal)
class AppealAdmin(admin.ModelAdmin):
    list_display = ["id", "created_at", "channel", "short_text", "category", "reason", "category_source", "status"]
    list_filter = ["status", "channel", "category_source", "category", "tags"]
    search_fields = ["subject", "text", "author_email"]
    date_hierarchy = "created_at"
    list_select_related = ["category", "reason"]
    autocomplete_fields = ["reason", "tags"]
    readonly_fields = ["text_norm", "category_score", "category_matches", "updated_at"]
    fieldsets = [
        (None, {"fields": ["created_at", "channel", "author_name", "author_email", "subject", "text"]}),
        ("Обработка", {"fields": ["status", "assignee", "resolved_at", "tags"]}),
        ("Категория", {"fields": ["category", "reason", "category_source", "category_score", "category_matches"]}),
        ("Служебное", {"fields": ["text_norm", "updated_at"], "classes": ["collapse"]}),
    ]

    @admin.display(description="текст")
    def short_text(self, obj):
        return obj.subject or obj.text[:80]
