from unittest.mock import Mock
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database


def test_password_is_read_from_secret_file(tmp_path, monkeypatch):
    path = tmp_path / "password"
    path.write_text("test-password\n", encoding="utf-8")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(path))
    connect = Mock()
    monkeypatch.setattr(database.psycopg, "connect", connect)
    database.connect(connect_timeout=3)
    assert connect.call_args.kwargs["password"] == "test-password"
    assert connect.call_args.kwargs["host"] == "db"
    assert connect.call_args.kwargs["port"] == 5432


def test_tunnel_uses_configured_database_port(tmp_path, monkeypatch):
    path = tmp_path / "password"
    path.write_text("test-password", encoding="utf-8")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(path))
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "15432")
    connect = Mock()
    monkeypatch.setattr(database.psycopg, "connect", connect)
    database.connect()
    assert connect.call_args.kwargs["host"] == "127.0.0.1"
    assert connect.call_args.kwargs["port"] == 15432


def test_empty_password_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "password"
    path.write_text("\n", encoding="utf-8")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(path))
    with pytest.raises(ValueError):
        database.connect()
