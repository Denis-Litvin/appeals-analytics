import re
from datetime import datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from appeals.management.commands.generate_appeals import generate
from appeals.models import Appeal, Reason

MSK = ZoneInfo("Europe/Moscow")
END = datetime(2026, 9, 30, 15, 30, tzinfo=MSK)
# Сессия, пользователь, права пользователя и групп, группы в шапке, непрочитанные уведомления в меню
# аналитика; списки формы фильтров (категории, причины для подписей, причины для вариантов, операторы, теги);
# count, страница, теги строк.
LIST_QUERIES = 14
DETAIL_QUERIES = 10  # то же без count и страницы, плюс обращение, теги, причины фраз, похожие


def rows(response):
    return re.findall(r'<td class="nowrap"><a href="/appeals/(\d+)/">', response.content.decode())


class ListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        generate(120, 1, seed=3, end=END)
        User.objects.create_user("nobody")

    def get_as(self, username, url):
        self.client.force_login(User.objects.get(username=username))
        return self.client.get(url)

    def test_all_roles_see_list(self):
        for username in ("operator", "analyst", "admin"):
            with self.subTest(user=username):
                response = self.get_as(username, reverse("appeals:list"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Найдено: 120")

    def test_without_role_forbidden(self):
        self.assertEqual(self.get_as("nobody", reverse("appeals:list")).status_code, 403)

    def test_pagination_by_50(self):
        first = self.get_as("operator", reverse("appeals:list"))
        self.assertEqual(len(rows(first)), 50)
        last = self.get_as("operator", reverse("appeals:list") + "?page=3")
        self.assertEqual(len(rows(last)), 20)
        self.assertContains(last, "Страница 3 из 3")
        # Номер страницы вне диапазона не ломает список.
        self.assertEqual(self.get_as("operator", reverse("appeals:list") + "?page=99").status_code, 200)

    def test_ordering(self):
        newest = Appeal.objects.order_by("-created_at", "-id").first()
        oldest = Appeal.objects.order_by("created_at", "id").first()
        self.assertEqual(rows(self.get_as("operator", reverse("appeals:list")))[0], str(newest.pk))
        self.assertEqual(rows(self.get_as("operator", reverse("appeals:list") + "?order=old"))[0], str(oldest.pk))

    def test_page_links_keep_ordering(self):
        response = self.get_as("operator", reverse("appeals:list") + "?order=old")
        self.assertContains(response, "?order=old&amp;page=2")

    def test_query_count_does_not_depend_on_page(self):
        self.client.force_login(User.objects.get(username="analyst"))
        for url in (reverse("appeals:list"), reverse("appeals:list") + "?page=2&order=old"):
            with self.subTest(url=url), self.assertNumQueries(LIST_QUERIES):
                self.client.get(url)


class DetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        cls.when = datetime(2026, 9, 10, 12, 0, tzinfo=MSK)
        cls.appeal = Appeal.objects.create(
            text="С карты списали дважды за один заказ, верните деньги",
            author_name="Иван Петров",
            author_email="ivan.petrov@mail.ru",
            created_at=cls.when,
        )
        reason = cls.appeal.reason

        def same_reason(days):
            Appeal.objects.bulk_create(
                [
                    Appeal(
                        text=f"Двойное списание, пример {days}",
                        created_at=cls.when + timedelta(days=days),
                        category=reason.category,
                        reason=reason,
                        category_source=Appeal.Source.AUTO,
                    )
                ]
            )

        same_reason(-3)
        same_reason(5)
        same_reason(20)  # за пределами 7 дней
        Appeal.objects.create(text="Курьер опоздал на два часа", created_at=cls.when)

    def get_as(self, username, appeal=None):
        self.client.force_login(User.objects.get(username=username))
        return self.client.get(reverse("appeals:detail", args=[(appeal or self.appeal).pk]))

    def test_all_roles_see_detail(self):
        for username in ("operator", "analyst", "admin"):
            with self.subTest(user=username):
                response = self.get_as(username)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Двойное списание")
                self.assertContains(response, "списали дважды")

    def test_personal_data_masked_for_analyst(self):
        analyst = self.get_as("analyst")
        self.assertNotContains(analyst, "Иван Петров")
        self.assertNotContains(analyst, "ivan.petrov@mail.ru")
        self.assertContains(analyst, "И*** П***")
        self.assertContains(analyst, "i***@mail.ru")
        for username in ("operator", "admin"):
            with self.subTest(user=username):
                self.assertContains(self.get_as(username), "ivan.petrov@mail.ru")

    def test_list_does_not_show_personal_data(self):
        self.client.force_login(User.objects.get(username="operator"))
        self.assertNotContains(self.client.get(reverse("appeals:list")), "ivan.petrov@mail.ru")

    def test_matched_words_highlighted(self):
        html = self.get_as("operator").content.decode()
        self.assertIn("<mark>списали</mark>", html)
        self.assertIn("<mark>дважды</mark>", html)

    def test_similar_appeals(self):
        context = self.get_as("operator").context
        texts = [a.text for a in context["similar"]]
        self.assertEqual(texts, ["Двойное списание, пример 5", "Двойное списание, пример -3"])

    def test_unclear_appeal(self):
        unclear = Appeal.objects.create(text="Здравствуйте, подскажите режим работы")
        response = self.get_as("operator", unclear)
        self.assertContains(response, "Категория не определена")
        self.assertContains(response, "без категории")

    def test_manual_category_explained(self):
        reason = Reason.objects.get(name="Задержка доставки")
        manual = Appeal.objects.create(
            text="Здравствуйте", category=reason.category, reason=reason, category_source=Appeal.Source.MANUAL
        )
        self.assertContains(self.get_as("operator", manual), "поставил оператор вручную")

    def test_html_is_escaped(self):
        bad = Appeal.objects.create(text="<script>alert(1)</script> не проходит оплата")
        response = self.get_as("operator", bad)
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")
        self.client.force_login(User.objects.get(username="operator"))
        self.assertNotContains(self.client.get(reverse("appeals:list")), "<script>alert(1)</script>")

    def test_missing_appeal(self):
        self.client.force_login(User.objects.get(username="operator"))
        self.assertEqual(self.client.get(reverse("appeals:detail", args=[999999])).status_code, 404)

    def test_query_count(self):
        self.client.force_login(User.objects.get(username="analyst"))
        with self.assertNumQueries(DETAIL_QUERIES):
            self.client.get(reverse("appeals:detail", args=[self.appeal.pk]))

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("appeals:detail", args=[self.appeal.pk]))
        self.assertEqual(response.status_code, 302)
