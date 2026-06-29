from __future__ import annotations

import json
import os
from glob import glob
from typing import Iterable, List

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def parse_json_response(resp):
    text = (getattr(resp, "text", "") or "").strip()
    content_type = str(getattr(resp, "headers", {}).get("Content-Type", "")).lower()
    if "application/json" in content_type or text.startswith("{") or text.startswith("["):
        try:
            return True, resp.json()
        except Exception:
            return False, text
    return False, text


def normalize_token_list(value) -> List[str]:
    if not isinstance(value, list):
        return []

    normalized: List[str] = []
    for item in value:
        token = ""
        if isinstance(item, dict):
            for key in ("token", "value", "sso", "ssoToken"):
                if item.get(key):
                    token = str(item[key]).strip()
                    break
        elif item:
            token = str(item).strip()

        if token:
            normalized.append(token)
    return normalized


def extract_existing_tokens(payload) -> List[str]:
    def walk(node):
        if isinstance(node, dict):
            for key in ("ssoBasic", "ssobasic", "sso_basic"):
                tokens = normalize_token_list(node.get(key))
                if tokens:
                    return tokens

            for key in ("tokens", "data", "result", "payload"):
                if key in node:
                    tokens = walk(node.get(key))
                    if tokens:
                        return tokens

            for value in node.values():
                tokens = walk(value)
                if tokens:
                    return tokens

        if isinstance(node, list):
            if node and all(isinstance(item, (str, dict)) for item in node):
                tokens = normalize_token_list(node)
                if tokens:
                    return tokens

            for item in node:
                tokens = walk(item)
                if tokens:
                    return tokens

        return []

    return walk(payload)


def collect_tokens_from_files(paths: Iterable[str]) -> List[str]:
    merged: List[str] = []
    seen = set()
    for path in paths:
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                token = line.strip()
                if not token or token in seen:
                    continue
                seen.add(token)
                merged.append(token)
    return merged


def collect_tokens_from_glob(pattern: str) -> List[str]:
    return collect_tokens_from_files(sorted(glob(pattern)))


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def resolve_api_config(
    *,
    endpoint: str | None = None,
    api_token: str | None = None,
    append: bool | None = None,
    verify_tls: bool | None = None,
) -> dict:
    return {
        "endpoint": str(
            endpoint
            or os.environ.get("GROK2API_ENDPOINT")
            or os.environ.get("API_ENDPOINT")
            or ""
        ).strip(),
        "api_token": str(
            api_token
            or os.environ.get("GROK2API_TOKEN")
            or os.environ.get("API_TOKEN")
            or ""
        ).strip(),
        "append": _env_bool("GROK2API_APPEND", True) if append is None else bool(append),
        "verify_tls": (
            not _env_bool("GROK2API_INSECURE", False)
            if verify_tls is None
            else bool(verify_tls)
        ),
    }


def _dedupe(tokens: Iterable[str]) -> list[str]:
    seen = set()
    deduped = []
    for token in tokens:
        value = str(token or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def push_sso_to_api(
    new_tokens: list,
    *,
    endpoint: str | None = None,
    api_token: str | None = None,
    append: bool | None = None,
    verify_tls: bool | None = None,
    request_get=None,
    request_post=None,
) -> dict:
    config = resolve_api_config(
        endpoint=endpoint,
        api_token=api_token,
        append=append,
        verify_tls=verify_tls,
    )
    endpoint = config["endpoint"]
    api_token = config["api_token"]
    append_mode = config["append"]
    verify_tls = config["verify_tls"]
    if not endpoint or not api_token:
        return {"pushed": False, "reason": "missing_config", "count": 0}

    tokens_to_push = _dedupe(new_tokens)
    if not tokens_to_push:
        return {"pushed": False, "reason": "empty_tokens", "count": 0}

    if request_get is None or request_post is None:
        import requests
        request_get = request_get or requests.get
        request_post = request_post or requests.post

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    existing_tokens: list[str] = []
    if append_mode:
        try:
            get_resp = request_get(endpoint, headers=headers, timeout=15, verify=verify_tls)
        except Exception as exc:
            return {"pushed": False, "reason": f"get_exception:{type(exc).__name__}", "count": 0}
        if getattr(get_resp, "status_code", 0) != 200:
            return {
                "pushed": False,
                "reason": f"get_http_{getattr(get_resp, 'status_code', 0)}",
                "count": 0,
            }
        ok, data = parse_json_response(get_resp)
        if not ok:
            return {"pushed": False, "reason": "get_non_json", "count": 0}
        existing_tokens = extract_existing_tokens(data)
        tokens_to_push = _dedupe(existing_tokens + tokens_to_push)

    try:
        resp = request_post(
            endpoint,
            json={"ssoBasic": tokens_to_push},
            headers=headers,
            timeout=60,
            verify=verify_tls,
        )
    except Exception as exc:
        return {"pushed": False, "reason": f"post_exception:{type(exc).__name__}", "count": 0}

    if getattr(resp, "status_code", 0) != 200:
        return {
            "pushed": False,
            "reason": f"post_http_{getattr(resp, 'status_code', 0)}",
            "count": 0,
        }

    return {
        "pushed": True,
        "reason": "ok",
        "count": len(tokens_to_push),
        "new_count": len(_dedupe(new_tokens)),
        "existing_count": len(existing_tokens),
        "endpoint": endpoint,
    }
