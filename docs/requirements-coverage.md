# Покрытие требований

Для каждого кода из задания в таблице указано:
- где требование реализовано;
- какой тест его проверяет;
- как увидеть его в интерфейсе на демо-базе (`python manage.py setup_demo`).

Тесты указаны как `файл: класс или функция`, запуск всех тестов: `python manage.py test`.

## Обязательная функциональность

| Код | Требование | Статус | Где в коде | Тест | Как увидеть |
|---|---|---|---|---|---|
| О1 | Хранение обращений | сделано | appeals/models.py `Appeal`; создание в appeals/views.py `appeal_create`, POST /api/appeals/ | appeals/tests/test_models.py; test_edit.py `test_create_gets_auto_category`; api/tests/test_api.py `test_create_gets_category` | operator, «Новое обращение» |
| О2 | Таблица обращений | сделано | appeals/views.py `appeal_list`, templates/appeals/list.html | appeals/tests/test_views.py `ListTests` | «Обращения», «Сначала старые», «Дальше» |
| О3 | Карточка обращения | сделано | appeals/views.py `appeal_detail`, `highlight`, templates/appeals/detail.html | test_views.py `DetailTests` | клик по номеру в списке |
| О4 | Поиск и фильтры | сделано | appeals/filters.py, appeals/forms.py `AppealFilterForm` | appeals/tests/test_filters.py | форма над списком |
| О5 | Распределение по категориям | сделано | appeals/classify.py, appeals/data/dictionary.json, ручная категория в `appeal_edit` | appeals/tests/test_classify.py; test_edit.py | карточка, блок «Почему такая категория»; «Изменить» |
| О6 | Статистика | сделано | analytics/stats.py `summary`, `breakdown`, `weekday_hour`; views.py `stats_page` | analytics/tests/test_stats.py `StatsMatchOrmTests` | analyst, «Статистика» |
| О7 | Частые причины | сделано | analytics/stats.py `top_reasons`, `by_category` | test_stats.py `test_top_reasons`, `test_category_breakdown` | «Статистика», «Частые причины» |
| О8 | Графики | сделано | analytics/charts.py, static/js/charts.js | analytics/tests/test_charts.py; test_page_charts.py | «Дашборд», «Статистика» |
| О9 | Аналитический отчёт | сделано | analytics/reports.py, templates/analytics/report.html, static/css/print.css | analytics/tests/test_reports.py | «Отчёты», «Печать» |

## Дополнительная функциональность

| Код | Требование | Статус | Где в коде | Тест | Как увидеть |
|---|---|---|---|---|---|
| Д1 | Автокатегория по ключевым словам | сделано | appeals/classify.py, appeals/text.py | test_classify.py: размеченный набор 55 из 55, опечатки, отрицания; test_demo_phrases.py; test_generator.py `test_auto_category_accuracy` | operator создаёт «Курер не приехал», категория «Доставка» |
| Д2 | Поиск по тексту и фильтры | сделано | appeals/filters.py `text_query`, `apply_filters` | test_filters.py `FilterTests` | поиск `"списали дважды"`, `#100` |
| Д3 | Теги | сделано | appeals/models.py `Tag`, формы создания и правки, фильтр `tags` | test_models.py `test_tags`; test_filters.py `test_tags_any_of_selected`; test_api.py `test_create_gets_category` | теги в списке, фильтр «Теги» |
| Д4 | Интерактивные графики и дашборд | сделано | analytics/charts.py `list_link`, static/js/charts.js | test_charts.py `test_category_click_opens_same_slice`, `test_analyst_sees_charts_offline` | «Дашборд», клик по столбцу |
| Д5 | Экспорт | сделано | analytics/export.py; views `report_export`, `appeal_export` | analytics/tests/test_export.py | «Скачать XLSX» в «Отчётах», «Выгрузить CSV» в «Обращениях» |
| Д6 | Сравнение периодов | сделано | analytics/stats.py `compare`, forms.py `CompareForm`, charts.py `compare_*` | analytics/tests/test_compare.py; test_page_charts.py `test_compare_*` | «Сравнение», «Месяц к месяцу» |
| Д7 | Рейтинг проблем | сделано | analytics/stats.py `problems`, charts.py `problems` | test_stats.py `ProblemsTests`; test_page_charts.py `test_problems_*` | «Рейтинг проблем» |
| Д8 | Уведомления о резком росте | сделано | analytics/spikes.py, context_processors.py, commands/check_spikes.py, templates/analytics/alerts.html | analytics/tests/test_spikes.py; tests/test_scenario.py | счётчик у «Уведомлений» под analyst |
| Д9 | REST API | сделано | api/, docs/api.md | api/tests/test_api.py | curl из docs/api.md |
| Д10 | Права доступа | сделано | appeals/roles.py, `permission_required` во всех view, api/permissions.py, маскирование `author_for`, поиск по email только для тех, кто видит email | tests/test_access_matrix.py; test_roles.py; test_export.py `test_appeals_masked_for_analyst`; test_api.py `test_email_masked_for_analyst`; test_filters.py `test_email_search_only_for_those_who_see_email` | войти как operator и как analyst |

## Этапы

Шаги и коммиты каждого этапа перечислены в [stages.md](stages.md).

| Код | Этап | Статус | Где видно |
|---|---|---|---|
| А1 | Изучение требований | сделано | docs/requirements.md |
| А2 | Проектирование базы данных | сделано | docs/database.md, appeals/migrations, analytics/migrations |
| А3 | Реализация хранения обращений | сделано | appeals/models.py, dictionary.json, генератор демо-данных |
| А4 | Реализация поиска и фильтрации | сделано | appeals/filters.py |
| А5 | Реализация аналитических функций | сделано | analytics/stats.py, spikes.py, reports.py, export.py |
| А6 | Разработка визуализации | сделано | analytics/charts.py, static/js/charts.js |
| А7 | Тестирование | сделано | 287 тестов, покрытие 99%, docs/testing.md |
| А8 | Подготовка документации | сделано | README.md, docs/ |

## Результат

| Код | Результат | Статус | Чем подтверждён |
|---|---|---|---|
| Р1 | Работоспособный сервис с хранением, категоризацией, статистикой и визуализацией | сделано | проверка на чистой копии ниже; сквозной сценарий tests/test_scenario.py |
| Р2 | Репозиторий с исходным кодом, инструкцией по запуску и описанием функциональности | сделано | README.md: запуск, возможности по кодам, ограничения; github.com/Denis-Litvin/appeals-analytics, тег v1.0 |

## Проверка на чистой копии

Итоговая проверка 10.10.2026: `git clone` с GitHub в пустую папку и шаги README по порядку, без правок руками.

| Что | Результат |
|---|---|
| Python | 3.13 и 3.11, на обоих версиях установка и тесты проходят |
| `pip install -r requirements.txt` | Django 5.2.18, djangorestframework 3.18.3, pandas 3.0.6, plotly 6.9.0, openpyxl 3.1.5, snowballstemmer 3.1.1; numpy 2.5.3 на Python 3.13 и 2.4.6 на 3.11 |
| `python manage.py setup_demo` | 6000 обращений, около 20 уведомлений о росте, 6-7 с |
| `python manage.py test` | 287 тестов, OK, около 40 с |
| Вход под демо-учётками и обход страниц в браузере | operator: обращения 200, аналитика 403; analyst: создание и правка 403, аналитика 200; admin: всё 200, админка открыта только ему; ошибок JavaScript нет, графики нарисованы |
| API | без токена 401; operator: /api/summary/ 403, /api/appeals/ 200; analyst и admin: оба адреса 200 |
| Работа без сети | браузеру запрещены все адреса, кроме сервиса: графики на пяти страницах рисуются, внешних запросов нет |
| Открытие выгрузок | LibreOffice Calc читает XLSX со всеми листами и форматами, CSV раскладывается по колонкам с кириллицей |

В самом Microsoft Excel файлы не открывались: его нет в среде проверки. CSV рассчитан на Excel с русскими региональными настройками, при английских его нужно открывать через «Данные → Из текста/CSV» или брать XLSX. Это написано в README.
