import json
import os
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content_type="application/json", text=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = {"Content-Type": content_type}
        self.text = json.dumps(self._payload) if text is None else text

    def json(self):
        return self._payload


class TokenSyncTests(unittest.TestCase):
    def test_extract_existing_tokens_handles_nested_payload_shapes(self):
        from token_sync import extract_existing_tokens

        payload = {
            "data": {
                "payload": {
                    "ssoBasic": [
                        {"token": "token-a"},
                        {"value": "token-b"},
                        {"sso": "token-c"},
                        "token-d",
                    ]
                }
            }
        }

        self.assertEqual(
            extract_existing_tokens(payload),
            ["token-a", "token-b", "token-c", "token-d"],
        )

    def test_push_sso_to_api_appends_existing_and_dedupes_before_posting(self):
        from token_sync import push_sso_to_api

        posts = []

        def fake_get(url, **kwargs):
            self.assertEqual(url, "https://api.example/admin/api/tokens")
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
            return FakeResponse(payload={"ssoBasic": ["old-token", "dup-token"]})

        def fake_post(url, **kwargs):
            posts.append({"url": url, **kwargs})
            return FakeResponse(payload={"ok": True})

        result = push_sso_to_api(
            ["dup-token", "new-token", "new-token"],
            endpoint="https://api.example/admin/api/tokens",
            api_token="secret",
            append=True,
            request_get=fake_get,
            request_post=fake_post,
        )

        self.assertTrue(result["pushed"])
        self.assertEqual(posts[0]["json"], {"ssoBasic": ["old-token", "dup-token", "new-token"]})
        self.assertEqual(posts[0]["verify"], True)

    def test_push_sso_to_api_verifies_tls_by_default_for_append_get(self):
        from token_sync import push_sso_to_api

        verify_values = []

        def fake_get(_url, **kwargs):
            verify_values.append(("get", kwargs["verify"]))
            return FakeResponse(payload={"ssoBasic": []})

        def fake_post(_url, **kwargs):
            verify_values.append(("post", kwargs["verify"]))
            return FakeResponse(payload={"ok": True})

        result = push_sso_to_api(
            ["new-token"],
            endpoint="https://api.example/admin/api/tokens",
            api_token="secret",
            append=True,
            request_get=fake_get,
            request_post=fake_post,
        )

        self.assertTrue(result["pushed"])
        self.assertEqual(verify_values, [("get", True), ("post", True)])

    def test_grok2api_append_env_zero_uses_replace_mode(self):
        from token_sync import push_sso_to_api

        old_value = os.environ.get("GROK2API_APPEND")
        posts = []
        get_called = False

        def fake_get(_url, **_kwargs):
            nonlocal get_called
            get_called = True
            return FakeResponse(payload={"ssoBasic": ["old-token"]})

        def fake_post(_url, **kwargs):
            posts.append(kwargs["json"])
            return FakeResponse(payload={"ok": True})

        try:
            os.environ["GROK2API_APPEND"] = "0"
            result = push_sso_to_api(
                ["new-token"],
                endpoint="https://api.example/admin/api/tokens",
                api_token="secret",
                request_get=fake_get,
                request_post=fake_post,
            )
        finally:
            if old_value is None:
                os.environ.pop("GROK2API_APPEND", None)
            else:
                os.environ["GROK2API_APPEND"] = old_value

        self.assertTrue(result["pushed"])
        self.assertFalse(get_called)
        self.assertEqual(posts, [{"ssoBasic": ["new-token"]}])

    def test_collect_tokens_from_files_dedupes_in_order(self):
        from token_sync import collect_tokens_from_files

        with tempfile.TemporaryDirectory() as tmp:
            first = pathlib.Path(tmp) / "first.txt"
            second = pathlib.Path(tmp) / "second.txt"
            first.write_text("a\nb\na\n", encoding="utf-8")
            second.write_text("b\nc\n", encoding="utf-8")

            tokens = collect_tokens_from_files([str(first), str(second)])

        self.assertEqual(tokens, ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
