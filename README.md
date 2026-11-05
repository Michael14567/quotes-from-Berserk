# Цитатник Смешариков

Небольшой сервис, который показывает случайную цитату и отправляет уведомление в Telegram. Уведомления получает пользователь, привязавший свой браузер к боту через QR-код.

Проект использует FastAPI, PostgreSQL, Nginx и Redpanda (брокер с поддержкой Kafka API). Все компоненты запускаются через Docker Compose.

```text
Браузер → Nginx → FastAPI → PostgreSQL
                      ↓
                Redpanda / Kafka → сервис уведомлений → Telegram
```

Для привязки браузера отдельный процесс получает команды `/start` от Telegram. Три брокера Redpanda хранят по реплике топика `quote-clicks`.

## Запуск

Установите и запустите Docker Desktop. В PowerShell из корня репозитория:

```powershell
cd berserk-quotes
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

Откройте [localhost:8088](http://localhost:8088). Кнопка показывает случайную цитату. Сервис цитат работает без настроек Telegram.

## Уведомления в Telegram

Создайте бота через [BotFather](https://t.me/BotFather) и укажите его токен и имя в `berserk-quotes/.env`:

```env
TELEGRAM_BOT_TOKEN=токен_бота
TELEGRAM_BOT_USERNAME=имя_бота_без_собаки
SESSION_COOKIE_SECURE=false
```

Файл `.env` хранится локально и исключён из Git. После изменения настроек пересоздайте сервисы:

```powershell
docker compose up -d --build
```

На сайте нажмите «Привязать Telegram», отсканируйте QR-код и нажмите Start в боте. Можно также открыть бота по ссылке под кодом. Код действует пять минут и подходит для одной привязки. Не передавайте его другим людям. При смене браузера или очистке cookie привязку нужно повторить. Кнопка «Отвязать Telegram» удаляет связь.

Получение обновлений через `getUpdates` должно быть запущено только в одном экземпляре бота. Не включайте `telegram-bot` одновременно в Compose и Minikube с одним токеном.

На существующей базе после обновления проекта примените миграцию:

```powershell
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U quotes -d quotes -f /docker-entrypoint-initdb.d/03-telegram.sql
```

## API и диагностика

Swagger доступен на [localhost:8000/docs](http://localhost:8000/docs). Основные маршруты:

- `GET /smeshariki-quotes` — цитаты; параметр `character` фильтрует их по персонажу.
- `POST /quote-click` — событие нажатия кнопки.
- `POST /telegram/link`, `GET /telegram/status`, `DELETE /telegram/link` — привязка и отвязка Telegram.

Nginx направляет запросы с префиксом `/api/` в FastAPI. Посмотреть логи и состояние брокеров:

```powershell
docker compose logs --tail 50 app notification telegram-bot
docker compose exec kafka rpk cluster info -X brokers=kafka:9092
docker compose exec kafka rpk topic describe quote-clicks -p -X brokers=kafka:9092
```

События Kafka отправляются в транзакции с `enable.idempotence` и `acks=all`. Consumer читает подтверждённые транзакции. При сбое после принятия сообщения Telegram и до сохранения позиции Kafka уведомление может прийти повторно; транзакция Kafka не охватывает Telegram API.

Данные PostgreSQL и брокеров сохраняются в Docker volumes. `docker compose down` останавливает сервисы без удаления данных; `docker compose down -v` удаляет также volumes. SQL-файлы инициализации применяются при создании пустой базы. Пароль базы в конфигурации учебный. Для публичного сервера нужны HTTPS, отдельные секреты и резервные копии; после настройки HTTPS установите `SESSION_COOKIE_SECURE=true`.

## Тесты и развёртывание

```powershell
python -m pip install -r berserk-quotes/requirements-test.txt
python -m pytest -q berserk-quotes/tests
```

Инструкции по GitLab CI, Ansible и Minikube находятся в [deploy/README.md](deploy/README.md). GitLab pipeline и развёртывание на удалённом сервере требуют отдельной настройки runner, Registry и SSH-доступа.

`smeshariki_to_sql.py` собирает записи из Викицитатника в `smeshariki_quotes.sql`. Перед публикацией цитат проверьте их достоверность и права на использование.
