"""Читает события Kafka и отправляет уведомления в Telegram."""
import json
import logging
import os
import signal
import sys
import time
from urllib import error, parse, request

from confluent_kafka import Consumer, KafkaException
import psycopg
import database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("notification")
running = True


def stop(_signum, _frame):
    global running
    running = False


def send_telegram(token, chat_id, event):
    quote = event.get("quote")
    if isinstance(quote, dict) and isinstance(quote.get("text"), str) and isinstance(quote.get("character"), str):
        text = f"{quote['text']}\n\n— {quote['character']}"
    else:
        # События, записанные до обновления приложения, не содержат цитату.
        text = "Нажата кнопка получения цитаты Смешариков."
    body = parse.urlencode({"chat_id": chat_id, "text": text[:4096]}).encode()
    req = request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    try:
        with request.urlopen(req, timeout=10) as response:
            result = json.load(response)
            return response.status == 200 and result.get("ok") is True
    except error.HTTPError as exc:
        if exc.code in (400, 403):
            logger.warning("Telegram не может доставить сообщение в этот чат; событие пропущено")
            return "undeliverable"
        logger.warning("Telegram временно не принял уведомление; повторим попытку")
        return False
    except (error.URLError, TimeoutError, OSError, ValueError):
        # Не выводим исключение: URL может содержать секретный токен.
        logger.warning("Telegram не принял уведомление; повторим попытку")
        return False


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("Укажи TELEGRAM_BOT_TOKEN в .env; уведомления пока не отправляются")
        return 1

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    consumer = Consumer({
        "bootstrap.servers": os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        "group.id": "telegram-notifications",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "isolation.level": "read_committed",
    })
    consumer.subscribe(["quote-clicks"])
    logger.info("Ожидаем события в Kafka")
    try:
        while running:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                logger.warning("Ошибка Kafka: %s", message.error())
                continue
            try:
                event = json.loads(message.value())
                if not isinstance(event, dict) or event.get("type") != "quote_button_clicked":
                    raise ValueError("unknown event")
            except (ValueError, UnicodeDecodeError, TypeError):
                logger.warning("Некорректное событие пропущено")
                consumer.commit(message=message, asynchronous=False)
                continue
            session_hash = event.get("session_hash")
            if not isinstance(session_hash, str) or len(session_hash) != 64:
                logger.info("Браузер не привязан к Telegram; уведомление не требуется")
                consumer.commit(message=message, asynchronous=False)
                continue
            while running:
                try:
                    with database.connect(connect_timeout=5) as connection:
                        row = connection.execute("SELECT chat_id FROM telegram_sessions WHERE session_hash = %s", (session_hash,)).fetchone()
                    break
                except (psycopg.Error, OSError, ValueError):
                    logger.warning("База недоступна; повторим проверку привязки")
                    time.sleep(5)
            if not running:
                break
            if not row or not row[0]:
                logger.info("Привязка отсутствует или удалена; событие пропущено")
                consumer.commit(message=message, asynchronous=False)
                continue
            chat_id = str(row[0])
            result = False
            while running and not result:
                result = send_telegram(token, chat_id, event)
                if not result:
                    time.sleep(5)
            if running:
                consumer.commit(message=message, asynchronous=False)
                if result == "undeliverable":
                    logger.info("Недоставленное событие %s подтверждено", event.get("event_id"))
                else:
                    logger.info("Уведомление отправлено, событие %s подтверждено", event.get("event_id"))
    except KafkaException:
        logger.exception("Ошибка чтения Kafka")
        return 1
    finally:
        consumer.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
