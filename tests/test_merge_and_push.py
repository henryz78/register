import pathlib
import os
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class MergeAndPushTests(unittest.TestCase):
    def test_run_label_reads_batch_grok_writes_merged_tokens_and_pushes(self):
        import merge_and_push

        pushed = []

        def fake_push(tokens, **kwargs):
            pushed.append({"tokens": list(tokens), **kwargs})
            return {"pushed": True, "count": len(tokens)}

        with tempfile.TemporaryDirectory() as tmp:
            batch_dir = pathlib.Path(tmp) / "batch-001"
            batch_dir.mkdir()
            (batch_dir / "grok.txt").write_text("token-a\ntoken-b\ntoken-a\n", encoding="utf-8")

            rc = merge_and_push.main(
                ["--run-label", "batch-001", "--data-dir", tmp],
                push_func=fake_push,
            )

            merged = (batch_dir / "merged_tokens.txt").read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        self.assertEqual(merged, "token-a\ntoken-b\n")
        self.assertEqual(pushed[0]["tokens"], ["token-a", "token-b"])

    def test_run_label_uses_shared_sanitized_batch_name(self):
        import merge_and_push

        with tempfile.TemporaryDirectory() as tmp:
            batch_dir = pathlib.Path(tmp) / "batch_001"
            batch_dir.mkdir()
            (batch_dir / "grok.txt").write_text("token-a\n", encoding="utf-8")

            rc = merge_and_push.main(
                ["--run-label", "batch 001", "--data-dir", tmp, "--no-push"],
            )

            merged = (batch_dir / "merged_tokens.txt").read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        self.assertEqual(merged, "token-a\n")

    def test_append_argument_defaults_to_environment(self):
        import merge_and_push

        old_value = os.environ.get("GROK2API_APPEND")
        pushed = []

        def fake_push(tokens, **kwargs):
            pushed.append({"tokens": list(tokens), **kwargs})
            return {"pushed": True, "count": len(tokens)}

        try:
            os.environ["GROK2API_APPEND"] = "0"
            with tempfile.TemporaryDirectory() as tmp:
                batch_dir = pathlib.Path(tmp) / "batch-001"
                batch_dir.mkdir()
                (batch_dir / "grok.txt").write_text("token-a\n", encoding="utf-8")

                rc = merge_and_push.main(
                    ["--run-label", "batch-001", "--data-dir", tmp],
                    push_func=fake_push,
                )
        finally:
            if old_value is None:
                os.environ.pop("GROK2API_APPEND", None)
            else:
                os.environ["GROK2API_APPEND"] = old_value

        self.assertEqual(rc, 0)
        self.assertIsNone(pushed[0]["append"])
        self.assertIsNone(pushed[0]["verify_tls"])

    def test_insecure_argument_overrides_tls_environment_default(self):
        import merge_and_push

        pushed = []

        def fake_push(tokens, **kwargs):
            pushed.append({"tokens": list(tokens), **kwargs})
            return {"pushed": True, "count": len(tokens)}

        with tempfile.TemporaryDirectory() as tmp:
            batch_dir = pathlib.Path(tmp) / "batch-001"
            batch_dir.mkdir()
            (batch_dir / "grok.txt").write_text("token-a\n", encoding="utf-8")

            rc = merge_and_push.main(
                ["--run-label", "batch-001", "--data-dir", tmp, "--insecure"],
                push_func=fake_push,
            )

        self.assertEqual(rc, 0)
        self.assertFalse(pushed[0]["verify_tls"])

    def test_input_glob_can_write_explicit_output(self):
        import merge_and_push

        with tempfile.TemporaryDirectory() as tmp:
            first = pathlib.Path(tmp) / "first.txt"
            second = pathlib.Path(tmp) / "second.txt"
            output = pathlib.Path(tmp) / "out" / "merged.txt"
            first.write_text("a\nb\n", encoding="utf-8")
            second.write_text("b\nc\n", encoding="utf-8")

            rc = merge_and_push.main(
                [
                    "--input-glob",
                    str(pathlib.Path(tmp) / "*.txt"),
                    "--output",
                    str(output),
                    "--no-push",
                ]
            )

            merged = output.read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        self.assertEqual(merged, "a\nb\nc\n")


if __name__ == "__main__":
    unittest.main()
