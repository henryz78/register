from __future__ import annotations

import argparse
import os
from glob import glob
from pathlib import Path

from token_sync import collect_tokens_from_files, push_sso_to_api


DEFAULT_DATA_DIR = "keys"


def resolve_input_paths(*, input_glob: str = "", run_label: str = "", data_dir: str = DEFAULT_DATA_DIR) -> list[str]:
    if input_glob:
        return sorted(glob(input_glob))
    label = str(run_label or "").strip()
    if not label:
        return []
    return [str(Path(data_dir or DEFAULT_DATA_DIR) / label / "grok.txt")]


def default_output_path(*, run_label: str = "", data_dir: str = DEFAULT_DATA_DIR) -> str:
    label = str(run_label or "").strip()
    if not label:
        return ""
    return str(Path(data_dir or DEFAULT_DATA_DIR) / label / "merged_tokens.txt")


def write_merged_tokens(tokens: list[str], output_path: str) -> None:
    if not output_path:
        return
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{token}\n" for token in tokens), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="合并本地 sso token 并推送到 grok2api")
    parser.add_argument("--input-glob", default="", help="待合并的 token 文件 glob，例如 keys/*/grok.txt")
    parser.add_argument("--run-label", default="", help="运行批次名，例如 test_001，会读取 keys/<run_label>/grok.txt")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="批次根目录，默认 keys")
    parser.add_argument("--output", default="", help="可选：写出合并后的 token 文件")
    parser.add_argument("--endpoint", default="", help="grok2api /admin/api/tokens 完整地址；也可用 GROK2API_ENDPOINT")
    parser.add_argument("--api-token", default="", help="grok2api app_key；也可用 GROK2API_TOKEN")
    parser.add_argument("--append", dest="append", action="store_true", default=True, help="先查询线上 token 再去重合并")
    parser.add_argument("--replace", dest="append", action="store_false", help="用本次合并结果覆盖线上 token 列表")
    parser.add_argument("--no-push", action="store_true", help="只合并写文件，跳过推送")
    return parser


def main(argv: list[str] | None = None, *, push_func=push_sso_to_api) -> int:
    args = build_parser().parse_args(argv)
    run_label = args.run_label or os.environ.get("RUN_LABEL", "").strip()
    input_paths = resolve_input_paths(
        input_glob=args.input_glob,
        run_label=run_label,
        data_dir=args.data_dir,
    )
    if not input_paths:
        print("[Error] 必须提供 --input-glob 或 --run-label")
        return 2

    tokens = collect_tokens_from_files(input_paths)
    if not tokens:
        print(f"[Warn] 未找到可推送的 token 文件: {', '.join(input_paths)}")
        return 1

    output_path = args.output or default_output_path(run_label=run_label, data_dir=args.data_dir)
    if output_path:
        write_merged_tokens(tokens, output_path)
        print(f"[*] 已合并 {len(tokens)} 个 token 到: {output_path}")

    if args.no_push:
        print("[*] 已跳过推送")
        return 0

    result = push_func(
        tokens,
        endpoint=args.endpoint or None,
        api_token=args.api_token or None,
        append=args.append,
    )
    if result.get("pushed"):
        print(f"[*] SSO token 已推送到 API（共 {result.get('count', 0)} 个）")
        return 0
    print(f"[Warn] 推送跳过或失败: {result.get('reason', 'unknown')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
