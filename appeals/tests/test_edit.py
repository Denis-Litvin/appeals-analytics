from io import StringIO

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from appeals.models import Appeal, Category, Reason, Tag


class EditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        cls.operator = User.objects.get(username="operator")
        cls.operator2 = User.objects.get(username="operator2")
        cls.payment = Category.objects.get(slug="payment")
        cls.delivery = Category.objects.get(slug="delivery")
        cls.late = Reason.objects.get(name="Задержка доставки")
        cls.double = Reason.objects.get(name="Двойное списание")

    def setUp(self):
        self.client.force_login(self.operator)
        self.appeal = Appeal.objects.create(text="С карты списали дважды за один заказ")

    def edit(self, **data):
        fields = {"status": self.appeal.status, "assignee": "", "category": "", "reason": "", "tags": []}
        if self.appeal.category_id:
            fields["category"] = self.appeal.category_id
        if self.appeal.reason_id:
            fields["reason"] = self.appeal.reason_id
        if self.appeal.assignee_id:
            fields["assignee"] = self.appeal.assignee_id
        fields.update(data)
        response = self.client.post(reverse("appeals:edit", args=[self.appeal.pk]), fields)
        self.appeal.refresh_from_db()
        return response

    def test_create_gets_auto_category(self):
        vip = Tag.objects.get(name="VIP")
        response = self.client.post(
            reverse("appeals:create"),
            {
                "channel": "phone",
                "author_name": "Анна Иванова",
                "author_email": "anna@mail.ru",
                "subject": "",
                "text": "Курьер не приехал, ждала весь день",
                "tags": [vip.pk],
            },
        )
        appeal = Appeal.objects.latest("id")
        self.assertRedirects(response, reverse("appeals:detail", args=[appeal.pk]))
        self.assertEqual(appeal.category, self.delivery)
        self.assertEqual(appeal.reason.name, "Курьер не приехал или опоздал")
        self.assertEqual(appeal.category_source, Appeal.Source.AUTO)
        self.assertEqual(list(appeal.tags.all()), [vip])
        self.assertIn("Категория: Доставка", str(list(get_messages(response.wsgi_request))[0]))

    def test_create_validation(self):
        response = self.client.post(reverse("appeals:create"), {"channel": "web", "text": "", "author_email": "не почта"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Appeal.objects.count(), 1)
        self.assertTrue(response.context["form"].errors.keys() >= {"text", "author_email"})

    def test_manual_category_survives_recategorize(self):
        self.assertEqual(self.appeal.category, self.payment)
        self.edit(category=self.delivery.pk, reason=self.late.pk)
        self.assertEqual(self.appeal.category_source, Appeal.Source.MANUAL)
        self.assertEqual(self.appeal.reason, self.late)
        call_command("recategorize", stdout=StringIO())
        self.appeal.refresh_from_db()
        self.assertEqual((self.appeal.category, self.appeal.reason), (self.delivery, self.late))

    def test_revert_to_auto(self):
        self.edit(category=self.delivery.pk, reason=self.late.pk)
        response = self.client.post(reverse("appeals:auto_category", args=[self.appeal.pk]))
        self.assertRedirects(response, reverse("appeals:detail", args=[self.appeal.pk]))
        self.appeal.refresh_from_db()
        self.assertEqual((self.appeal.category, self.appeal.reason), (self.payment, self.double))
        self.assertEqual(self.appeal.category_source, Appeal.Source.AUTO)

    def test_revert_needs_post(self):
        self.assertEqual(self.client.get(reverse("appeals:auto_category", args=[self.appeal.pk])).status_code, 405)

    def test_manual_without_category(self):
        self.edit(category="", reason="")
        self.assertIsNone(self.appeal.category)
        self.assertEqual(self.appeal.category_source, Appeal.Source.MANUAL)
        call_command("recategorize", stdout=StringIO())
        self.appeal.refresh_from_db()
        self.assertIsNone(self.appeal.category)

    def test_status_change_keeps_auto_category(self):
        self.edit(status="in_work")
        self.assertEqual(self.appeal.category_source, Appeal.Source.AUTO)
        self.assertEqual(self.appeal.assignee, self.operator)  # взял в работу без исполнителя: назначен он сам
        self.assertIsNone(self.appeal.resolved_at)

    def test_resolved_at_follows_status(self):
        self.edit(status="resolved", assignee=self.operator2.pk)
        self.assertIsNotNone(self.appeal.resolved_at)
        self.assertEqual(self.appeal.assignee, self.operator2)
        first = self.appeal.resolved_at
        self.edit(status="closed")
        self.assertEqual(self.appeal.resolved_at, first)
        self.edit(status="in_work")
        self.assertIsNone(self.appeal.resolved_at)

    def test_reason_must_match_category(self):
        response = self.edit(category=self.delivery.pk, reason=self.double.pk)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "относится к категории")
        self.assertEqual(self.appeal.category_source, Appeal.Source.AUTO)

    def test_reason_without_category_takes_its_category(self):
        self.edit(category="", reason=self.late.pk)
        self.assertEqual(self.appeal.category, self.delivery)
        self.assertEqual(self.appeal.category_source, Appeal.Source.MANUAL)

    def test_tags(self):
        ios, repeat = Tag.objects.get(name="iOS"), Tag.objects.get(name="Повторное")
        self.edit(tags=[ios.pk, repeat.pk])
        self.assertEqual(set(self.appeal.tags.all()), {ios, repeat})
        self.edit(tags=[])
        self.assertFalse(self.appeal.tags.exists())

    def test_reason_options_carry_category(self):
        html = self.client.get(reverse("appeals:edit", args=[self.appeal.pk])).content.decode()
        self.assertIn(f'data-category="{self.delivery.pk}"', html)

    def test_buttons_on_detail(self):
        detail = reverse("appeals:detail", args=[self.appeal.pk])
        self.assertContains(self.client.get(detail), "Изменить")
        self.assertNotContains(self.client.get(detail), "Вернуть автоопределение")
        self.edit(category=self.delivery.pk, reason=self.late.pk)
        self.assertContains(self.client.get(detail), "Вернуть автоопределение")
        self.client.force_login(User.objects.get(username="analyst"))
        self.assertNotContains(self.client.get(detail), "Изменить")
        self.assertNotContains(self.client.get(reverse("appeals:list")), "Новое обращение")


class EditAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_dictionary", stdout=StringIO())
        call_command("setup_roles", "--demo-users", stdout=StringIO())
        cls.appeal = Appeal.objects.create(text="Курьер опоздал")

    def test_analyst_forbidden(self):
        self.client.force_login(User.objects.get(username="analyst"))
        urls = [reverse("appeals:create"), reverse("appeals:edit", args=[self.appeal.pk])]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {"text": "x"}).status_code, 403)
        auto = reverse("appeals:auto_category", args=[self.appeal.pk])
        self.assertEqual(self.client.post(auto).status_code, 403)
        self.assertEqual(Appeal.objects.count(), 1)

    def test_operator_and_admin_allowed(self):
        for username in ("operator", "admin"):
            self.client.force_login(User.objects.get(username=username))
            with self.subTest(user=username):
                self.assertEqual(self.client.get(reverse("appeals:create")).status_code, 200)
                self.assertEqual(self.client.get(reverse("appeals:edit", args=[self.appeal.pk])).status_code, 200)
