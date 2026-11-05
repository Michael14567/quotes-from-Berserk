import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs
from unittest.mock import MagicMock


def test_telegram_message_contains_selected_quote(monkeypatch):
    consumer_path = Path(__file__).resolve().parents[2] / "notification" / "consumer.py"
    spec = importlib.util.spec_from_file_location("notification_consumer", consumer_path)
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    response = MagicMock()
    response.status = 200
    response.read.return_value = json.dumps({"ok": True}).encode()
    opener = MagicMock()
    opener.return_value.__enter__.return_value = response
    monkeypatch.setattr(consumer.request, "urlopen", opener)

    event = {"quote": {"text": "Пример цитаты", "character": "Бараш"}}
    assert consumer.send_telegram("test-token", "123", event) is True
    data = parse_qs(opener.call_args.args[0].data.decode())
    assert data["text"] == ["Пример цитаты\n\n— Бараш"]
