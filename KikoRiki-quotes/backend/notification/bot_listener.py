"""Привязывает браузер и управляет личными задачами через Telegram."""
import hashlib
import json
import logging
import os
import re
import time
from urllib import error, parse, request

import psycopg
import database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram-bot")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
START = re.compile(r"^/start(?:@\w+)? ([A-Za-z0-9_-]{32})$")
TASK_ACTION = re.compile(r"^task:([0-9]{1,18}):([01])$")
COMMAND = re.compile(r"^/(tasks|add|start|help)(?:@\w+)?(?:\s+([\s\S]*))?$")
HELP = "Задачи на сегодня (по Москве):\n/tasks — показать список\n/add Название задачи — добавить\nОтмечайте готовые задачи кнопками под списком.\nНа сайте dnec4.ru доступен тот же список после привязки Telegram."


def telegram_api(method, payload):
    """POST без вывода URL, текста задач или ID чата в логи."""
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=10) as response:
            return json.load(response).get("ok") is True
    except (error.URLError, TimeoutError, OSError, ValueError):
        log.warning("Не удалось отправить ответ Telegram")
        return False


def task_message(cursor, chat_id):
    cursor.execute(
        """SELECT id, title, done FROM daily_tasks WHERE chat_id = %s
           AND task_date = (now() AT TIME ZONE 'Europe/Moscow')::date ORDER BY id LIMIT 11""",
        (chat_id,),
    )
    rows = cursor.fetchall()
    lines = ["Задачи на сегодня · Москва"]
    buttons = []
    for index, (task_id, title, done) in enumerate(rows[:10], 1):
        lines.append(f"{'✅' if done else '⬜'} {index}. {title}")
        buttons.append([{"text": f"{'Вернуть в работу' if done else 'Готово'} · {index}",
                         "callback_data": f"task:{task_id}:{0 if done else 1}"}])
    if not rows:
        lines.append("Пока пусто. Добавьте задачу: /add Повторить SQL")
    if len(rows) > 10:
        lines.append("Первые 10 задач. Полный список — на сайте dnec4.ru.")
    return {"text": "\n\n".join(lines), "reply_markup": {"inline_keyboard": buttons}}


def process_update(connection, update):
    update_id = update["update_id"]
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    match = START.fullmatch(message.get("text", "")) if chat.get("type") == "private" else None
    outgoing = []
    with connection.cursor() as cursor:
        cursor.execute("SELECT next_update_id FROM telegram_bot_state WHERE name = 'poller'")
        previous = cursor.fetchone()
        if previous and update_id < previous[0]:
            connection.commit()
            return
        if match and isinstance(chat.get("id"), int):
            digest = hashlib.sha256(match.group(1).encode()).hexdigest()
            cursor.execute(
                """UPDATE telegram_sessions SET chat_id = %s, link_hash = NULL, link_expires_at = NULL
                   WHERE link_hash = %s AND link_expires_at > now() RETURNING session_hash""",
                (chat["id"], digest),
            )
            if cursor.fetchone():
                log.info("Telegram успешно привязан к браузеру")
                text = "Telegram привязан! Теперь задачи доступны и на сайте, и здесь.\n\n" + HELP
            else:
                text = "Код привязки истёк или уже использован. Получите новый код на сайте.\n\n" + HELP
            outgoing.append(("sendMessage", {"chat_id": chat["id"], "text": text}))
        elif chat.get("type") == "private" and isinstance(chat.get("id"), int):
            command = COMMAND.fullmatch(message.get("text", ""))
            if command:
                name, title = command.groups()
                if name == "add":
                    title = (title or "").strip()
                    if 0 < len(title) <= 200:
                        cursor.execute(
                            """INSERT INTO daily_tasks (chat_id, title, telegram_update_id) VALUES (%s, %s, %s)
                               ON CONFLICT (telegram_update_id) DO NOTHING""",
                            (chat["id"], title, update_id),
                        )
                        payload = task_message(cursor, chat["id"])
                    else:
                        payload = {"text": "Напишите /add и название задачи длиной от 1 до 200 символов."}
                elif name == "tasks":
                    payload = task_message(cursor, chat["id"])
                else:
                    payload = {"text": HELP}
                outgoing.append(("sendMessage", {"chat_id": chat["id"], **payload}))

        callback = update.get("callback_query") or {}
        callback_message = callback.get("message") or {}
        callback_chat = callback_message.get("chat") or {}
        callback_owner = (callback.get("from") or {}).get("id")
        action = TASK_ACTION.fullmatch(callback.get("data", ""))
        if callback and action and callback_chat.get("type") == "private" and callback_chat.get("id") == callback_owner and isinstance(callback_owner, int):
            task_id, done = action.groups()
            cursor.execute(
                """UPDATE daily_tasks SET done = %s WHERE id = %s AND chat_id = %s
                   AND task_date = (now() AT TIME ZONE 'Europe/Moscow')::date RETURNING id""",
                (done == "1", int(task_id), callback_owner),
            )
            changed = cursor.fetchone() is not None
            outgoing.append(("answerCallbackQuery", {"callback_query_id": callback["id"],
                             "text": "Сохранено" if changed else "Задача удалена или уже не на сегодня"}))
            outgoing.append(("editMessageText", {"chat_id": callback_owner,
                             "message_id": callback_message["message_id"], **task_message(cursor, callback_owner)}))
        cursor.execute(
            """INSERT INTO telegram_bot_state(name, next_update_id) VALUES ('poller', %s)
               ON CONFLICT(name) DO UPDATE SET next_update_id = GREATEST(telegram_bot_state.next_update_id, EXCLUDED.next_update_id)""",
            (update_id + 1,),
        )
    connection.commit()
    for method, payload in outgoing:
        telegram_api(method, payload)


def main():
    if not TOKEN:
        log.error("Укажи TELEGRAM_BOT_TOKEN в .env")
        return 1
    log.info("Ожидаем команды привязки и задач от Telegram")
    telegram_api("setMyCommands", {"commands": [
        {"command": "tasks", "description": "Мои задачи на сегодня"},
        {"command": "add", "description": "Добавить задачу: /add название"},
        {"command": "help", "description": "Как пользоваться ботом"},
    ]})
    while True:
        try:
            with database.connect(connect_timeout=5) as connection:
                row = connection.execute("SELECT next_update_id FROM telegram_bot_state WHERE name = 'poller'").fetchone()
                offset = row[0] if row else 0
                connection.commit()
                params = parse.urlencode({"offset": offset, "timeout": 20, "allowed_updates": '["message","callback_query"]'})
                with request.urlopen(f"https://api.telegram.org/bot{TOKEN}/getUpdates?{params}", timeout=30) as response:
                    result = json.load(response)
                if not result.get("ok"):
                    raise ValueError("Telegram rejected request")
                for update in result.get("result", []):
                    process_update(connection, update)
        except (error.URLError, TimeoutError, OSError, ValueError, psycopg.Error, KeyError, TypeError):
            # Ошибки HTTP не печатаем: URL содержит токен бота.
            log.warning("Не удалось получить или обработать обновления Telegram; повторяем")
            time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
