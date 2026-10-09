# Анализ обращений пользователей

Веб-приложение для хранения обращений пользователей, их категоризации и анализа: статистика, частые причины, графики, отчёты, уведомления о всплесках, REST API.

Проект в разработке. Сейчас готов каркас: вход в систему, меню разделов и заглушки на их месте. Анализ требований лежит в [docs/requirements.md](docs/requirements.md).

## Стек

Python 3.10 или новее, Django 5.2, SQLite. Для аналитики pandas и numpy, для графиков Plotly, для выгрузки openpyxl, для поиска по словоформам snowballstemmer. Полный список зависимостей в `requirements.txt`.

## Запуск

Создать и активировать виртуальное окружение:

```
python -m venv .venv
source .venv/bin/activate        # macOS и Linux
.venv\Scripts\activate           # Windows
```

Установить зависимости, создать базу и пользователя, запустить сервер:

```
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Приложение откроется на http://127.0.0.1:8000/. Демо-данные и учётки по ролям появятся позже, тогда запуск сократится до команды `python manage.py setup_demo`.

## PostgreSQL

По умолчанию используется файл `db.sqlite3` в корне проекта. Для PostgreSQL нужно поставить драйвер (`pip install "psycopg[binary]"`) и задать переменные окружения `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`.
