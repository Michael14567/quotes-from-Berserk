"""Проверяет изоляцию задач и Telegram на настоящем PostgreSQL.

TEST_DATABASE_DSN указывает только на тестовую базу; каждый тест получает
отдельную схему, которая удаляется после проверки.
"""
import importlib.util
import os
from pathlib import Path
import sys
import time
from unittest.mock import Mock
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


@pytest.fixture
def task_db(monkeypatch):
    dsn = os.environ.get("TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("Для интеграционных тестов требуется TEST_DATABASE_DSN")
    for attempt in range(30):
        try:
            admin = psycopg.connect(dsn, autocommit=True)
            break
        except psycopg.OperationalError:
            if attempt == 29:
                raise
            time.sleep(1)
    schema = "tasks_test_" + uuid4().hex
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    def connect(**kwargs):
        return psycopg.connect(dsn, options=f"-c search_path={schema}", **kwargs)

    try:
        with connect() as conn:
            conn.execute((Path(__file__).resolve().parents[3] / "telegram.sql").read_text(encoding="utf-8"))
        monkeypatch.setattr(app.database, "connect", connect)
        yield connect
    finally:
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


def browser(task_db, token, chat_id):
    with task_db() as conn:
        conn.execute("INSERT INTO telegram_sessions (session_hash, chat_id) VALUES (%s, %s)",
                     (app.token_hash(token), chat_id))
    client = TestClient(app.app)
    client.cookies.set("quotes_session", token)
    return client


def bot_module(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "notification" / "bot_listener.py"
    spec = importlib.util.spec_from_file_location("tasks_test_bot", path)
    bot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot)
    monkeypatch.setattr(bot, "telegram_api", Mock(return_value=True))
    return bot


def test_tasks_require_a_linked_browser(task_db):
    client = TestClient(app.app)
    assert client.get("/tasks").status_code == 401
    assert client.post("/tasks", json={"title": "SQL"}).status_code == 401


def test_tasks_are_shared_by_chat_and_isolated_from_other_users(task_db):
    first = browser(task_db, "a" * 43, 101)
    same_user = browser(task_db, "b" * 43, 101)
    stranger = browser(task_db, "c" * 43, 202)
    result = first.post("/tasks", json={"title": "  Повторить SQL  ", "chat_id": 202})
    assert result.status_code == 201
    task = result.json()
    assert task["title"] == "Повторить SQL"
    assert same_user.get("/tasks").json()["tasks"] == [task]
    assert stranger.get("/tasks").json()["tasks"] == []
    assert stranger.patch(f"/tasks/{task['id']}", json={"done": True}).status_code == 404
    assert stranger.delete(f"/tasks/{task['id']}").status_code == 404
    assert same_user.patch(f"/tasks/{task['id']}", json={"done": True}).json()["done"] is True
    assert first.get("/tasks").json()["tasks"][0]["done"] is True
    assert first.delete(f"/tasks/{task['id']}").status_code == 204
    assert same_user.get("/tasks").json()["tasks"] == []


def test_empty_titles_and_previous_days(task_db):
    client = browser(task_db, "a" * 43, 101)
    assert client.post("/tasks", json={"title": "   "}).status_code == 422
    assert client.post("/tasks", json={"title": "a" * 201}).status_code == 422
    task = client.post("/tasks", json={"title": "Вчерашняя"}).json()
    with task_db() as conn:
        conn.execute("UPDATE daily_tasks SET task_date = task_date - 1 WHERE id = %s", (task["id"],))
    assert client.get("/tasks").json()["tasks"] == []
    assert client.patch(f"/tasks/{task['id']}", json={"done": True}).status_code == 404


def test_bot_add_and_buttons_use_the_same_tasks_and_check_owner(task_db, monkeypatch):
    client = browser(task_db, "a" * 43, 101)
    bot = bot_module(monkeypatch)
    update = {"update_id": 100, "message": {"chat": {"id": 101, "type": "private"}, "text": "/add Проверить логи"}}
    with task_db() as conn:
        bot.process_update(conn, update)
        bot.process_update(conn, update)  # повторное обновление не создаёт копию
    tasks = client.get("/tasks").json()["tasks"]
    assert len(tasks) == 1 and tasks[0]["title"] == "Проверить логи"
    task_id = tasks[0]["id"]
    assert bot.telegram_api.call_args.args[1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"task:{task_id}:1"

    def click(update_id, chat_id):
        return {"update_id": update_id, "callback_query": {"id": "test-callback", "from": {"id": chat_id},
                "message": {"message_id": 7, "chat": {"id": chat_id, "type": "private"}}, "data": f"task:{task_id}:1"}}

    with task_db() as conn:
        bot.process_update(conn, click(101, 202))  # пользователь подделал ID чужой задачи
    assert client.get("/tasks").json()["tasks"][0]["done"] is False
    with task_db() as conn:
        bot.process_update(conn, click(102, 101))
    assert client.get("/tasks").json()["tasks"][0]["done"] is True


def test_bot_ignores_group_commands(task_db, monkeypatch):
    bot = bot_module(monkeypatch)
    with task_db() as conn:
        bot.process_update(conn, {"update_id": 100, "message": {"chat": {"id": -1, "type": "group"}, "text": "/add Чужая задача"}})
        assert conn.execute("SELECT count(*) FROM daily_tasks").fetchone()[0] == 0
    bot.telegram_api.assert_not_called()
