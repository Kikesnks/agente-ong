"""Tests de `is_ollama_available` (R7, T9): ping ligero, sin red real."""

from __future__ import annotations

from unittest.mock import patch

import httpx

from agente_ong.llm.health import is_ollama_available

_GET = "agente_ong.llm.health.httpx.get"


def _response(status_code: int) -> httpx.Response:
    request = httpx.Request("GET", "http://localhost:11434/api/tags")
    return httpx.Response(status_code, request=request)


def test_is_ollama_available_ok_returns_true() -> None:
    with patch(_GET, return_value=_response(200)):
        assert is_ollama_available() is True


def test_is_ollama_available_connection_error_returns_false_without_exception() -> None:
    with patch(_GET, side_effect=httpx.ConnectError("conexion rechazada")):
        assert is_ollama_available() is False


def test_is_ollama_available_timeout_returns_false() -> None:
    with patch(_GET, side_effect=httpx.TimeoutException("timeout")):
        assert is_ollama_available() is False


def test_is_ollama_available_http_error_status_returns_false() -> None:
    with patch(_GET, return_value=_response(500)):
        assert is_ollama_available() is False


def test_is_ollama_available_calls_get_with_expected_url_and_timeout() -> None:
    with patch(_GET, return_value=_response(200)) as mock_get:
        is_ollama_available(base_url="http://otrohost:11434", timeout=2.5)

    mock_get.assert_called_once_with("http://otrohost:11434/api/tags", timeout=2.5)
