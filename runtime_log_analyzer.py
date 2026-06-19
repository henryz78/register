"""
Parse real runtime monitor logs from both CSP and legacy state-machine runs.

The analyzer is intentionally read-only. It does not tune parameters or modify
runtime state; it only turns production logs into comparable stage rates.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


_CSP_RE = re.compile(
    r"^\[\*\] T:(?P<t>\d+) Q:(?P<q>\d+) phys:(?P<phys>\d+) "
    r"(?:p_send:(?P<p_send>\d+) )?t_slot:(?P<t_slot>\d+) q_slot:(?P<q_slot>\d+) q_pend:(?P<q_pend>\d+)"
    r"(?P<rest>.*)rate:(?P<rate>[0-9.]+)/min #(?P<ok>\d+)"
)

_STATE_RE = re.compile(
    r"^\[\*\] slots:(?P<slots>\d+)/(?P<max_slots>\d+) act:(?P<active>\d+) "
    r"cpu:(?P<cpu>[0-9.]+)% avg:(?P<cpu_avg>[0-9.]+)%/(?P<cpu_target>[0-9.]+) "
    r"mem:(?P<mem>\d+)M T:(?P<t>\d+) Q:(?P<q>\d+) "
    r"sent:(?P<q_sent>\d+) got:(?P<q_ret>\d+)\((?P<q_hit>[0-9.]+)%\) "
    r"rate:(?P<rate>[0-9.]+)/min #(?P<ok>\d+)"
)


@dataclass(frozen=True)
class MonitorRow:
    kind: str
    t: int
    q: int
    ok: int
    rate: float
    t_prod: int | None = None
    q_sent: int | None = None
    q_ret: int | None = None
    q_adm: int | None = None
    pair: int | None = None
    fail: int | None = None
    solver_goto: float | None = None
    solver_inject: float | None = None
    solver_initial: float | None = None
    solver_click: float | None = None
    solver_wait: float | None = None
    solver_reuse: float | None = None
    solver_visible: float | None = None
    slots: int | None = None
    max_slots: int | None = None
    active: int | None = None

    @property
    def elapsed_min(self) -> float | None:
        if self.ok <= 0 or self.rate <= 0:
            return None
        return self.ok / self.rate


def _int_field(rest: str, name: str) -> int | None:
    match = re.search(rf"\b{name}:(\d+)", rest)
    return int(match.group(1)) if match else None


def _float_field(rest: str, name: str) -> float | None:
    match = re.search(rf"\b{name}:([0-9.]+)", rest)
    return float(match.group(1)) if match else None


def parse_monitor_lines(text_or_lines: str | Iterable[str]) -> list[MonitorRow]:
    if isinstance(text_or_lines, str):
        lines = text_or_lines.splitlines()
    else:
        lines = list(text_or_lines)

    rows: list[MonitorRow] = []
    for line in lines:
        csp = _CSP_RE.match(line)
        if csp:
            rest = csp.group("rest")
            rows.append(
                MonitorRow(
                    kind="csp",
                    t=int(csp.group("t")),
                    q=int(csp.group("q")),
                    ok=int(csp.group("ok")),
                    rate=float(csp.group("rate")),
                    t_prod=_int_field(rest, "t_prod"),
                    q_sent=_int_field(rest, "q_sent"),
                    q_ret=_int_field(rest, "q_ret"),
                    q_adm=_int_field(rest, "q_adm"),
                    pair=_int_field(rest, "pair"),
                    fail=_int_field(rest, "fail"),
                    solver_goto=_float_field(rest, "solver_goto"),
                    solver_inject=_float_field(rest, "solver_inject"),
                    solver_initial=_float_field(rest, "solver_initial"),
                    solver_click=_float_field(rest, "solver_click"),
                    solver_wait=_float_field(rest, "solver_wait"),
                    solver_reuse=_float_field(rest, "solver_reuse"),
                    solver_visible=_float_field(rest, "solver_visible"),
                )
            )
            continue

        state = _STATE_RE.match(line)
        if state:
            rows.append(
                MonitorRow(
                    kind="state_machine",
                    t=int(state.group("t")),
                    q=int(state.group("q")),
                    ok=int(state.group("ok")),
                    rate=float(state.group("rate")),
                    q_sent=int(state.group("q_sent")),
                    q_ret=int(state.group("q_ret")),
                    slots=int(state.group("slots")),
                    max_slots=int(state.group("max_slots")),
                    active=int(state.group("active")),
                )
            )
    return rows


def _rate_delta(rows: list[MonitorRow], attr: str) -> float | None:
    candidates = [r for r in rows if r.elapsed_min is not None and getattr(r, attr) is not None]
    if len(candidates) < 2:
        return None
    first = candidates[0]
    last = candidates[-1]
    dt = (last.elapsed_min or 0) - (first.elapsed_min or 0)
    if dt <= 0:
        return None
    return (getattr(last, attr) - getattr(first, attr)) / dt


def summarize_monitor_rows(rows: list[MonitorRow], recent_count: int = 6) -> dict[str, float | int | str | None]:
    if not rows:
        return {"rows": 0}

    last = rows[-1]
    recent = rows[-recent_count:]
    summary: dict[str, float | int | str | None] = {
        "rows": len(rows),
        "kind": last.kind,
        "last_ok": last.ok,
        "last_cumulative_rate": last.rate,
        "last_q_minus_t": last.q - last.t,
        "last_q_return_minus_t_prod": (
            last.q_ret - last.t_prod
            if last.q_ret is not None and last.t_prod is not None
            else None
        ),
        "last_slots": last.slots,
        "last_t_prod": last.t_prod,
        "last_q_ret": last.q_ret,
        "last_q_adm": last.q_adm,
        "last_pair": last.pair,
        "last_fail": last.fail,
        "last_solver_goto": last.solver_goto,
        "last_solver_inject": last.solver_inject,
        "last_solver_initial": last.solver_initial,
        "last_solver_click": last.solver_click,
        "last_solver_wait": last.solver_wait,
        "last_solver_reuse": last.solver_reuse,
        "last_solver_visible": last.solver_visible,
        "recent_ok_per_min": _rate_delta(recent, "ok"),
        "recent_t_prod_per_min": _rate_delta(recent, "t_prod"),
        "recent_q_ret_per_min": _rate_delta(recent, "q_ret"),
        "recent_pair_per_min": _rate_delta(recent, "pair"),
    }
    return summary


def analyze_text(text: str) -> dict[str, float | int | str | None]:
    return summarize_monitor_rows(parse_monitor_lines(text))
