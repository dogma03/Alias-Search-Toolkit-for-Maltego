# Alias Search Toolkit for Maltego / Alias Search Toolkit для Maltego

[English](#english) | [Русская версия](#русская-версия)

## English

A local Maltego Transform server that searches public profiles by username
(alias) through **Sherlock** and **Maigret**, merges and deduplicates results,
and returns a summary `Phrase` plus `URL` entities for the graph.

It runs separately from the photo/file metadata server:

- Photo Metadata Toolkit — `https://127.0.0.1:3000/seed`
- Alias Search Toolkit — `https://127.0.0.1:3001/seed`

### Transform

```text
Search alias (Sherlock + Maigret) [OSINT]
```

The transform:

- runs both search engines;
- merges profiles and removes duplicate URLs, including `www.` variants;
- creates one `URL` entity per unique profile;
- creates a `Phrase` with per-engine counts, timings, and errors;
- copies Maigret metadata (`fullname`, `location`, `company`, `bio`,
  `created_at`, `follower_count`, etc.) into the URL note and properties;
- stores raw Sherlock CSV / Maigret JSON in the `raw_results` property.

It deliberately does **not** create `Person` entities: a matching profile is
an OSINT candidate, not proof of identity.

### Requirements

- Python 3.11+ (tested on Python 3.14)
- Maltego Graph Desktop
- Sherlock
- Maigret

Example installation:

```bash
pipx install maigret
# Install Sherlock from https://github.com/sherlock-project/sherlock
# Then set SHERLOCK_BIN if it is not on PATH.
```

The transform server calls both tools as external CLI processes; it does not
import them as Python libraries.

### Install and run

```bash
cd ~/"папка с трансформами/second transform"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python project.py
```

The server listens on:

```text
https://127.0.0.1:3001/seed
```

Import this seed URL in **Maltego Data Hub** and trust `certs/cert.pem`. The
transform set is **OSINT Toolkit**.

The `certs/` directory is intentionally excluded from git. If it is absent,
create a local self-signed certificate:

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/key.pem -out certs/cert.pem -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

### Usage

1. Add an **Alias** entity to the graph.
2. Set its `alias` property, for example `torvalds` or `@torvalds`.
3. Run **OSINT Toolkit → Search alias (Sherlock + Maigret) [OSINT]**.

The graph receives a summary `Phrase` and one `URL` per unique profile. Verify
matches manually before drawing conclusions.

### Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `ALIAS_ENGINES` | `sherlock,maigret` | Engines to run: `sherlock`, `maigret`, or both |
| `SHERLOCK_BIN` | auto-detected | Path to the Sherlock executable |
| `MAIGRET_BIN` | auto-detected | Path to the Maigret executable |
| `SHERLOCK_SITES` | all sites | Comma-separated Sherlock site names |
| `MAIGRET_SITES` | empty | Comma-separated Maigret site names |
| `MAIGRET_TOP_SITES` | `100` | Number of top Maigret sites to check |
| `ALIAS_MAX_PROFILES` | `150` | Maximum number of URL entities in the graph |
| `ALIAS_PORT` | `3001` | Server port |

Quick mode with Sherlock only:

```bash
ALIAS_ENGINES=sherlock SHERLOCK_SITES=GitHub python project.py
```

The same code can be tested without Maltego:

```bash
.venv/bin/python scripts/search_alias.py torvalds
```

### Limitations

- A found profile does not prove that it belongs to a specific person.
- Sites may block automated requests, return false positives, or change their
  markup; the absence of a result does not prove that an account does not exist.
- The server does not bypass CAPTCHAs and does not use proxies by default.
- Respect site terms of service, privacy laws, and rate limits.
- The server binds to localhost and uses a self-signed certificate.

Full Russian documentation follows below.

## Русская версия

Второй локальный transform-сервер: ищет профили по нику (alias) через
**Sherlock** и **Maigret**, объединяет результаты и возвращает в граф ссылки на
найденные профили.

Сервер работает отдельно от `exifdata transform`:

- `exifdata transform` — метаданные фото и файлов, порт `3000`;
- `second transform` — поиск по алиасам, порт `3001`.

## Что делает трансформ

Один трансформ:

```text
Search alias (Sherlock + Maigret) [OSINT]
```

Он запускает оба инструмента, ждёт результаты и:

- объединяет профили;
- убирает дубликаты по URL (в том числе `www.`-варианты);
- создаёт отдельную `URL`-сущность для каждого профиля;
- создаёт `Phrase` со сводкой, счётчиками и ошибками;
- складывает метаданные Maigret (`fullname`, `location`, `company`, `bio`,
  `created_at`, `follower_count` и т. п.) в note и свойства `URL`;
- сохраняет сырой CSV/JSON в свойство `raw_results` итоговой `Phrase`.

Трансформ **не создаёт `Person`**: найденный профиль ещё не доказывает, что он
принадлежит конкретному человеку. Проверяйте совпадения вручную.

## Требования

- Python 3.11+ (проверено на Python 3.14);
- Maltego Graph Desktop;
- установленный Sherlock;
- установленный Maigret.

В текущем окружении уже установлены:

```text
Sherlock: /home/homosapiens/Tools/Sherlock/.venv/bin/sherlock
Maigret:  /home/homosapiens/.local/bin/maigret
```

Проверка:

```bash
~/Tools/Sherlock/.venv/bin/sherlock --version
maigret --version
```

Трансформ-сервер не импортирует Sherlock или Maigret как Python-библиотеки:
он запускает их как внешние CLI-процессы. Поэтому конфликты зависимостей
исключены.

## Установка

```bash
cd ~/"папка с трансформами/second transform"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Виртуальное окружение уже создано в этой папке. Если оно есть, повторно
создавать его не нужно: достаточно `pip install -r requirements.txt`, когда
меняются зависимости.

## Запуск сервера

```bash
cd ~/"папка с трансформами/second transform"
source .venv/bin/activate
python project.py
```

В логе должна появиться строка:

```text
Seed Endpoint: https://127.0.0.1:3001/seed
```

Сервер слушает только localhost. Не закрывайте терминал, пока работаете с
трансформом.

Проверка без Maltego:

```bash
curl --cacert certs/cert.pem https://127.0.0.1:3001/seed
curl --cacert certs/cert.pem https://127.0.0.1:3001/transforms
```

Второй запрос должен показать трансформ и выходные типы
`maltego.Phrase` и `maltego.URL`.

## HTTPS и сертификат

Maltego 4.x не принимает обычный HTTP для transform-серверов. Проект использует
HTTPS на `127.0.0.1:3001`.

Сертификат скопирован из `exifdata transform/certs/`:

```text
second transform/certs/cert.pem
second transform/certs/key.pem
```

Это тот же локальный сертификат `CN=localhost` с SAN
`DNS:localhost, IP:127.0.0.1`. Если вы уже импортировали сертификат exif-сервера
в Maltego, отдельно импортировать его снова не нужно.

Если сертификат ещё не доверен:

1. Откройте Maltego.
2. Перейдите во вкладку **Transforms** → **Manage Certificates**.
3. Нажмите **Import Certificates**.
4. Выберите:

   ```text
   ~/папка с трансформами/second transform/certs/cert.pem
   ```

5. Отметьте сертификат как **Trusted**.
6. Перезапустите Maltego или повторите discovery.

Проверка сертификата:

```bash
openssl x509 -in certs/cert.pem -noout -subject -dates -fingerprint -sha256
```

Если Maltego при первом подключении показывает окно `Trust` / `Don't Trust`,
можно выбрать `Trust`.

## Импорт в Maltego Desktop

1. Запустите сервер и оставьте его работать.
2. Убедитесь, что сертификат доверен (см. раздел выше).
3. Откройте Maltego Graph Desktop.
4. Перейдите на вкладку **Transforms** → **Maltego Data Hub**.
5. Прокрутите до **INTERNAL HUB ITEMS**.
6. Нажмите **+** (Add Transform Seed).
7. Заполните:

   - **ID** — например, `alias-search-local`;
   - **Name** — `Alias Search Toolkit`;
   - **Seed URL** — `https://127.0.0.1:3001/seed`.

8. Нажмите **OK**.
9. В карточке seed нажмите **INSTALL** и дождитесь discovery.
10. В **Transform Manager** появится набор **OSINT Toolkit** с трансформом
    `Search alias (Sherlock + Maigret) [OSINT]`.

Если ранее был добавлен seed с `http://127.0.0.1:3001/seed`, замените его на
HTTPS: Maltego выдаст ошибку `Only HTTPS (SSL/TLS) Transform Servers are allowed`.

## Как искать

1. Добавьте в граф сущность **Alias**.
2. В свойстве `alias` укажите ник:

   ```text
   torvalds
   ```

   Можно использовать и `@torvalds` — ведущая `@` будет удалена.

3. Правый клик по сущности → **Run Transform** → **OSINT Toolkit** →
   **Search alias (Sherlock + Maigret) [OSINT]**.
4. Дождитесь завершения. В графе появятся:

   - `Phrase` — сводка: сколько профилей нашёл каждый движок, время, ошибки;
   - `URL` — по одной сущности на каждый уникальный профиль.

В note у `URL` указаны сайт, источник (Sherlock/Maigret), HTTP-статус и
метаданные. В свойствах доступны `title`, `short-title`, `sources`, `alias`,
`http_status`, `fullname`, `location`, `company`, `profile_metadata` и др.

## Настройка через переменные окружения

Настройки читаются при запуске сервера и при выполнении трансформа.

| Переменная | По умолчанию | Назначение |
|---|---:|---|
| `ALIAS_ENGINES` | `sherlock,maigret` | Какие движки запускать. Можно `sherlock` или `maigret`. |
| `SHERLOCK_BIN` | автоопределение | Полный путь к `sherlock`. |
| `MAIGRET_BIN` | автоопределение | Полный путь к `maigret`. |
| `SHERLOCK_SITES` | пусто = все сайты | Список сайтов Sherlock через запятую, например `GitHub,Reddit`. |
| `MAIGRET_SITES` | пусто | Список сайтов Maigret через запятую. Если задан, `--top-sites` не используется. |
| `MAIGRET_TOP_SITES` | `100` | Сколько топ-сайтов проверять в Maigret. |
| `MAIGRET_MAX_CONNECTIONS` | `20` | Параллельные соединения Maigret. |
| `SHERLOCK_REQUEST_TIMEOUT` | `15` | Таймаут одного запроса Sherlock, сек. |
| `SHERLOCK_TIMEOUT` | `150` | Общий лимит Sherlock, сек. |
| `MAIGRET_REQUEST_TIMEOUT` | `10` | Таймаут одного запроса Maigret, сек. |
| `MAIGRET_TIMEOUT` | `240` | Общий лимит Maigret, сек. |
| `ALIAS_MAX_PROFILES` | `150` | Максимум `URL`-сущностей в графе. |
| `ALIAS_TRANSFORM_TIMEOUT` | `300` | Общий лимит выполнения трансформа, сек. |
| `ALIAS_PORT` | `3001` | Порт сервера. |
| `ALIAS_HOST` | `127.0.0.1` | Адрес сервера. |
| `ALIAS_PROTOCOL` | `https` | Протокол сервера. Для Maltego нужен HTTPS. |
| `MAIGRET_ENRICH` | выкл. | `1` добавляет `--enrich` для Maigret. |

### Быстрый режим

Только Sherlock и только GitHub:

```bash
cd ~/"папка с трансформами/second transform"
ALIAS_ENGINES=sherlock SHERLOCK_SITES=GitHub .venv/bin/python project.py
```

### Полный режим

Оба движка, все сайты Sherlock и топ-100 Maigret:

```bash
cd ~/"папка с трансформами/second transform"
.venv/bin/python project.py
```

Это может занять несколько минут: Sherlock проверяет много сайтов, а Maigret
ходит по топ-100. Для ускорения ограничьте списки сайтов.

### Ограничение конкретными сайтами

```bash
ALIAS_ENGINES=sherlock,maigret \
SHERLOCK_SITES=GitHub,Reddit,Instagram \
MAIGRET_SITES=GitHub,Reddit,Instagram \
.venv/bin/python project.py
```

Названия сайтов должны совпадать с названиями в базах Sherlock/Maigret.
Например, для Sherlock это `GitHub`, `Reddit`, `Instagram`; для Maigret —
`GitHub`, `Reddit`, `Instagram`.

## Проверка без Maltego

CLI-скрипт использует тот же код, что и трансформ:

```bash
cd ~/"папка с трансформами/second transform"
.venv/bin/python scripts/search_alias.py torvalds
```

Только Sherlock:

```bash
ALIAS_ENGINES=sherlock SHERLOCK_SITES=GitHub \
.venv/bin/python scripts/search_alias.py torvalds --engines sherlock
```

Только Maigret:

```bash
ALIAS_ENGINES=maigret MAIGRET_SITES=GitHub \
.venv/bin/python scripts/search_alias.py torvalds --engines maigret
```

Показать сырые CSV/JSON:

```bash
.venv/bin/python scripts/search_alias.py torvalds --raw
```

## Ограничения и важные предупреждения

- Sherlock и Maigret проверяют **наличие публичного профиля**, а не
  принадлежность профиля человеку. Одинаковый ник у разных людей — обычная
  ситуация.
- Возможны ложные срабатывания: сайт может отдавать `200` на заглушку или
  страницу входа. В note есть `alias_in_url` и `http_status`, но итоговую
  проверку всё равно нужно делать вручную.
- Сайты могут блокировать автоматические запросы, требовать captcha или
  менять разметку. В таком случае движок вернёт ошибку или меньше результатов;
  это не означает, что профиля нет.
- Maigret по умолчанию работает без рекурсии (`--no-recursion`) и без
  автоматического обновления базы (`--no-autoupdate`). Это сделано для
  предсказуемости и скорости.
- Трансформ не обходит CAPTCHA и не использует прокси. Прокси можно добавить
  позже через переменные окружения, если понадобится.
- Не запускайте массовые проверки чужих ников без необходимости и соблюдайте
  условия использования сайтов и законодательство.
- Сервер по умолчанию доступен только с `127.0.0.1`. Не открывайте порт в
  интернет без аутентификации и нормального TLS-сертификата.

## Если что-то не работает

### Трансформ не появился в Maltego

- Проверьте, что сервер запущен:

  ```bash
  curl --cacert certs/cert.pem https://127.0.0.1:3001/seed
  ```

- Убедитесь, что в Data Hub добавлен именно seed URL
  `https://127.0.0.1:3001/seed`, а не `/transforms`.
- Проверьте, что сертификат `certs/cert.pem` импортирован в Maltego и отмечен
  как **Trusted**.
- Посмотрите лог сервера: там будет ошибка discovery или TLS.

### `Only HTTPS (SSL/TLS) Transform Servers are allowed`

Используйте `https://127.0.0.1:3001/seed`. HTTP Maltego не принимает.

### `Не найден SHERLOCK_BIN` или `Не найден MAIGRET_BIN`

Задайте путь явно:

```bash
SHERLOCK_BIN=/home/homosapiens/Tools/Sherlock/.venv/bin/sherlock \
MAIGRET_BIN=/home/homosapiens/.local/bin/maigret \
.venv/bin/python project.py
```

### Поиск идёт слишком долго

Ограничьте сайты и/или отключите Maigret:

```bash
ALIAS_ENGINES=sherlock SHERLOCK_SITES=GitHub,Reddit \
.venv/bin/python project.py
```

Или уменьшите `MAIGRET_TOP_SITES`:

```bash
MAIGRET_TOP_SITES=30 .venv/bin/python project.py
```

### `AuthlibDeprecationWarning: authlib.jose module is deprecated`

Это предупреждение библиотеки `authlib`, а не ошибка трансформа. Оно не мешает
работе и появляется при импорте Maltego SDK.

## Структура проекта

```text
second transform/
├── project.py                  # настройки и запуск HTTPS-сервера
├── requirements.txt
├── certs/
│   ├── cert.pem                # локальный сертификат
│   └── key.pem
├── transforms/
│   ├── __init__.py             # регистрация трансформа
│   ├── alias_core.py           # запуск Sherlock/Maigret и парсинг
│   └── alias_search.py         # Maltego-сущности и @register_transform
└── scripts/
    └── search_alias.py         # проверка без Maltego
```
