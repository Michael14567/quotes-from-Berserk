import sys
import json
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from confluent_kafka import KafkaError, KafkaException
from fastapi.testclient import TestClient


def test_quotes_filter_uses_parameter(monkeypatch):
    query = Mock(return_value=[{"id": 1, "text": "Пример", "character": "Бараш"}])
    monkeypatch.setattr(app, "fetch_all", query)
    response = TestClient(app.app).get("/smeshariki-quotes", params={"character": "Бараш"})
    assert response.status_code == 200
    assert response.json()[0]["character"] == "Бараш"
    assert query.call_args.args[1] == ("Бараш",)


def test_click_commits_kafka_transaction(monkeypatch):
    producer = Mock()
    monkeypatch.setattr(app, "producer", producer)
    monkeypatch.setattr(app, "producer_initialized", False)
    response = TestClient(app.app).post("/quote-click")
    assert response.status_code == 202
    producer.init_transactions.assert_called_once()
    producer.begin_transaction.assert_called_once()
    producer.produce.assert_called_once()
    producer.commit_transaction.assert_called_once()


def test_click_publishes_the_quote_from_database(monkeypatch):
    producer = Mock()
    query = Mock(return_value=[{"text": "Пример цитаты", "character": "Бараш"}])
    monkeypatch.setattr(app, "producer", producer)
    monkeypatch.setattr(app, "producer_initialized", True)
    monkeypatch.setattr(app, "fetch_all", query)
    response = TestClient(app.app).post("/quote-click", json={"quote_id": 7})
    assert response.status_code == 202
    assert query.call_args.args[1] == (7,)
    event = json.loads(producer.produce.call_args.kwargs["value"])
    assert event["quote"] == {"text": "Пример цитаты", "character": "Бараш"}


def test_click_rejects_unknown_quote(monkeypatch):
    producer = Mock()
    monkeypatch.setattr(app, "producer", producer)
    monkeypatch.setattr(app, "fetch_all", Mock(return_value=[]))
    response = TestClient(app.app).post("/quote-click", json={"quote_id": 999})
    assert response.status_code == 404
    producer.produce.assert_not_called()


def test_click_returns_503_and_aborts_if_kafka_fails(monkeypatch):
    producer = Mock()
    producer.commit_transaction.side_effect = KafkaException(KafkaError(KafkaError._TIMED_OUT))
    monkeypatch.setattr(app, "producer", producer)
    monkeypatch.setattr(app, "producer_initialized", True)
    response = TestClient(app.app).post("/quote-click")
    assert response.status_code == 503
    producer.abort_transaction.assert_called_once()


def test_link_creates_private_session_and_qr(monkeypatch):
    query = Mock(return_value=[{"session_hash": "saved"}])
    monkeypatch.setattr(app, "fetch_all", query)
    client = TestClient(app.app)
    result = client.post('/telegram/link')
    assert result.status_code == 200
    assert result.json()['url'].startswith('https://t.me/KikoRiki_quotes_bot?start=')
    assert result.json()['qr'].startswith('data:image/svg+xml;base64,')
    assert 'HttpOnly' in result.headers['set-cookie']
    saved_session, saved_link = query.call_args.args[1]
    assert saved_session == app.token_hash(client.cookies['quotes_session'])
    assert saved_link != result.json()['url'].split('start=')[1]


def test_click_uses_only_current_browser_session(monkeypatch):
    producer = Mock()
    monkeypatch.setattr(app, 'producer', producer)
    monkeypatch.setattr(app, 'producer_initialized', True)
    token = 'a' * 43
    client = TestClient(app.app)
    client.cookies.set('quotes_session', token)
    result = client.post('/quote-click')
    assert result.status_code == 202
    import json
    event = json.loads(producer.produce.call_args.kwargs['value'])
    assert event['session_hash'] == app.token_hash(token)
    assert token not in json.dumps(event)


def test_linked_session_cookie_is_upgraded_to_secure(monkeypatch):
    monkeypatch.setattr(app, 'fetch_all', Mock(return_value=[{'linked': True}]))
    monkeypatch.setattr(app, 'COOKIE_SECURE', True)
    client = TestClient(app.app, base_url='https://localhost')
    client.cookies.set('quotes_session', 'a' * 43)
    response = client.get('/telegram/status')
    assert response.json() == {'linked': True}
    assert 'Secure' in response.headers['set-cookie']
