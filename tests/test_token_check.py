import json
import pathlib
import shutil
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeResponse:
    def __init__(self, status_code, content_type="application/json", text='{"ok": true}'):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.text = text


class TokenCheckTests(unittest.TestCase):
    def test_check_token_classifies_alive_dead_and_unknown(self):
        from token_check import check_token

        def requester(_url, **kwargs):
            token = kwargs["cookies"]["sso"]
            if token == "alive-token":
                return FakeResponse(200)
            if token == "dead-token":
                return FakeResponse(401)
            if token == "limited-token":
                return FakeResponse(429)
            raise AssertionError(token)

        alive = check_token("alive-token", request_get=requester)
        dead = check_token("dead-token", request_get=requester)
        limited = check_token("limited-token", request_get=requester)

        self.assertEqual(alive.status, "alive")
        self.assertEqual(dead.status, "dead")
        self.assertEqual(limited.status, "unknown")
        self.assertEqual(limited.http_status, 429)

    def test_html_200_is_unknown_not_alive(self):
        from token_check import check_token

        result = check_token(
            "maybe-token",
            request_get=lambda _url, **_kwargs: FakeResponse(200, "text/html", "<html></html>"),
        )

        self.assertEqual(result.status, "unknown")
        self.assertIn("non-json", result.reason)

    def test_html_403_is_unknown_to_avoid_cloudflare_false_dead(self):
        from token_check import check_token

        result = check_token(
            "maybe-token",
            request_get=lambda _url, **_kwargs: FakeResponse(403, "text/html", "<html>blocked</html>"),
        )

        self.assertEqual(result.status, "unknown")
        self.assertIn("non-json-403", result.reason)

    def test_request_exception_is_unknown(self):
        from token_check import check_token

        def requester(_url, **_kwargs):
            raise TimeoutError("slow")

        result = check_token("timeout-token", request_get=requester)

        self.assertEqual(result.status, "unknown")
        self.assertIn("TimeoutError", result.reason)

    def test_write_outputs_groups_tokens_and_keeps_summary_token_free(self):
        from token_check import TokenCheckResult, write_check_outputs

        temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="token_check_test_"))
        try:
            results = [
                TokenCheckResult("alive-token-secret", "alive", 200, "ok"),
                TokenCheckResult("dead-token-secret", "dead", 401, "auth_failed"),
                TokenCheckResult("unknown-token-secret", "unknown", 429, "rate_limited"),
            ]

            summary = write_check_outputs(results, temp_dir, check_url="https://grok.com/rest/test")

            self.assertEqual((temp_dir / "alive_tokens.txt").read_text(encoding="utf-8").strip(), "alive-token-secret")
            self.assertEqual((temp_dir / "dead_tokens.txt").read_text(encoding="utf-8").strip(), "dead-token-secret")
            self.assertEqual((temp_dir / "unknown_tokens.txt").read_text(encoding="utf-8").strip(), "unknown-token-secret")
            self.assertEqual(summary["counts"], {"alive": 1, "dead": 1, "unknown": 1, "total": 3})

            summary_text = (temp_dir / "token_check_summary.json").read_text(encoding="utf-8")
            self.assertNotIn("alive-token-secret", summary_text)
            self.assertEqual(json.loads(summary_text)["check_url"], "https://grok.com/rest/test")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_check_tokens_reports_progress_and_applies_worker_interval(self):
        import token_check

        original_check_token = token_check.check_token
        original_sleep = token_check.time.sleep
        sleep_calls = []
        progress = []

        def fake_check_token(token, **_kwargs):
            return token_check.TokenCheckResult(token, "alive", 200, "ok")

        token_check.check_token = fake_check_token
        token_check.time.sleep = lambda seconds: sleep_calls.append(seconds)
        try:
            results = token_check.check_tokens(
                ["token-a", "token-b", "token-c"],
                concurrency=2,
                interval=1,
                timeout=1,
                progress_callback=lambda completed, total, result: progress.append(
                    (completed, total, result.token)
                ),
            )
        finally:
            token_check.check_token = original_check_token
            token_check.time.sleep = original_sleep

        self.assertEqual([item.token for item in results], ["token-a", "token-b", "token-c"])
        self.assertEqual(len(sleep_calls), 3)
        self.assertTrue(all(seconds == 1 for seconds in sleep_calls))
        self.assertEqual(len(progress), 3)
        self.assertEqual(progress[-1][0:2], (3, 3))

    def test_run_label_reads_batch_grok_file(self):
        from token_check import collect_input_tokens

        with tempfile.TemporaryDirectory() as tmp:
            batch_dir = pathlib.Path(tmp) / "batch-001"
            batch_dir.mkdir()
            (batch_dir / "grok.txt").write_text("token-a\ntoken-b\ntoken-a\n", encoding="utf-8")

            tokens = collect_input_tokens(run_label="batch-001", data_dir=tmp)

        self.assertEqual(tokens, ["token-a", "token-b"])

    def test_default_output_dir_uses_batch_directory_for_run_label(self):
        from token_check import default_output_dir

        output_dir = pathlib.Path(default_output_dir("batch-001", data_dir="keys"))

        self.assertEqual(output_dir.parent.as_posix(), "keys/batch-001")
        self.assertTrue(output_dir.name.startswith("token_check_"))


if __name__ == "__main__":
    unittest.main()
