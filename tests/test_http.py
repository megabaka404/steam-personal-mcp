from __future__ import annotations

import httpx
import pytest

from cache.memory_cache import MemoryTTLCache
from clients.http_client import JsonHttpClient


def client_for(handler, retries=0):
    return JsonHttpClient(timeout=0.05, max_retries=retries, min_request_interval=0, transport=httpx.MockTransport(handler), cache=MemoryTTLCache())


def test_http_200_and_cache():
    calls = []
    client = client_for(lambda request: (calls.append(request) or httpx.Response(200, json={"ok": True})))
    assert client.get_json("https://mock", cache_key="x", cache_ttl=60) == {"ok": True}
    assert client.get_json("https://mock", cache_key="x", cache_ttl=60) == {"ok": True}
    assert len(calls) == 1


@pytest.mark.parametrize("status,code", [(401, "HTTP_UNAUTHORIZED"), (403, "HTTP_UNAUTHORIZED"), (429, "RATE_LIMITED"), (500, "NETWORK_ERROR")])
def test_http_statuses(status, code):
    client = client_for(lambda request: httpx.Response(status), retries=0)
    with pytest.raises(Exception) as exc:
        client.get_json("https://mock")
    assert getattr(exc.value, "code", None) == code


def test_invalid_json():
    client = client_for(lambda request: httpx.Response(200, content=b"not json"))
    with pytest.raises(Exception) as exc:
        client.get_json("https://mock")
    assert getattr(exc.value, "code", None) == "NETWORK_ERROR"


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    client = client_for(handler)
    with pytest.raises(Exception) as exc:
        client.get_json("https://mock")
    assert getattr(exc.value, "code", None) == "NETWORK_ERROR"
