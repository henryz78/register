from __future__ import annotations

import os
import re
import time
from pathlib import Path


DEFAULT_OUTPUT_ROOT = "keys"


def make_run_label(now: float | None = None, pid: int | None = None) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(now or time.time()))
    return f"run_{ts}_{pid or os.getpid()}"


def safe_run_label(label: str | None = None) -> str:
    text = str(label or "").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return text or make_run_label()


def batch_dir(run_label: str, data_dir: str | os.PathLike = DEFAULT_OUTPUT_ROOT) -> Path:
    return Path(str(data_dir or DEFAULT_OUTPUT_ROOT)) / safe_run_label(run_label)


def grok_path(run_label: str, data_dir: str | os.PathLike = DEFAULT_OUTPUT_ROOT) -> Path:
    return batch_dir(run_label, data_dir) / "grok.txt"


def merged_tokens_path(run_label: str, data_dir: str | os.PathLike = DEFAULT_OUTPUT_ROOT) -> Path:
    return batch_dir(run_label, data_dir) / "merged_tokens.txt"
