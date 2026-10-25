from __future__ import annotations

from io import BytesIO
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from literature_tree.providers import meterless
from literature_tree.providers.base import ONLINE, UNAUTHORIZED, ProviderStatus
from literature_tree.providers.meterless import MeterlessProvider
from literature_tree.providers import store
from literature_tree.providers.store import TOKEN_KEY, reject_placeholder, resolve_token
from literature_tree.providers.urls import normalize_base_url, parse_connect_link


class MeterlessProviderTests(unittest.TestCase):
    def test_base_url_normalization(self) -> None:
        for value in (
            "127.0.0.1:8088",
            "http://127.0.0.1:8088/v1",
            "http://127.0.0.1:8088/v1/chat/completions",
            "http://127.0.0.1:8088/v1/models",
            "http://127.0.0.1:8088/healthz",
        ):
            with self.subTest(value=value):
                self.assertEqual(normalize_base_url(value), "http://127.0.0.1:8088/v1")
        self.assertEqual(
            normalize_base_url("http://127.0.0.1:8088/v1/v1/models"),
            "http://127.0.0.1:8088/v1",
        )

    def test_connect_link_extracts_origin_and_token(self) -> None:
        link = parse_connect_link("http://runtime.local:8088/connect#k=secret")
        self.assertIsNotNone(link)
        assert link is not None
        self.assertEqual(link.base_url, "http://runtime.local:8088/v1")
        self.assertEqual(link.api_key, "secret")

    def test_unauthorized_status_asks_for_token(self) -> None:
        provider = MeterlessProvider(token="wrong-token")
        def unauthorized(request, timeout):
            self.assertEqual(timeout, 5)
            self.assertEqual(request.get_header("Authorization"), "Bearer wrong-token")
            self.assertEqual(request.get_header("Meterless-app"), "literature-tree")
            raise HTTPError(request.full_url, 401, "unauthorized", {}, BytesIO())

        with patch.object(meterless, "_open_without_redirects", side_effect=unauthorized):
            status = provider.status()
        self.assertEqual(status.state, UNAUTHORIZED)
        self.assertEqual(status.paste_token_field, TOKEN_KEY)

    def test_connect_input_persists_token_and_rejects_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            saved_path = Path(temp_dir) / "provider-settings.json"
            with patch.object(store, "SETTINGS_PATH", saved_path):
                provider = MeterlessProvider.from_connection_input(
                    "http://runtime.local:8088/connect#k=secret"
                )
                self.assertEqual(provider.base_url, "http://runtime.local:8088/v1")
                self.assertEqual(resolve_token(), "secret")
                with self.assertRaises(ValueError):
                    reject_placeholder("rt-local")

    def test_models_keep_unknown_meterless_routes(self) -> None:
        provider = MeterlessProvider(token="valid-token")
        with patch.object(
            provider,
            "_get_models",
            return_value=(
                200,
                {
                    "data": [
                        {"id": "meterless/auto"},
                        {"id": "meterless/new-class.x"},
                        {"id": "gpt-x"},
                    ]
                },
            ),
        ):
            status = provider.status()
        self.assertEqual(status.state, ONLINE)
        self.assertEqual(status.models, ("meterless/auto", "meterless/new-class.x"))

    def test_auto_detect_saves_first_authorized_or_unauthorized_hit(self) -> None:
        hit = ProviderStatus(
            id="meterless",
            name="Meterless Runtime",
            state=UNAUTHORIZED,
            base_url="http://127.0.0.1:8090/v1",
        )

        def status(self: MeterlessProvider) -> ProviderStatus:
            if self.base_url == hit.base_url:
                return hit
            return ProviderStatus(
                id="meterless", name="Meterless Runtime", state="offline", base_url=self.base_url
            )

        with (
            patch.object(MeterlessProvider, "status", status),
            patch.object(meterless, "save_meterless") as save,
        ):
            result = MeterlessProvider.auto_detect(token="valid-token")
        self.assertIs(result, hit)
        save.assert_called_once_with(base_url=hit.base_url)

    def test_chat_sends_string_content_and_contract_headers(self) -> None:
        provider = MeterlessProvider(token="valid-token")
        response = {"choices": [{"message": {"content": "answer"}}]}
        with patch.object(meterless, "_request_json", return_value=(200, response)) as request_json:
            answer = provider.complete(
                [{"role": "user", "content": "plain text"}],
                model="meterless/auto",
            )

        self.assertEqual(answer, "answer")
        request, = request_json.call_args.args
        self.assertEqual(request_json.call_args.kwargs["timeout"], 180)
        self.assertEqual(request.get_header("Authorization"), "Bearer valid-token")
        self.assertEqual(request.get_header("Meterless-app"), "literature-tree")
        self.assertEqual(request.get_header("Meterless-scope"), "user")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "meterless/auto")
        self.assertEqual(payload["messages"][0]["content"], "plain text")


if __name__ == "__main__":
    unittest.main()
