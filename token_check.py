from __future__ import annotations

import argparse
import datetime
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Callable, Iterable


DEFAULT_CHECK_URL = "https://grok.com/rest/app-chat/conversations?pageSize=1"
DEFAULT_DATA_DIR = "keys"
ALIVE_FILE = "alive_tokens.txt"
DEAD_FILE = "dead_tokens.txt"
UNKNOWN_FILE = "unknown_tokens.txt"
SUMMARY_FILE = "token_check_summary.json"


@dataclass(frozen=True)
class TokenCheckResult:
    token: str
    status: str
    http_status: int | None
    reason: str


def _looks_json_response(response) -> bool:
    content_type = str(getattr(response, "headers", {}).get("Content-Type", "")).lower()
    text = str(getattr(response, "text", "") or "").lstrip()
    return "application/json" in content_type or text.startswith("{") or text.startswith("[")


def _classify_response(token: str, response) -> TokenCheckResult:
    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code == 200:
        if _looks_json_response(response):
            return TokenCheckResult(token, "alive", status_code, "ok")
        return TokenCheckResult(token, "unknown", status_code, "non-json-200")
    if status_code == 401:
        return TokenCheckResult(token, "dead", status_code, "auth_failed")
    if status_code == 403:
        if _looks_json_response(response):
            return TokenCheckResult(token, "dead", status_code, "auth_failed")
        return TokenCheckResult(token, "unknown", status_code, "non-json-403")
    if status_code == 429:
        return TokenCheckResult(token, "unknown", status_code, "rate_limited")
    if 500 <= status_code <= 599:
        return TokenCheckResult(token, "unknown", status_code, "server_error")
    return TokenCheckResult(token, "unknown", status_code, "unexpected_status")


def check_token(
    token: str,
    *,
    check_url: str = DEFAULT_CHECK_URL,
    timeout: float = 15,
    request_get: Callable | None = None,
) -> TokenCheckResult:
    normalized = str(token or "").strip()
    if not normalized:
        return TokenCheckResult("", "unknown", None, "empty_token")

    get = request_get
    if get is None:
        import requests
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        get = requests.get
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        response = get(
            check_url,
            headers=headers,
            cookies={"sso": normalized},
            timeout=timeout,
            verify=False,
        )
    except Exception as exc:
        return TokenCheckResult(normalized, "unknown", None, f"{type(exc).__name__}: {exc}")
    return _classify_response(normalized, response)


def _write_token_file(path: Path, tokens: Iterable[str]) -> None:
    values = [str(token).strip() for token in tokens if str(token).strip()]
    path.write_text("".join(f"{token}\n" for token in values), encoding="utf-8")


def write_check_outputs(
    results: list[TokenCheckResult],
    output_dir: str | os.PathLike,
    *,
    check_url: str = DEFAULT_CHECK_URL,
) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    groups = {
        "alive": [item.token for item in results if item.status == "alive"],
        "dead": [item.token for item in results if item.status == "dead"],
        "unknown": [item.token for item in results if item.status == "unknown"],
    }
    _write_token_file(out / ALIVE_FILE, groups["alive"])
    _write_token_file(out / DEAD_FILE, groups["dead"])
    _write_token_file(out / UNKNOWN_FILE, groups["unknown"])

    counts = {
        "alive": len(groups["alive"]),
        "dead": len(groups["dead"]),
        "unknown": len(groups["unknown"]),
        "total": len(results),
    }
    reason_counts: dict[str, int] = {}
    http_status_counts: dict[str, int] = {}
    for item in results:
        reason_counts[item.reason] = reason_counts.get(item.reason, 0) + 1
        key = "none" if item.http_status is None else str(item.http_status)
        http_status_counts[key] = http_status_counts.get(key, 0) + 1

    summary = {
        "check_url": check_url,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "counts": counts,
        "reason_counts": reason_counts,
        "http_status_counts": http_status_counts,
        "files": {
            "alive": str((out / ALIVE_FILE).as_posix()),
            "dead": str((out / DEAD_FILE).as_posix()),
            "unknown": str((out / UNKNOWN_FILE).as_posix()),
            "summary": str((out / SUMMARY_FILE).as_posix()),
        },
    }
    (out / SUMMARY_FILE).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def _resolve_run_label_input(run_label: str, data_dir: str) -> list[str]:
    label = str(run_label or "").strip()
    if not label:
        return []
    base = Path(str(data_dir or DEFAULT_DATA_DIR))
    candidates = [
        base / label / "grok.txt",
        base / label / "merged_tokens.txt",
    ]
    return [str(path) for path in candidates if path.is_file()]


def collect_tokens_from_files(paths: Iterable[str]) -> list[str]:
    merged: list[str] = []
    seen = set()
    for path in paths:
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as file:
            for line in file:
                token = line.strip()
                if not token or token in seen:
                    continue
                seen.add(token)
                merged.append(token)
    return merged


def collect_input_tokens(
    *,
    input_files: Iterable[str] = (),
    input_globs: Iterable[str] = (),
    run_label: str = "",
    data_dir: str = DEFAULT_DATA_DIR,
) -> list[str]:
    paths: list[str] = []
    paths.extend(str(path) for path in input_files if str(path).strip())
    for pattern in input_globs:
        text = str(pattern or "").strip()
        if text:
            paths.extend(sorted(glob(text)))
    paths.extend(_resolve_run_label_input(run_label, data_dir))
    return collect_tokens_from_files(paths)


def check_tokens(
    tokens: list[str],
    *,
    check_url: str = DEFAULT_CHECK_URL,
    concurrency: int = 3,
    interval: float = 1,
    timeout: float = 15,
    progress_callback: Callable[[int, int, TokenCheckResult], None] | None = None,
) -> list[TokenCheckResult]:
    if not tokens:
        return []
    worker_count = max(1, int(concurrency or 1))
    delay = max(0.0, float(interval or 0))
    results: list[TokenCheckResult] = []

    def run_check(token: str) -> TokenCheckResult:
        result = check_token(
            token,
            check_url=check_url,
            timeout=timeout,
        )
        if delay:
            time.sleep(delay)
        return result

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(run_check, token): token for token in tokens}
        total = len(futures)
        for completed, future in enumerate(as_completed(futures), start=1):
            token = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = TokenCheckResult(token, "unknown", None, f"{type(exc).__name__}: {exc}")
            results.append(result)
            if progress_callback is not None:
                progress_callback(completed, total, result)

    order = {token: index for index, token in enumerate(tokens)}
    results.sort(key=lambda item: order.get(item.token, len(order)))
    return results


def default_output_dir(run_label: str = "", *, data_dir: str = DEFAULT_DATA_DIR) -> str:
    suffix = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    label = str(run_label or "").strip()
    if label:
        return str(Path(data_dir or DEFAULT_DATA_DIR) / label / f"token_check_{suffix}")
    return str(Path(data_dir or DEFAULT_DATA_DIR) / f"token_check_{suffix}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="批量检测 SSO token 是否仍可使用")
    parser.add_argument("--input-file", action="append", default=[], help="输入 token 文件，可重复传入")
    parser.add_argument("--input-glob", action="append", default=[], help="输入 token glob，例如 keys/*/grok.txt")
    parser.add_argument("--run-label", default="", help="按 keys/<run_label>/grok.txt 读取")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="批次根目录，默认 keys")
    parser.add_argument("--output-dir", default="", help="输出目录；留空时自动生成 token_check_<timestamp>")
    parser.add_argument("--check-url", default=DEFAULT_CHECK_URL, help="用于测活的 Grok 登录态接口")
    parser.add_argument("--concurrency", type=int, default=3, help="并发请求数，默认 3")
    parser.add_argument("--interval", type=float, default=1, help="每个并发 worker 两次检测之间的等待秒数，默认 1")
    parser.add_argument("--timeout", type=float, default=15, help="单个请求超时秒数，默认 15")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    tokens = collect_input_tokens(
        input_files=args.input_file,
        input_globs=args.input_glob,
        run_label=args.run_label,
        data_dir=args.data_dir,
    )
    if not tokens:
        print("[Error] 未读取到 token，请检查 --input-file / --input-glob / --run-label。")
        return 2

    output_dir = args.output_dir or default_output_dir(args.run_label, data_dir=args.data_dir)
    print(f"[*] 开始测活: {len(tokens)} 个 token，输出目录: {output_dir}", flush=True)
    print(
        "[*] 测活限速: "
        f"concurrency={args.concurrency} interval={args.interval}s/worker timeout={args.timeout}s",
        flush=True,
    )
    progress_counts = {"alive": 0, "dead": 0, "unknown": 0}
    last_progress_at = 0.0

    def report_progress(completed: int, total: int, result: TokenCheckResult) -> None:
        nonlocal last_progress_at
        progress_counts[result.status] = progress_counts.get(result.status, 0) + 1
        now = time.monotonic()
        should_report = (
            completed == 1
            or completed == total
            or completed % 50 == 0
            or now - last_progress_at >= 10
        )
        if not should_report:
            return
        last_progress_at = now
        print(
            "[*] 测活进度: "
            f"{completed}/{total} "
            f"alive={progress_counts.get('alive', 0)} "
            f"dead={progress_counts.get('dead', 0)} "
            f"unknown={progress_counts.get('unknown', 0)} "
            f"last={result.status}/{result.reason}",
            flush=True,
        )

    results = check_tokens(
        tokens,
        check_url=args.check_url,
        concurrency=args.concurrency,
        interval=args.interval,
        timeout=args.timeout,
        progress_callback=report_progress,
    )
    summary = write_check_outputs(results, output_dir, check_url=args.check_url)
    counts = summary["counts"]
    print(
        "[*] 测活完成: "
        f"alive={counts['alive']} dead={counts['dead']} unknown={counts['unknown']} total={counts['total']}"
    )
    print(f"[*] 测活结果目录: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
