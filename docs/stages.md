# Этапы работы

Проект собирался по плану из 21 шага, по одному коммиту на шаг, и завершился итоговой проверкой. Ниже показано, какие шаги закрывают этапы А1-А8 из задания, а затем каждый шаг с коммитом и файлами. Посмотреть изменения шага можно командой `git show <коммит>`.

## Этапы задания

| Этап | Шаги | Коммиты | Основные файлы |
|---|---|---|---|
| А1 Изучение требований | 1 | 476ddca | docs/requirements.md |
| А2 Проектирование базы данных | 2, 3 | ab9da3e, a986740 | appeals/models.py, analytics/models.py, миграции, docs/database.md |
| А3 Реализация хранения обращений | 2, 4, 5, 7, 9 | ab9da3e, 6dcdbda, 6f79b4d, 30e288b, d4b2645 | appeals/models.py, appeals/data/dictionary.json, appeals/classify.py, generate_appeals.py, appeals/views.py |
| А4 Реализация поиска и фильтрации | 8, 10 | f114c0c, e6b629e | appeals/filters.py, appeals/forms.py, templates/appeals/list.html |
| А5 Реализация аналитических функций | 5, 11, 12, 13, 16, 17, 18 | 6f79b4d, c7f7234, 3b09f47, 82add98, 8fc1b2c, 03dbf6c, 53d1190 | appeals/classify.py, analytics/stats.py, analytics/spikes.py, analytics/reports.py, analytics/export.py, api/views.py |
| А6 Разработка визуализации | 14, 15, 16 | be6a4d1, 6981579, 8fc1b2c | analytics/charts.py, static/js/charts.js, шаблоны analytics/ |
| А7 Тестирование | каждый шаг, отдельно 19 | все, 7f4492e | тесты в appeals/tests, analytics/tests, api/tests, tests/; docs/testing.md |
| А8 Подготовка документации | 1, 2, 7, 18, 19, 20 | 476ddca, ab9da3e, 30e288b, 53d1190, 7f4492e, d6b017f | README.md и docs/ |

Тесты писались вместе с кодом на каждом шаге и лежат в том же коммите. Шаг 19 добавил проверку всех адресов по ролям, сквозной сценарий и замер покрытия.

## Шаги

| Шаг | Коммит | Что сделано | Коды | Основные файлы |
|---|---|---|---|---|
| 0 | нет | план из 21 шага, проверка плана | | |
| 1 | 476ddca | каркас Django, вход, анализ требований | А1 | config/, docs/requirements.md |
| 2 | ab9da3e | схема данных: обращения, справочники, теги, уведомления | А2, О1, О5, Д3 | appeals/models.py, analytics/models.py, docs/database.md |
| 3 | a986740 | роли оператора, аналитика и администратора, права на разделы, маскирование | Д10 | appeals/roles.py, setup_roles.py, templates/403.html |
| 4 | 6dcdbda | справочник: 8 категорий, 30 причин, ключевые фразы, 10 тегов | О5, Д3 | appeals/data/dictionary.json, load_dictionary.py |
| 5 | 6f79b4d | нормализация текста и автокатегория по ключевым фразам | Д1, О5 | appeals/text.py, appeals/classify.py, recategorize.py |
| 6 | b1196b7 | банк формулировок для генератора, доработка опечаток | Д1 | appeals/demo_phrases.py |
| 7 | 30e288b | генератор 6000 обращений с всплесками, команда setup_demo | О1, А3 | generate_appeals.py, setup_demo.py, docs/demo-data.md |
| 8 | f114c0c | список обращений и карточка с объяснением категории | О2, О3 | appeals/views.py, list.html, detail.html |
| 9 | d4b2645 | создание и правка обращений, ручная категория, теги | О1, О5, Д3 | appeals/forms.py, form.html |
| 10 | e6b629e | поиск по основам слов и фильтры | О4, Д2 | appeals/filters.py |
| 11 | c7f7234 | статистика, частые причины, рейтинг проблем | О6, О7, Д7 | analytics/stats.py, stats.html, problems.html |
| 12 | 3b09f47 | сравнение двух периодов | Д6 | analytics/stats.py, compare.html |
| 13 | 82add98 | поиск всплесков, уведомления, письма | Д8 | analytics/spikes.py, check_spikes.py, alerts.html |
| 14 | be6a4d1 | модуль графиков и дашборд | Д4, О8 | analytics/charts.py, static/js/charts.js, dashboard.html |
| 15 | 6981579 | графики на страницах статистики, рейтинга и сравнения | О8, Д6, Д7 | analytics/charts.py |
| 16 | 8fc1b2c | аналитический отчёт с выводами и версией для печати | О9 | analytics/reports.py, report.html, print.css |
| 17 | 03dbf6c | выгрузка отчёта и списка в XLSX и CSV | Д5 | analytics/export.py |
| 18 | 53d1190 | REST API с токенами | Д9, Д10 | api/, docs/api.md |
| 19 | 7f4492e | матрица доступа, сквозной сценарий, покрытие | А7 | tests/, docs/testing.md, .coveragerc |
| 20 | d6b017f | документация | А8, Р2 | README.md, docs/architecture.md, docs/user-guide.md, docs/stages.md |
| 21 | 62502bb | финальная сверка на чистой копии, поиск по email только для тех, кто видит email, таблица покрытия требований | Р1, Р2, Д10 | docs/requirements-coverage.md, appeals/filters.py |
| итог | последний коммит, тег v1.0 | проверка клона с GitHub по README, Python 3.11, проверка без сети и в LibreOffice, чистка стиля | Р1, Р2 | README.md, docs/testing.md, analytics/export.py |
