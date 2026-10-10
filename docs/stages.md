# Этапы работы

Проект собирался по плану из 21 шага, по одному коммиту на шаг. Ниже показано, какие шаги закрывают этапы А1-А8 из задания, а затем каждый шаг с коммитом и файлами. Посмотреть изменения шага можно командой `git show <коммит>`.

## Этапы задания

| Этап | Шаги | Коммиты | Основные файлы |
|---|---|---|---|
| А1 Изучение требований | 1 | ff9b5e4 | docs/requirements.md |
| А2 Проектирование базы данных | 2, 3 | 7be90c7, a5cd991 | appeals/models.py, analytics/models.py, миграции, docs/database.md |
| А3 Реализация хранения обращений | 2, 4, 5, 7, 9 | 7be90c7, 4c370a2, e5d0195, 1ebb969, 35b51d6 | appeals/models.py, appeals/data/dictionary.json, appeals/classify.py, generate_appeals.py, appeals/views.py |
| А4 Реализация поиска и фильтрации | 8, 10 | 981d96b, 71f8e55 | appeals/filters.py, appeals/forms.py, templates/appeals/list.html |
| А5 Реализация аналитических функций | 5, 11, 12, 13, 16, 17, 18 | e5d0195, d4473fa, 57e1908, 665019c, b540561, e4cb107, d65c73b | appeals/classify.py, analytics/stats.py, analytics/spikes.py, analytics/reports.py, analytics/export.py, api/views.py |
| А6 Разработка визуализации | 14, 15, 16 | d08e9d2, f0ebd5f, b540561 | analytics/charts.py, static/js/charts.js, шаблоны analytics/ |
| А7 Тестирование | каждый шаг, отдельно 19 | все, 5f0cda5 | тесты в appeals/tests, analytics/tests, api/tests, tests/; docs/testing.md |
| А8 Подготовка документации | 1, 2, 7, 18, 19, 20 | ff9b5e4, 7be90c7, 1ebb969, d65c73b, 5f0cda5, 2050eea | README.md и docs/ |

Тесты писались вместе с кодом на каждом шаге и лежат в том же коммите. Шаг 19 добавил проверку всех адресов по ролям, сквозной сценарий и замер покрытия.

## Шаги

| Шаг | Коммит | Что сделано | Коды | Основные файлы |
|---|---|---|---|---|
| 0 | нет | план из 21 шага, проверка плана | | |
| 1 | ff9b5e4 | каркас Django, вход, анализ требований | А1 | config/, docs/requirements.md |
| 2 | 7be90c7 | схема данных: обращения, справочники, теги, уведомления | А2, О1, О5, Д3 | appeals/models.py, analytics/models.py, docs/database.md |
| 3 | a5cd991 | роли оператора, аналитика и администратора, права на разделы, маскирование | Д10 | appeals/roles.py, setup_roles.py, templates/403.html |
| 4 | 4c370a2 | справочник: 8 категорий, 30 причин, ключевые фразы, 10 тегов | О5, Д3 | appeals/data/dictionary.json, load_dictionary.py |
| 5 | e5d0195 | нормализация текста и автокатегория по ключевым фразам | Д1, О5 | appeals/text.py, appeals/classify.py, recategorize.py |
| 6 | 526b122 | банк формулировок для генератора, доработка опечаток | Д1 | appeals/demo_phrases.py |
| 7 | 1ebb969 | генератор 6000 обращений с всплесками, команда setup_demo | О1, А3 | generate_appeals.py, setup_demo.py, docs/demo-data.md |
| 8 | 981d96b | список обращений и карточка с объяснением категории | О2, О3 | appeals/views.py, list.html, detail.html |
| 9 | 35b51d6 | создание и правка обращений, ручная категория, теги | О1, О5, Д3 | appeals/forms.py, form.html |
| 10 | 71f8e55 | поиск по основам слов и фильтры | О4, Д2 | appeals/filters.py |
| 11 | d4473fa | статистика, частые причины, рейтинг проблем | О6, О7, Д7 | analytics/stats.py, stats.html, problems.html |
| 12 | 57e1908 | сравнение двух периодов | Д6 | analytics/stats.py, compare.html |
| 13 | 665019c | поиск всплесков, уведомления, письма | Д8 | analytics/spikes.py, check_spikes.py, alerts.html |
| 14 | d08e9d2 | модуль графиков и дашборд | Д4, О8 | analytics/charts.py, static/js/charts.js, dashboard.html |
| 15 | f0ebd5f | графики на страницах статистики, рейтинга и сравнения | О8, Д6, Д7 | analytics/charts.py |
| 16 | b540561 | аналитический отчёт с выводами и версией для печати | О9 | analytics/reports.py, report.html, print.css |
| 17 | e4cb107 | выгрузка отчёта и списка в XLSX и CSV | Д5 | analytics/export.py |
| 18 | d65c73b | REST API с токенами | Д9, Д10 | api/, docs/api.md |
| 19 | 5f0cda5 | матрица доступа, сквозной сценарий, покрытие | А7 | tests/, docs/testing.md, .coveragerc |
| 20 | 2050eea | документация | А8, Р2 | README.md, docs/architecture.md, docs/user-guide.md, docs/stages.md |
| 21 | тег v1.0 | финальная сверка на чистой копии, поиск по email только для тех, кто видит email, таблица покрытия требований | Р1, Р2, Д10 | docs/requirements-coverage.md, appeals/filters.py |
