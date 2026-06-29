import os
import tempfile
import unittest
from pathlib import Path

import init_env


def parse_env(text):
    result = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        result[key] = value
    return result


class EnvInitTests(unittest.TestCase):
    def test_default_env_writes_every_config_key_with_auto_machine_capacity(self):
        text = init_env.render_env(init_env.default_values())
        values = parse_env(text)

        self.assertEqual(set(values), {field.key for field in init_env.CONFIG_FIELDS})
        self.assertEqual(values["EMAIL_MODE"], "tempmail")
        self.assertEqual(values["PHYSICAL_CAP"], "0")
        self.assertEqual(values["PHYSICAL_PER_CPU"], "2")
        self.assertEqual(values["PHYSICAL_MEM_MB"], "512")
        self.assertEqual(values["MIN_FREE_MEM_MB"], "500")
        self.assertEqual(values["OUTPUT_ROOT"], "keys")
        self.assertEqual(values["GROK2API_APPEND"], "1")

    def test_custom_env_prompts_all_fields_and_uses_enter_for_defaults(self):
        answers = iter([
            "2",
            "custom",
            "example.com",
            "http://127.0.0.1:8081",
            "25",
            "batch_demo",
            "out",
            "",
            "https://api.example.test/admin/api/tokens",
            "secret-token",
            "0",
            "0",
            "6",
        ])
        prompts = []

        def ask(prompt):
            prompts.append(prompt)
            return next(answers, "")

        values = init_env.collect_values(input_func=ask, output_func=lambda _msg="": None)

        self.assertEqual(values["EMAIL_MODE"], "custom")
        self.assertEqual(values["EMAIL_DOMAIN"], "example.com")
        self.assertEqual(values["EMAIL_API"], "http://127.0.0.1:8081")
        self.assertEqual(values["TARGET"], "25")
        self.assertEqual(values["RUN_LABEL"], "batch_demo")
        self.assertEqual(values["OUTPUT_ROOT"], "out")
        self.assertEqual(values["OUTPUT_DIR"], "")
        self.assertEqual(values["GROK2API_ENDPOINT"], "https://api.example.test/admin/api/tokens")
        self.assertEqual(values["GROK2API_TOKEN"], "secret-token")
        self.assertEqual(values["GROK2API_APPEND"], "0")
        self.assertEqual(values["GROK2API_INSECURE"], "0")
        self.assertEqual(values["PHYSICAL_CAP"], "6")
        self.assertEqual(values["SOLVER_TIMELINE_TRACE"], "0")
        self.assertTrue(any("EMAIL_DOMAIN" in prompt for prompt in prompts))
        self.assertTrue(any("EMAIL_API" in prompt for prompt in prompts))
        self.assertTrue(any("GROK2API_TOKEN" in prompt for prompt in prompts))
        self.assertTrue(any("GROK2API_APPEND" in prompt for prompt in prompts))
        self.assertFalse(any("SOLVER_TIMELINE_SAMPLE" in prompt for prompt in prompts))

    def test_tempmail_skips_custom_email_prompts(self):
        answers = iter([
            "2",
            "tempmail",
        ])
        prompts = []

        def ask(prompt):
            prompts.append(prompt)
            return next(answers, "")

        values = init_env.collect_values(input_func=ask, output_func=lambda _msg="": None)

        self.assertEqual(values["EMAIL_MODE"], "tempmail")
        self.assertEqual(values["EMAIL_DOMAIN"], "")
        self.assertEqual(values["EMAIL_API"], "http://127.0.0.1:8080")
        self.assertFalse(any("EMAIL_DOMAIN" in prompt for prompt in prompts))
        self.assertFalse(any("EMAIL_API" in prompt for prompt in prompts))

    def test_empty_grok2api_endpoint_skips_push_detail_prompts(self):
        answers = iter([
            "2",
            "tempmail",
        ])
        prompts = []

        def ask(prompt):
            prompts.append(prompt)
            return next(answers, "")

        values = init_env.collect_values(input_func=ask, output_func=lambda _msg="": None)

        self.assertEqual(values["GROK2API_ENDPOINT"], "")
        self.assertEqual(values["GROK2API_TOKEN"], "")
        self.assertEqual(values["GROK2API_APPEND"], "1")
        self.assertEqual(values["GROK2API_INSECURE"], "0")
        self.assertFalse(any("GROK2API_TOKEN" in prompt for prompt in prompts))
        self.assertFalse(any("GROK2API_APPEND" in prompt for prompt in prompts))
        self.assertFalse(any("GROK2API_INSECURE" in prompt for prompt in prompts))

    def test_disabled_optional_features_skip_their_detail_prompts(self):
        answers = iter([
            "2",
            "tempmail",
        ])
        prompts = []

        def ask(prompt):
            prompts.append(prompt)
            return next(answers, "")

        values = init_env.collect_values(input_func=ask, output_func=lambda _msg="": None)

        self.assertEqual(values["SOLVER_REUSE"], "1")
        self.assertEqual(values["MAX_SOLVER_REUSE"], "25")
        self.assertEqual(values["SOLVER_TIMELINE_TRACE"], "0")
        self.assertEqual(values["SOLVER_TIMELINE_SAMPLE"], "8")
        self.assertEqual(values["C_HOT_PAGE_POOL"], "0")
        self.assertEqual(values["C_HOT_PAGE_POOL_SIZE"], "0")
        self.assertFalse(any("SOLVER_TIMELINE_SAMPLE" in prompt for prompt in prompts))
        self.assertFalse(any("C_HOT_PAGE_POOL_SIZE" in prompt for prompt in prompts))

    def test_setup_script_suppresses_package_manager_noise(self):
        text = Path("setup.sh").read_text(encoding="utf-8")

        self.assertIn("APT_LISTCHANGES_FRONTEND=none", text)
        self.assertIn("apt update -qq >/dev/null", text)
        self.assertIn("apt install -y -qq", text)
        self.assertIn(">/dev/null 2>&1", text)

    def test_start_script_uses_single_clear_step_sequence(self):
        text = Path("start.sh").read_text(encoding="utf-8")

        self.assertIn("[1/4] 检查 Python 环境", text)
        self.assertIn("[2/4] 检查浏览器", text)
        self.assertIn("[3/4] 初始化配置", text)
        self.assertIn("[4/4] 初始化完成", text)

    def test_collect_values_uses_defaults_when_input_stream_ends(self):
        def ask(_prompt):
            raise EOFError()

        values = init_env.collect_values(input_func=ask, output_func=lambda _msg="": None)

        self.assertEqual(values, init_env.default_values())

    def test_write_env_preserves_existing_file_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("EMAIL_MODE=custom\n", encoding="utf-8")

            wrote = init_env.write_env(path, force=False, values={"EMAIL_MODE": "tempmail"})

            self.assertFalse(wrote)
            self.assertEqual(path.read_text(encoding="utf-8"), "EMAIL_MODE=custom\n")

    def test_write_env_force_replaces_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("EMAIL_MODE=custom\n", encoding="utf-8")

            wrote = init_env.write_env(path, force=True, values=init_env.default_values())

            self.assertTrue(wrote)
            self.assertIn("EMAIL_MODE=tempmail\n", path.read_text(encoding="utf-8"))


class ScriptBoundaryTests(unittest.TestCase):
    def test_start_sh_initializes_and_stops_before_register(self):
        text = Path("start.sh").read_text(encoding="utf-8")

        self.assertIn("init_env.py", text)
        self.assertIn("bash run.sh", text)
        self.assertNotIn("register.py \"$@\"", text)

    def test_run_sh_is_the_register_entrypoint_and_requires_env(self):
        text = Path("run.sh").read_text(encoding="utf-8")

        self.assertIn("[ ! -f .env ]", text)
        self.assertIn("bash start.sh --init", text)
        self.assertIn("exec .venv/bin/python register.py \"$@\"", text)


if __name__ == "__main__":
    unittest.main()
