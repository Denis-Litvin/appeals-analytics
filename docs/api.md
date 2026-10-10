# REST API

API отдаёт те же данные, что страницы сайта: числа считаются теми же функциями, а фильтры разбираются теми же формами. Все адреса начинаются с `/api/`, ответы приходят в JSON, время указано по Москве со смещением `+03:00`.

## Доступ

Доступ к API выдаётся по токену. Токен получают один раз по логину и паролю, затем передают в каждом запросе в заголовке `Authorization: Token <токен>`.

```
curl -X POST -d "username=analyst&password=demo12345" http://127.0.0.1:8000/api/auth/token/
{"token":"<40 символов>"}

export TOKEN=<токен из ответа>
curl -H "Authorization: Token $TOKEN" http://127.0.0.1:8000/api/summary/
```

Токен действует, пока его не удалят в админке (раздел «Токены»).

Коды ответов:

| Код | Когда |
|---|---|
| 200, 201 | запрос выполнен, обращение создано |
| 400 | неверный параметр, в ответе указано поле и ошибка: `{"date_from": ["Введите правильную дату."]}` |
| 401 | нет токена или токен неверный |
| 403 | у роли нет права на этот запрос |
| 404 | обращения с таким номером нет |

Права ролей:

| Запрос | Оператор | Аналитик | Администратор |
|---|---|---|---|
| Статистика: summary, categories, reasons/top, problems, timeseries, compare, alerts | 403 | да | да |
| Обращения: список и карточка | да | да, имя и email замаскированы | да |
| Создание обращения | да | 403 | да |

## Фильтры периода

Параметры для `summary`, `categories`, `reasons/top`, `problems` и `timeseries` те же, что у формы на странице «Статистика»:

| Параметр | Значение |
|---|---|
| `date_from`, `date_to` | даты `ГГГГ-ММ-ДД`, сутки по Москве. Без них берутся последние 30 дней, период не длиннее 366 дней |
| `category` | slug категории (`payment`, `delivery`, ...) или `none` для обращений без категории |
| `channel` | `app`, `web`, `email`, `phone`, `chat` |

## Статистика

`GET /api/summary/` возвращает сводку за период. Это те же числа, что в плитках страницы «Статистика».

```
curl -H "Authorization: Token $TOKEN" "http://127.0.0.1:8000/api/summary/?date_from=2026-09-10&date_to=2026-10-09"
{"period":{"date_from":"2026-09-10","date_to":"2026-10-09","days":30},"total":1245,"days":30,"per_day":41.5,
 "open_count":195,"open_share":0.1566,"without_category":166,"without_category_share":0.1333,
 "manual_share":0.0426,"median_resolution_hours":15.1}
```

Доли передаются числом от 0 до 1, в примерах ниже они округлены. Если в периоде нет решённых обращений, медиана времени решения равна `null`.

`GET /api/categories/` возвращает распределение по категориям. Обращения без категории идут отдельной строкой со slug `none`.

```
curl -H "Authorization: Token $TOKEN" "http://127.0.0.1:8000/api/categories/?channel=app"
{"period":{"date_from":"2026-09-11","date_to":"2026-10-10","days":30},"total":485,
 "results":[{"name":"Доставка","slug":"delivery","count":121,"share":0.2495},...]}
```

`GET /api/reasons/top/?limit=10` возвращает самые частые причины. Параметр `limit` принимает значения от 1 до 50.

```
curl -H "Authorization: Token $TOKEN" "http://127.0.0.1:8000/api/reasons/top/?limit=3"
{"period":{...},"results":[{"reason_id":5,"name":"Задержка доставки","category":"Доставка","count":142,"share":0.114},...]}
```

`GET /api/problems/` возвращает рейтинг причин. Для каждой причины есть место, место в предыдущем периоде такой же длины, прирост, доля нерешённых и медиана времени решения в часах. Если причины в предыдущем периоде не было, `growth` и `prev_rank` равны `null`.

```
curl -H "Authorization: Token $TOKEN" "http://127.0.0.1:8000/api/problems/?date_from=2026-09-10&date_to=2026-10-09"
{"period":{...},"previous_period":{"date_from":"2026-08-11","date_to":"2026-09-09","days":30},
 "results":[{"reason_id":5,"rank":1,"prev_rank":1,"rank_change":0,"name":"Задержка доставки","category":"Доставка",
 "category_slug":"delivery","count":142,"share":0.1141,"prev_count":106,"growth":0.3396,"open_share":0.2113,
 "median_resolution_hours":26.8},...]}
```

`GET /api/timeseries/` возвращает число обращений по дням: всего и отдельно по каждой категории.

```
curl -H "Authorization: Token $TOKEN" "http://127.0.0.1:8000/api/timeseries/?date_from=2026-10-01&date_to=2026-10-03"
{"period":{...},"days":["2026-10-01","2026-10-02","2026-10-03"],"total":[40,42,26],
 "series":[{"name":"Доставка","slug":"delivery","values":[13,11,10]},...]}
```

`GET /api/compare/` сравнивает два периода. Параметры те же, что на странице «Сравнение»:
- `preset=week` или `month` берёт последние 7 или 30 дней против стольких же дней перед ними;
- `preset=custom` требует все четыре даты: `base_from`, `base_to`, `current_from`, `current_to`;
- `by=category` (по умолчанию) или `by=reason` задаёт, по чему сравнивать;
- `category` и `channel` работают как фильтры.

Периоды могут быть разной длины, поэтому изменение `change` считается по числу обращений в день.

```
curl -H "Authorization: Token $TOKEN" "http://127.0.0.1:8000/api/compare/?preset=custom&base_from=2026-08-01&base_to=2026-08-14&current_from=2026-09-01&current_to=2026-09-28&by=reason"
{"base_period":{"date_from":"2026-08-01","date_to":"2026-08-14","days":14},
 "current_period":{"date_from":"2026-09-01","date_to":"2026-09-28","days":28},
 "totals":{"base_count":514,"current_count":1088,"base_per_day":36.71,"current_per_day":38.86,"change":0.0584},
 "results":[{"name":"Задержка доставки","category":"Доставка","base_count":44,"current_count":116,"base_per_day":3.14,
 "current_per_day":4.14,"expected":88.0,"change":0.3182,"notable":true},...]}
```

`GET /api/alerts/` возвращает уведомления о резком росте. Параметры:
- `unread=1` оставляет только непрочитанные этим пользователем;
- `date_from` и `date_to` ограничивают день всплеска.

Ответ разбит на страницы, как список обращений.

```
curl -H "Authorization: Token $TOKEN" "http://127.0.0.1:8000/api/alerts/?unread=1"
{"count":23,"next":"...?page=2&unread=1","previous":null,
 "results":[{"id":39,"day":"2026-10-07","category":"payment","category_name":"Оплата","reason":null,
 "count":11,"baseline":2.9,"ratio":3.79,"read":false,"updated_at":"..."}]}
```

## Обращения

`GET /api/appeals/` возвращает список обращений. Фильтры те же, что на странице «Обращения»:

| Параметр | Значение |
|---|---|
| `q` | поиск по тексту, `#123` ищет по номеру, строка с `@` ищет по email |
| `date_from`, `date_to` | период |
| `category` | slug категории или `none` |
| `reason` | номер причины |
| `tags` | номер тега, параметр можно повторить |
| `channel` | канал |
| `status` | `new`, `in_work`, `resolved`, `closed` или `open` (новые и в работе) |
| `source` | `auto`, `manual`, `none` |
| `assignee` | номер пользователя или `none` |
| `order` | `new` (по умолчанию) или `old` |
| `page`, `page_size` | по 50 на странице, не больше 500 |

```
curl -H "Authorization: Token $TOKEN" "http://127.0.0.1:8000/api/appeals/?category=payment&status=open&page_size=1"
{"count":37,"next":"...","previous":null,"results":[{"id":5994,"created_at":"2026-10-09T21:02:57+03:00",
 "channel":"app","author_name":"А*** К***","author_email":"a***@bk.ru","subject":"",
 "text":"сняли деньги за чайник, но зака не появился в истории","status":"new",
 "category":{"id":1,"slug":"payment","name":"Оплата"},"reason":{"id":3,"name":"Деньги списаны, заказ не оформлен"},
 "category_source":"auto","category_score":4.0,"tags":["Android","Срочно"],"assignee":null,"resolved_at":null,
 "updated_at":"..."}]}
```

Аналитику имя и email автора приходят замаскированными, как в карточке на сайте. Оператор и администратор видят их полностью.

`GET /api/appeals/<номер>/` возвращает одно обращение в том же виде.

`POST /api/appeals/` создаёт обращение. Обязательно только поле `text`. Остальные поля необязательные:
- `channel` (по умолчанию `web`);
- `author_name`;
- `author_email`;
- `subject`;
- `tags` со списком названий тегов.

Категория и причина определяются по словарю при сохранении, так же как у обращения из формы на сайте. После сохранения запускается проверка на резкий рост. Новые уведомления возвращаются в поле `new_alerts`, а аналитикам уходит письмо.

Создавать обращения может оператор или администратор, поэтому здесь нужен токен учётки operator:

```
curl -X POST -d "username=operator&password=demo12345" http://127.0.0.1:8000/api/auth/token/
export OPERATOR_TOKEN=<токен из ответа>
curl -X POST -H "Authorization: Token $OPERATOR_TOKEN" -H "Content-Type: application/json" \
  -d '{"channel":"app","text":"Приложение вылетает при оплате","tags":["iOS"]}' \
  http://127.0.0.1:8000/api/appeals/
{"id":6002,"created_at":"2026-10-10T14:48:24+03:00","channel":"app",...,
 "category":{"id":5,"slug":"app","name":"Приложение и сайт"},"reason":{"id":19,"name":"Приложение вылетает"},
 "category_source":"auto","category_score":3.0,"tags":["iOS"],...,"new_alerts":[]}
```

Ошибки в полях возвращаются с кодом 400:

```
{"channel":["Значения fax нет среди допустимых вариантов."],"text":["Это поле не может быть пустым."],
 "tags":["Объект с name=нет такого не существует."]}
```
