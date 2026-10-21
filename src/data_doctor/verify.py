"""Run a reproduction to confirm a fix actually works.

A verified fix is worth far more than a guessed one. An entry can carry a repro
spec that a built-in verifier runs. We never execute arbitrary shell from an entry.
Only vetted verifiers run, and the one that shells out to a tool is off unless the
user opts in.

Verifiers:
- duckdb_sql: runs in a fresh in-memory DuckDB with external access turned off, so
  it cannot touch the filesystem or network. It confirms the failing SQL really
  raises, then that the fixed SQL runs clean. Safe to run by default.
- command: runs an allowlisted tool (dbt, spark-submit, pyspark, python) in a
  project directory. Off by default. The caller must allow it, and the tool must
  be on PATH or the result is skipped. It can run a failing command first, to
  reproduce the error, then the fixed command, like the duckdb_sql verifier.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["COMMAND_ALLOWLIST", "VerifyResult", "run_repro"]

COMMAND_ALLOWLIST = {"dbt", "spark-submit", "pyspark", "python", "python3", "uv"}


@dataclass
class VerifyResult:
    status: str  # "passed" | "failed" | "skipped"
    detail: str = ""


def run_repro(repro: dict | None, *, project: Path | None = None,
              allow_commands: bool = False) -> VerifyResult:
    if not repro:
        return VerifyResult("skipped", "no repro to run")
    verifier = repro.get("verifier")
    if verifier == "duckdb_sql":
        return _duckdb_sql(repro)
    if verifier == "command":
        return _command(repro, project=project, allow_commands=allow_commands)
    return VerifyResult("skipped", f"unknown verifier: {verifier}")


def _duckdb_sql(repro: dict) -> VerifyResult:
    import duckdb

    con = duckdb.connect()
    try:
        # Sandbox: no files, no network. The repro is pure in-memory SQL.
        con.execute("SET enable_external_access=false")
        for stmt in repro.get("setup", []):
            con.execute(stmt)

        failing = repro.get("failing")
        if failing:
            try:
                con.execute(failing)
            except Exception as exc:  # noqa: BLE001 - any raise is the reproduction
                want = (repro.get("expect_error") or "").lower()
                if want and want not in str(exc).lower():
                    return VerifyResult("failed",
                                        f"raised, but not the expected error: {exc}")
            else:
                return VerifyResult("failed", "the failing SQL did not raise")

        fixed = repro.get("fixed")
        if fixed:
            try:
                con.execute(fixed)
            except Exception as exc:  # noqa: BLE001 - report any failure of the fix
                return VerifyResult("failed", f"the fixed SQL still fails: {exc}")
        return VerifyResult("passed", "reproduced the error; the fix runs clean")
    finally:
        con.close()


def _command(repro: dict, *, project: Path | None, allow_commands: bool) -> VerifyResult:
    if not allow_commands:
        return VerifyResult("skipped", "command verifier needs --allow-commands")
    tool = repro.get("tool", "")
    if tool not in COMMAND_ALLOWLIST:
        return VerifyResult("skipped", f"tool not allowlisted: {tool}")
    if shutil.which(tool) is None:
        return VerifyResult("skipped", f"{tool} is not on PATH")
    cwd = str(project) if repro.get("cwd") == "project" and project else None
    timeout = int(repro.get("timeout", 120))

    def run(cmd_args: list) -> subprocess.CompletedProcess:
        return subprocess.run([tool, *[str(a) for a in cmd_args]], cwd=cwd,
                              capture_output=True, text=True, timeout=timeout, check=False)

    try:
        # An optional reproduce step: the failing command must fail first, so a
        # pass means the error was real and the fix resolves it.
        failing = repro.get("failing")
        if failing:
            fail_proc = run(failing)
            if fail_proc.returncode == 0:
                return VerifyResult("failed", f"the failing {tool} command did not fail")
        proc = run(repro.get("args", []))
    except subprocess.TimeoutExpired:
        return VerifyResult("failed", "the command timed out")

    expect_exit = int(repro.get("expect_exit", 0))
    if proc.returncode == expect_exit:
        detail = ("reproduced the error; the fix runs clean" if repro.get("failing")
                  else f"{tool} exited {proc.returncode} as expected")
        return VerifyResult("passed", detail)
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or [""]
    return VerifyResult("failed", f"{tool} exited {proc.returncode}: {tail[0]}")
