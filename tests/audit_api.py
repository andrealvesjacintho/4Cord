"""Testes de contrato da API: paginação, after e validação da ponte."""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import app as app_module
from core.discord import Discord


def check_heartbeat():
    client = Discord("token-de-teste", lambda ev: None)
    client._start_heartbeat(3600)
    first_stop = client._hb_stop
    first_thread = client._hb_thread
    assert first_thread.is_alive()

    client._start_heartbeat(3600)
    second_stop = client._hb_stop
    second_thread = client._hb_thread
    assert first_stop is not second_stop
    assert first_stop.is_set()
    assert not second_stop.is_set()
    assert second_thread.is_alive()

    first_thread.join(1)
    assert not first_thread.is_alive(), "heartbeat antigo continuou vivo"
    client.close()
    second_thread.join(1)
    assert second_stop.is_set()
    assert not second_thread.is_alive()
    return {"fresh_events": True, "old_thread_stopped": True}


class FakeAPI:
    def __init__(self):
        self.calls = []

    def messages(self, cid, before=None, limit=50, after=None):
        self.calls.append({
            "channel": cid, "before": before, "limit": limit, "after": after,
        })
        return []

    def dms(self):
        self.calls.append({"dms": True})
        return [{"id": "20", "type": 1}]


class FakeWindow:
    def __init__(self):
        self.api = FakeAPI()
        self.replies = []
        self.app = None

    def reply(self, rid, ok, data=None, error=None):
        self.replies.append({
            "id": rid, "ok": ok, "data": data, "error": error,
        })


def check_discord_paths():
    client = Discord("token-de-teste", lambda ev: None)
    paths = []

    def fake_request(method, path, *args, **kwargs):
        paths.append((method, path))
        return []

    client._request = fake_request
    client.messages("123")
    client.messages("123", before="456")
    client.messages("123", after="789", limit=100)
    client.messages("123", before="456", after="789")
    client.dms()
    expected = [
        ("GET", "/channels/123/messages?limit=50"),
        ("GET", "/channels/123/messages?limit=50&before=456"),
        ("GET", "/channels/123/messages?limit=100&after=789"),
        ("GET", "/channels/123/messages?limit=50&before=456"),
        ("GET", "/users/@me/channels"),
    ]
    assert paths == expected, (paths, expected)
    return paths


def check_desktop_detection():
    keys = ("XDG_CURRENT_DESKTOP", "DESKTOP_SESSION", "XDG_SESSION_DESKTOP")
    saved = {key: os.environ.get(key) for key in keys}
    try:
        empty = {key: "" for key in keys}
        cases = [
            (dict(empty, XDG_CURRENT_DESKTOP="XFCE",
                  DESKTOP_SESSION="xfce", XDG_SESSION_DESKTOP="xfce"), False),
            (dict(empty, XDG_CURRENT_DESKTOP="XFCE",
                  DESKTOP_SESSION="xubuntu", XDG_SESSION_DESKTOP="xfce"), False),
            (dict(empty, XDG_CURRENT_DESKTOP="KDE",
                  DESKTOP_SESSION="plasma", XDG_SESSION_DESKTOP="plasma"), False),
            (empty, False),
            (dict(empty, XDG_CURRENT_DESKTOP="GNOME",
                  DESKTOP_SESSION="gnome", XDG_SESSION_DESKTOP="gnome"), True),
            (dict(empty, XDG_CURRENT_DESKTOP="ubuntu:GNOME",
                  DESKTOP_SESSION="ubuntu", XDG_SESSION_DESKTOP="ubuntu"), True),
        ]
        for values, expected in cases:
            for key in keys:
                os.environ[key] = values[key]
            assert app_module.is_gnome_desktop() is expected, values
        for key in keys:
            os.environ.pop(key, None)
        assert app_module.is_gnome_desktop() is False
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return {"xfce": False, "xubuntu": False, "plasma": False,
            "gnome": True, "empty": False}


def handle(window, payload):
    app_module.MainWindow.handle(window, payload)
    assert window.replies, "a ponte não respondeu"
    return window.replies[-1]


def check_bridge():
    window = FakeWindow()
    reply = handle(window, {
        "id": 1, "cmd": "messages",
        "args": {"channel": "20", "after": "123", "limit": 500},
    })
    assert reply["ok"] is True
    assert window.api.calls[-1] == {
        "channel": "20", "before": None, "limit": 100, "after": "123",
    }, window.api.calls[-1]

    reply = handle(window, {
        "id": 2, "cmd": "messages",
        "args": {"channel": "20", "after": "abc", "limit": "invalido"},
    })
    assert reply["ok"] is True
    assert window.api.calls[-1] == {
        "channel": "20", "before": None, "limit": 50, "after": None,
    }, window.api.calls[-1]

    reply = handle(window, {
        "id": 3, "cmd": "messages",
        "args": {"channel": "20", "after": "-1", "limit": 0},
    })
    assert reply["ok"] is True
    assert window.api.calls[-1]["limit"] == 1
    assert window.api.calls[-1]["after"] is None

    reply = handle(window, {"id": 4, "cmd": "dms", "args": {}})
    assert reply["ok"] is True
    assert reply["data"] == [{"id": "20", "type": 1}]

    mock = app_module.MockAPI()
    assert mock.messages("100", after="123") == []
    assert mock.messages("100", before="123") == []
    assert len(mock.messages("100")) > 0

    return {
        "last_call": window.api.calls[0],
        "replies": len(window.replies),
        "mock_normal": len(mock.messages("100")),
    }


if __name__ == "__main__":
    result = {
        "paths": check_discord_paths(),
        "bridge": check_bridge(),
        "heartbeat": check_heartbeat(),
        "desktop": check_desktop_detection(),
    }
    print("API_AUDIT " + json.dumps(result, ensure_ascii=False))
