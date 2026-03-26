import pytest
from unittest.mock import patch, MagicMock
from src.utils.web import WebClient, WEIBO_UA


def test_extract_text_strips_tags():
    html = "<p>Hello <b>world</b></p>"
    assert WebClient.extract_text(html) == "Hello world"


def test_extract_text_handles_empty():
    assert WebClient.extract_text("") == ""


def test_webclient_sets_ua():
    client = WebClient()
    assert WEIBO_UA in client.session.headers["User-Agent"]


def test_webclient_sets_referer():
    client = WebClient()
    assert client.session.headers.get("Referer") == "https://m.weibo.cn/"


def test_webclient_sets_cookie():
    client = WebClient(cookie="SUB=abc")
    assert client.session.headers.get("Cookie") == "SUB=abc"


def test_webclient_fetch_returns_text():
    client = WebClient()
    mock_resp = MagicMock()
    mock_resp.text = "hello"
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
        result = client.fetch("https://example.com")
    assert result == "hello"
    mock_get.assert_called_once_with("https://example.com", timeout=10)


def test_webclient_fetch_raises_fetch_error_on_http_error():
    import requests
    client = WebClient()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.HTTPError("404")
    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(WebClient.FetchError):
            client.fetch("https://example.com")


def test_webclient_fetch_json_parses():
    client = WebClient()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client.session, "get", return_value=mock_resp):
        result = client.fetch_json("https://example.com")
    assert result == {"ok": True}
