from datetime import date, datetime
from io import StringIO
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management import call_command
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse

from appeals.filters import filter_appeals, text_query
from appeals.models import Appeal, Category, Reason, Tag

MSK = ZoneInfo("Europe/Moscow")


def at(day, hour=12, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=MSK)


class FilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        cls.operator = User.objects.get(username="operator")
        cls.operator2 = User.objects.get(username="operator2")
        cls.ios, cls.android, cls.vip = (Tag.objects.get(name=n) for n in ("iOS", "Android", "VIP"))
        cls.delivery = Category.objects.get(slug="delivery")

        cls.payment_appeal = Appeal.objects.create(
            text="Не проходят оплаты картой, пишет отказ", channel="app", created_at=at(1, 10)
        )
        cls.payment_appeal.tags.add(cls.ios)
        cls.courier = Appeal.objects.create(
            text="Курьер опоздал на три часа", channel="phone", created_at=at(15, 23, 30),
            status="resolved", assignee=cls.operator,
        )
        cls.courier.tags.add(cls.vip)
        cls.unclear = Appeal.objects.create(
            text="Здравствуйте, подскажите режим работы", channel="chat", created_at=at(20),
            status="closed", author_email="petrov@yandex.ru",
        )
        cls.manual = Appeal.objects.create(
            text="Списали дважды за один заказ", channel="email", created_at=at(30), status="in_work",
            assignee=cls.operator2, category=cls.delivery,
            reason=Reason.objects.get(name="Задержка доставки"), category_source="manual",
        )
        cls.manual.tags.add(cls.ios, cls.android)

    def ids(self, **params):
        query = QueryDict(mutable=True)
        for key, value in params.items():
            if isinstance(value, list):
                query.setlist(key, [str(v) for v in value])
            else:
                query[key] = str(value)
        appeals, form = filter_appeals(query)
        return set(appeals.values_list("pk", flat=True))

    def test_no_filters(self):
        self.assertEqual(len(self.ids()), 4)

    def test_text_by_stems(self):
        self.assertEqual(self.ids(q="оплата не проходит"), {self.payment_appeal.pk})
        self.assertEqual(self.ids(q="курьера"), {self.courier.pk})
        self.assertEqual(self.ids(q="Курьер оплата"), set())  # слова соединяются через И

    def test_text_ignores_case_and_yo(self):
        self.assertEqual(self.ids(q="ОПЛАТЫ"), {self.payment_appeal.pk})
        self.assertEqual(self.ids(q="здравствуйте"), {self.unclear.pk})

    def test_phrase_in_quotes(self):
        self.assertEqual(self.ids(q='"списали дважды"'), {self.manual.pk})
        self.assertEqual(self.ids(q='"дважды списали"'), set())

    def test_number(self):
        self.assertEqual(self.ids(q=f"#{self.courier.pk}"), {self.courier.pk})
        self.assertEqual(self.ids(q="#999999"), set())

    def test_email(self):
        self.assertEqual(self.ids(q="petrov@"), {self.unclear.pk})
        self.assertEqual(self.ids(q="@YANDEX.ru"), {self.unclear.pk})

    def test_email_search_only_for_those_who_see_email(self):
        # Аналитик не видит email автора и не должен проверять поиском, писал ли конкретный адрес.
        found = {}
        for username in ("operator", "analyst", "admin"):
            appeals, _ = filter_appeals(QueryDict("q=petrov@yandex.ru"), User.objects.get(username=username))
            found[username] = set(appeals.values_list("pk", flat=True))
        self.assertEqual(found, {"operator": {self.unclear.pk}, "analyst": set(), "admin": {self.unclear.pk}})

    def test_period_by_moscow_days(self):
        # 15 сентября 23:30 по Москве уже 20:30 UTC того же дня, но граница суток считается по Москве.
        self.assertEqual(self.ids(date_from="2026-09-15", date_to="2026-09-15"), {self.courier.pk})
        self.assertEqual(self.ids(date_from="2026-09-16"), {self.unclear.pk, self.manual.pk})
        self.assertEqual(self.ids(date_to="2026-09-01"), {self.payment_appeal.pk})

    def test_wrong_period_is_reported_and_skipped(self):
        appeals, form = filter_appeals(QueryDict("date_from=2026-09-20&date_to=2026-09-10"))
        self.assertIn("date_to", form.errors)
        self.assertEqual(set(appeals.values_list("pk", flat=True)), {self.unclear.pk, self.manual.pk})

    def test_category(self):
        self.assertEqual(self.ids(category="payment"), {self.payment_appeal.pk})
        self.assertEqual(self.ids(category="delivery"), {self.courier.pk, self.manual.pk})

    def test_without_category(self):
        self.assertEqual(self.ids(category="none"), {self.unclear.pk})

    def test_reason(self):
        reason = Reason.objects.get(name="Задержка доставки")
        self.assertEqual(self.ids(reason=reason.pk), {self.manual.pk})

    def test_tags_any_of_selected(self):
        self.assertEqual(self.ids(tags=[self.ios.pk]), {self.payment_appeal.pk, self.manual.pk})
        self.assertEqual(self.ids(tags=[self.android.pk, self.vip.pk]), {self.courier.pk, self.manual.pk})
        appeals, _ = filter_appeals(QueryDict(f"tags={self.ios.pk}&tags={self.android.pk}"))
        self.assertEqual(appeals.count(), 2)  # обращение с двумя тегами не задваивается

    def test_channel(self):
        self.assertEqual(self.ids(channel="phone"), {self.courier.pk})

    def test_status(self):
        self.assertEqual(self.ids(status="closed"), {self.unclear.pk})
        self.assertEqual(self.ids(status="open"), {self.payment_appeal.pk, self.manual.pk})

    def test_source(self):
        self.assertEqual(self.ids(source="manual"), {self.manual.pk})
        self.assertEqual(self.ids(source="none"), {self.unclear.pk})

    def test_assignee(self):
        self.assertEqual(self.ids(assignee=self.operator.pk), {self.courier.pk})
        self.assertEqual(self.ids(assignee="none"), {self.payment_appeal.pk, self.unclear.pk})

    def test_combination_category_and_status(self):
        self.assertEqual(self.ids(category="delivery", status="open"), {self.manual.pk})

    def test_combination_text_and_channel(self):
        self.assertEqual(self.ids(q="дважды", channel="email"), {self.manual.pk})
        self.assertEqual(self.ids(q="дважды", channel="app"), set())

    def test_combination_period_tags_and_source(self):
        self.assertEqual(self.ids(date_from="2026-09-10", tags=[self.ios.pk], source="manual"), {self.manual.pk})
        self.assertEqual(self.ids(date_to="2026-09-10", tags=[self.ios.pk], source="manual"), set())

    def test_unknown_values_ignored(self):
        self.assertEqual(len(self.ids(category="nonexistent", channel="fax")), 4)

    def test_text_query_skips_service_words(self):
        self.assertEqual(str(text_query("оплата в магазине")), str(text_query("оплата магазине")))


class ListFilterViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        Appeal.objects.bulk_create(
            [Appeal(text=f"Обращение из чата {i}", channel="chat", created_at=at(1 + i % 28)) for i in range(60)]
        )
        Appeal.objects.create(text="Третий раз у меня не проходит оплата", channel="app", created_at=at(5))

    def setUp(self):
        self.client.force_login(User.objects.get(username="analyst"))

    def test_search_in_list(self):
        response = self.client.get(reverse("appeals:list"), {"q": "оплата не проходит"})
        self.assertContains(response, "Найдено: 1")

    def test_pagination_keeps_filter(self):
        first = self.client.get(reverse("appeals:list"), {"channel": "chat"})
        self.assertContains(first, "Найдено: 60")
        self.assertContains(first, "?channel=chat&amp;page=2")
        second = self.client.get(reverse("appeals:list"), {"channel": "chat", "page": 2})
        self.assertContains(second, "Найдено: 60")
        self.assertContains(second, "Страница 2 из 2")
        self.assertNotContains(second, "Третий раз у меня")

    def test_form_keeps_values_and_has_reset(self):
        response = self.client.get(reverse("appeals:list"), {"q": "оплата", "channel": "app"})
        self.assertContains(response, 'value="оплата"')
        self.assertContains(response, '<option value="app" selected>')
        self.assertContains(response, "Сбросить")

    def test_empty_result(self):
        self.assertContains(self.client.get(reverse("appeals:list"), {"q": "#999999"}), "По заданным условиям")

    def test_analyst_cannot_search_by_email(self):
        Appeal.objects.create(text="Где мой заказ", author_email="secret@mail.ru", created_at=at(6))
        self.assertContains(self.client.get(reverse("appeals:list"), {"q": "secret@mail.ru"}), "Найдено: 0")
        self.client.force_login(User.objects.get(username="operator"))
        self.assertContains(self.client.get(reverse("appeals:list"), {"q": "secret@mail.ru"}), "Найдено: 1")
