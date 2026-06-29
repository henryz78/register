from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class EnvField:
    group: str
    key: str
    default: str
    prompt: str


CONFIG_FIELDS: tuple[EnvField, ...] = (
    EnvField("邮箱模式", "EMAIL_MODE", "tempmail", "邮箱模式 tempmail/custom"),
    EnvField("邮箱模式", "EMAIL_DOMAIN", "", "custom 模式域名，例如 example.com"),
    EnvField("邮箱模式", "EMAIL_API", "http://127.0.0.1:8080", "本地收信服务地址"),
    EnvField("运行目标", "TARGET", "0", "成功 N 个后停止，0 表示不限"),
    EnvField("输出批次", "RUN_LABEL", "", "本次运行批次名，留空自动生成"),
    EnvField("输出批次", "OUTPUT_ROOT", "keys", "批次输出根目录"),
    EnvField("输出批次", "OUTPUT_DIR", "", "指定完整输出目录，留空使用 OUTPUT_ROOT/RUN_LABEL"),
    EnvField("grok2api 推送", "GROK2API_ENDPOINT", "", "grok2api 管理接口地址"),
    EnvField("grok2api 推送", "GROK2API_TOKEN", "", "grok2api app_key"),
    EnvField("grok2api 推送", "GROK2API_APPEND", "1", "1=合并去重，0=覆盖线上号池"),
    EnvField("grok2api 推送", "GROK2API_INSECURE", "0", "1=跳过 TLS 证书校验"),
    EnvField("浏览器并发容量", "PHYSICAL_CAP", "0", "浏览器物理并发，0 表示按本机 CPU/内存自动估算"),
    EnvField("浏览器并发容量", "PHYSICAL_PER_CPU", "2", "自动估算时每个 CPU 核心对应并发"),
    EnvField("浏览器并发容量", "PHYSICAL_MEM_MB", "512", "每个浏览器任务内存预算 MB"),
    EnvField("浏览器并发容量", "MIN_FREE_MEM_MB", "500", "自动估算时保留内存 MB"),
    EnvField("浏览器并发容量", "CAPACITY_PROFILE", "", "可选离线容量 profile JSON 路径"),
    EnvField("缓冲容量", "T_SLOT_CAP", "8", "token 库存缓冲容量"),
    EnvField("缓冲容量", "Q_SLOT_CAP", "8", "验证码库存缓冲容量"),
    EnvField("缓冲容量", "Q_PENDING_CAP", "12", "外部在途验证码请求上限"),
    EnvField("Worker 数量", "S_WORKERS", "0", "token Worker 数量，0 表示自动派生"),
    EnvField("Worker 数量", "P_WORKERS", "0", "验证码 Worker 数量，0 表示自动派生"),
    EnvField("Worker 数量", "C_WORKERS", "0", "注册 Worker 数量，0 表示自动派生"),
    EnvField("资源有效期", "T_MAX_AGE", "300", "token 最大年龄秒"),
    EnvField("资源有效期", "Q_MAX_AGE", "120", "验证码最大年龄秒"),
    EnvField("阶段超时", "P_REQUEST_TIMEOUT", "95", "等待验证码返回超时秒"),
    EnvField("阶段超时", "C_CONSUME_TIMEOUT", "60", "最终提交阶段超时秒"),
    EnvField("局部门控和批量发送", "T_TARGET", "4", "token 缓冲目标"),
    EnvField("局部门控和批量发送", "Q_TARGET", "4", "验证码缓冲目标"),
    EnvField("局部门控和批量发送", "T_HIGH_WATER", "", "token 生产高水位，留空自动派生"),
    EnvField("局部门控和批量发送", "T_LOW_WATER", "", "token 生产恢复低水位，留空自动派生"),
    EnvField("局部门控和批量发送", "Q_HIGH_WATER", "", "验证码生产高水位，留空自动派生"),
    EnvField("局部门控和批量发送", "Q_LOW_WATER", "", "验证码生产恢复低水位，留空自动派生"),
    EnvField("局部门控和批量发送", "P_BATCH_MAX", "4", "单个发送页面最多发送的验证码请求数"),
    EnvField("局部门控和批量发送", "P_SEND_CAP", "0", "发送页面并发限制，0 表示不额外限制"),
    EnvField("页面和 token 获取", "SOLVER_REUSE", "1", "1=复用 token 页面，0=关闭"),
    EnvField("页面和 token 获取", "MAX_SOLVER_REUSE", "25", "单个 token 页面最大复用次数"),
    EnvField("页面和 token 获取", "SOLVER_INITIAL_WAIT_MS", "500", "token 注入后的首次等待毫秒"),
    EnvField("页面和 token 获取", "SOLVER_POLL_INTERVAL_MS", "500", "token 轮询间隔毫秒"),
    EnvField("页面和 token 获取", "SOLVER_POLL_ATTEMPTS", "100", "token 最大轮询次数"),
    EnvField("页面和 token 获取", "SOLVER_FAST_CLICK", "1", "1=启用快速点击策略，0=关闭"),
    EnvField("页面和 token 获取", "SOLVER_MOUSE_CLICK_RETRIES", "3", "验证框中心点击次数，0=关闭"),
    EnvField("页面和 token 获取", "SOLVER_MOUSE_CLICK_INTERVAL_MS", "600", "验证框中心点击间隔毫秒"),
    EnvField("页面和 token 获取", "SOLVER_TIMELINE_TRACE", "0", "1=输出 solver 时间线诊断"),
    EnvField("页面和 token 获取", "SOLVER_TIMELINE_SAMPLE", "8", "solver 时间线最多输出样本数"),
    EnvField("页面和 token 获取", "PAGE_GOTO_WAIT_UNTIL", "domcontentloaded", "页面导航等待策略"),
    EnvField("页面和 token 获取", "PAGE_POST_WAIT_MS", "500", "页面导航后的短等待毫秒"),
    EnvField("性能开关", "PAGE_BLOCK_STATIC_ASSETS", "0", "1=阻断部分静态资源"),
    EnvField("性能开关", "C_HOT_PAGE_POOL", "0", "1=复用消费阶段页面"),
    EnvField("性能开关", "C_HOT_PAGE_POOL_SIZE", "0", "热页池大小，0 表示按并发派生"),
    EnvField("性能开关", "C_SET_COOKIE_VIA_REQUEST", "0", "1=用 request 访问 set-cookie URL"),
    EnvField("代理", "HTTP_PROXY", "", "HTTP 代理地址，留空关闭"),
    EnvField("代理", "HTTPS_PROXY", "", "HTTPS 代理地址，留空关闭"),
)


def default_values() -> dict[str, str]:
    return {field.key: field.default for field in CONFIG_FIELDS}


def _clean_value(value: str) -> str:
    return str(value).replace("\r", "").replace("\n", "").strip()


def _ask(
    input_func: Callable[[str], str],
    prompt: str,
    default: str,
) -> str:
    try:
        answer = input_func(f"{prompt} [{default}]: ")
    except EOFError:
        return default
    value = _clean_value(answer)
    return value if value else default


def collect_custom_values(
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> dict[str, str]:
    values: dict[str, str] = {}
    current_group = ""
    for field in CONFIG_FIELDS:
        if field.group != current_group:
            current_group = field.group
            output_func("")
            output_func(f"## {current_group}")
        values[field.key] = _ask(input_func, f"{field.key} {field.prompt}", field.default)
    return values


def collect_values(
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> dict[str, str]:
    output_func("选择配置方式:")
    output_func("  [1] 使用默认配置生成 .env")
    output_func("  [2] 逐项自定义全部配置")
    try:
        mode = _clean_value(input_func("输入 1 或 2 [1]: ")) or "1"
    except EOFError:
        mode = "1"
    if mode == "2":
        return collect_custom_values(input_func=input_func, output_func=output_func)
    return default_values()


def render_env(values: dict[str, str]) -> str:
    resolved = default_values()
    resolved.update({key: _clean_value(value) for key, value in values.items()})
    lines = [
        "# grok-free-register 正式配置",
        "# 由 bash start.sh 初始化生成；修改后执行 bash run.sh 生效。",
    ]
    current_group = ""
    for field in CONFIG_FIELDS:
        if field.group != current_group:
            current_group = field.group
            lines.extend(["", f"# {current_group}"])
        lines.append(f"{field.key}={resolved[field.key]}")
    lines.append("")
    return "\n".join(lines)


def write_env(
    path: str | Path,
    *,
    force: bool = False,
    values: dict[str, str] | None = None,
) -> bool:
    env_path = Path(path)
    if env_path.exists() and not force:
        return False
    env_path.write_text(render_env(values or default_values()), encoding="utf-8")
    return True


def main(
    argv: Iterable[str] | None = None,
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(description="初始化 grok-free-register .env 配置")
    parser.add_argument("--output", default=".env", help="输出 .env 路径")
    parser.add_argument("--force", action="store_true", help="覆盖已有 .env")
    parser.add_argument("--default", action="store_true", help="直接写入默认配置")
    parser.add_argument("--custom", action="store_true", help="逐项自定义全部配置")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.default and args.custom:
        parser.error("--default 和 --custom 只能选择一个")

    path = Path(args.output)
    if path.exists() and not args.force:
        output_func("[*] 已存在 .env，保留当前配置。需要重置请执行: bash start.sh --init")
        return 0

    if args.default:
        values = default_values()
    elif args.custom:
        values = collect_custom_values(input_func=input_func, output_func=output_func)
    else:
        values = collect_values(input_func=input_func, output_func=output_func)

    write_env(path, force=True, values=values)
    output_func(f"[*] 已写入 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
