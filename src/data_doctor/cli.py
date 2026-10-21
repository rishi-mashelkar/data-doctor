"""data-doctor command line.

Commands:
  diagnose   read an error (file or stdin), match the bank, print the fix
  triage     scan a log file or directory, find every known failure in it
  search     match free text against the bank
  add        add one entry from a YAML file
  feedback   record whether a suggested fix worked
  seed       load the bundled seed entries into your bank
  stats      show bank size and the fix-worked rate
  version    print the version
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from data_doctor import __version__
from data_doctor.fingerprint import fingerprint
from data_doctor.matcher import rank
from data_doctor.models import Entry, Match
from data_doctor.redact import redact
from data_doctor.seed import load_seed
from data_doctor.store import Bank


def _bank(args: argparse.Namespace) -> Bank:
    return Bank(home=Path(args.home) if args.home else None)


def _resolve_embedder(want: bool):
    """Load the semantic embedder when asked. Return None and tell the user if the
    extra is not installed or a model cannot load. The lexical tier still runs."""
    if not (want or os.environ.get("DATA_DOCTOR_SEMANTIC")):
        return None
    from data_doctor.semantic import available, load_embedder

    if not available():
        print("Semantic match needs the extra. Install it with:\n"
              "  pip install 'data-doctor[semantic]'\nRunning the lexical tier only.",
              file=sys.stderr)
        return None
    embedder = load_embedder()
    if embedder is None:
        print("Could not load the embeddings model (offline, no cached model?). "
              "Running the lexical tier only.", file=sys.stderr)
    return embedder


def _read_input(positional: str | None) -> str:
    if positional and positional != "-":
        return Path(positional).read_text()
    return sys.stdin.read()


def _render(match: Match) -> str:
    e = match.entry
    lines = [
        f"  [{e.id}]  {e.title}",
        f"    engine: {e.engine}" + (f"  ·  applies to: {e.version_range}" if e.version_range else ""),
        f"    cause:  {e.root_cause}" if e.root_cause else "",
        f"    fix:    {e.fix}" if e.fix else "",
        f"    verify: {e.verification}" if e.verification else "",
        f"    source: {e.source}" if e.source else "",
        f"    trust:  {e.status}, confidence {e.confidence}"
        + (f", last verified {e.last_verified[:10]}" if e.last_verified else ""),
        f"    why:    {'; '.join(match.why)}" if match.why else "",
        f"    score:  {match.score}",
    ]
    return "\n".join(ln for ln in lines if ln)


def _diagnose(args: argparse.Namespace) -> int:
    text = _read_input(args.source)
    if not text.strip():
        print("Nothing to diagnose. Pass a file or pipe an error on stdin.", file=sys.stderr)
        return 1
    fp = fingerprint(text)
    engine = args.engine or fp.engine_hint
    embedder = _resolve_embedder(args.semantic)
    with _bank(args) as bank:
        if bank.count() == 0:
            print("The bank is empty. Run `data-doctor seed` to load the starter entries.",
                  file=sys.stderr)
            return 1
        candidates = bank.all(engine=engine if engine != "other" else None)
        if not candidates:
            candidates = bank.all()
        matches = rank(fp, candidates, user_version=args.version or "",
                       limit=args.limit, embedder=embedder)

    if args.json:
        print(json.dumps({
            "engine": engine, "exception": fp.exception,
            "matches": [{"id": m.entry.id, "score": m.score, "why": m.why,
                         "fix": m.entry.fix, "source": m.entry.source,
                         "confidence": m.entry.confidence, "status": m.entry.status}
                        for m in matches],
        }, indent=2))
        return 0

    if not matches:
        print(f"No known match (engine guessed: {engine}, exception: {fp.exception or 'n/a'}).")
        print("If you solve it, add it with `data-doctor add` so it is known next time.")
        return 2
    print(f"Diagnosis  (engine: {engine}, exception: {fp.exception or 'n/a'})\n")
    for m in matches:
        print(_render(m))
        print()
    print("Apply the top fix, then record the result:")
    print(f"  data-doctor feedback {matches[0].entry.id} worked|failed")
    return 0


def _search(args: argparse.Namespace) -> int:
    fp = fingerprint(args.text)
    embedder = _resolve_embedder(args.semantic)
    with _bank(args) as bank:
        matches = rank(fp, bank.all(), user_version="", limit=args.limit,
                       min_score=0.05, embedder=embedder)
    if not matches:
        print("No matches.")
        return 2
    for m in matches:
        print(_render(m))
        print()
    return 0


def _add(args: argparse.Namespace) -> int:
    rows = yaml.safe_load(Path(args.file).read_text())
    rows = rows if isinstance(rows, list) else [rows]
    added = 0
    with _bank(args) as bank:
        for row in rows:
            entry = Entry(**row)
            if entry.scope == "public":
                entry.signature, n1 = redact(entry.signature)
                entry.symptom, n2 = redact(entry.symptom)
                if n1 + n2:
                    print(f"  redacted {n1 + n2} secret(s) from public entry {entry.id}")
            bank.upsert(entry)
            added += 1
    print(f"Added {added} entr{'y' if added == 1 else 'ies'}.")
    return 0


def _feedback(args: argparse.Namespace) -> int:
    worked = args.result == "worked"
    with _bank(args) as bank:
        entry = bank.record_feedback(args.entry_id, worked)
    if entry is None:
        print(f"No entry with id {args.entry_id}.", file=sys.stderr)
        return 1
    print(f"Recorded. {entry.id} is now confidence {entry.confidence} "
          f"({entry.successes} worked, {entry.failures} failed).")
    return 0


def _seed(args: argparse.Namespace) -> int:
    entries = load_seed()
    with _bank(args) as bank:
        n = bank.upsert_many(entries)
        total = bank.count()
    print(f"Loaded {n} seed entries. Bank now holds {total}.")
    return 0


def _stats(args: argparse.Namespace) -> int:
    with _bank(args) as bank:
        s = bank.stats()
    print(f"Bank: {s['total']} entries, {s['verified']} verified.")
    if s["by_engine"]:
        print("By engine: " + ", ".join(f"{k} {v}" for k, v in s["by_engine"].items()))
    rate = s["fix_worked_rate"]
    print(f"Feedback: {s['feedback_count']} recorded, "
          f"fix-worked rate {rate if rate is not None else 'n/a'}.")
    return 0


def _promote(entry, result) -> None:
    """A passed repro marks the entry verified and lifts its confidence floor.

    The floor goes on the prior, not just the current value, so later feedback
    moves confidence from 0.8, not from the authored prior."""
    from data_doctor.models import now_iso

    entry.status = "verified"
    entry.last_verified = now_iso()
    entry.base_confidence = max(entry.base_confidence, 0.8)
    entry.recompute_confidence()


def _verify(args: argparse.Namespace) -> int:
    from data_doctor.verify import run_repro

    if not args.all and not args.entry_id:
        print("Pass an entry id, or --all.", file=sys.stderr)
        return 1
    project = Path(args.project) if args.project else None
    with _bank(args) as bank:
        targets = bank.all() if args.all else [bank.get(args.entry_id)]
        if not args.all and targets[0] is None:
            print(f"No entry with id {args.entry_id}.", file=sys.stderr)
            return 1
        targets = [e for e in targets if e is not None and e.repro]
        if not targets:
            print("Nothing to verify (no entry with a repro here).")
            return 0
        passed = failed = skipped = 0
        for entry in targets:
            result = run_repro(entry.repro, project=project, allow_commands=args.allow_commands)
            mark = {"passed": "✓", "failed": "✗", "skipped": "–"}[result.status]
            print(f"  {mark} {entry.id}: {result.detail}")
            if result.status == "passed":
                _promote(entry, result)
                bank.upsert(entry)
                passed += 1
            elif result.status == "failed":
                failed += 1
            else:
                skipped += 1
    print(f"\nVerified {passed}, failed {failed}, skipped {skipped}.")
    return 1 if failed else 0


def _triage(args: argparse.Namespace) -> int:
    from data_doctor.logs import extract_errors, read_sources

    stdin_text = sys.stdin.read() if (not args.source or args.source == "-") else None
    sources = read_sources(args.source, stdin_text=stdin_text)
    if not any(text.strip() for _, text in sources):
        print("Nothing to triage. Pass a log file, a directory, or pipe a log on stdin.",
              file=sys.stderr)
        return 1
    errors = extract_errors(sources)
    embedder = _resolve_embedder(args.semantic)

    results = []
    with _bank(args) as bank:
        if bank.count() == 0:
            print("The bank is empty. Run `data-doctor seed` to load the starter entries.",
                  file=sys.stderr)
            return 1
        for le in errors:
            engine = args.engine or le.fingerprint.engine_hint
            candidates = bank.all(engine=engine if engine != "other" else None) or bank.all()
            matches = rank(le.fingerprint, candidates, user_version=args.version or "",
                           limit=args.limit, embedder=embedder)
            results.append((le, engine, matches))

    matched = [r for r in results if r[2]]
    unmatched = [r for r in results if not r[2]]

    if args.json:
        print(json.dumps({
            "blocks_found": len(errors),
            "matched": len(matched),
            "unmatched": len(unmatched),
            "failures": [{
                "engine": engine, "count": le.count, "origins": le.origins,
                "exception": le.fingerprint.exception,
                "matches": [{"id": m.entry.id, "score": m.score, "fix": m.entry.fix,
                             "status": m.entry.status, "confidence": m.entry.confidence}
                            for m in matches],
            } for le, engine, matches in results],
        }, indent=2))
        return 0

    if not errors:
        print("No errors found in the logs. Nothing stood out as a failure.")
        return 0

    print(f"Scanned the logs. Found {len(errors)} distinct failure(s): "
          f"{len(matched)} known, {len(unmatched)} not yet in the bank.\n")
    for le, engine, matches in matched:
        where = ", ".join(le.origins)
        seen = f"seen {le.count}x" if le.count > 1 else "seen once"
        print(f"● {engine} failure ({seen} in {where}):")
        snippet, _ = redact(le.block)
        for ln in snippet.splitlines()[:4]:
            print(f"    | {ln}")
        print()
        print(_render(matches[0]))
        print()
    if unmatched:
        print(f"{len(unmatched)} failure(s) are not in the bank yet:")
        for le, engine, _ in unmatched:
            snippet, _ = redact(le.block)
            head = snippet.splitlines()[0] if snippet.splitlines() else ""
            print(f"  - {engine}: {head[:100]}")
        print("Solve one and add it with `data-doctor add` so it is known next time.")
    return 0


def _check(args: argparse.Namespace) -> int:
    from data_doctor.changelog import alerts, detect_versions

    project = Path(args.path)
    versions = detect_versions(project)
    if not versions:
        print(f"No pinned versions found under {project} "
              "(looked in requirements.txt, pyproject.toml, dbt_project.yml).")
        return 0
    with _bank(args) as bank:
        found = alerts(versions, bank.all())
    detected = ", ".join(f"{k} {v}" for k, v in sorted(versions.items()))
    print(f"Detected: {detected}\n")
    if not found:
        print("No known upgrade risks for these versions.")
        return 0
    print(f"{len(found)} upgrade risk(s) apply to your versions:\n")
    for a in found:
        print(f"  [{a.entry.id}]  {a.entry.title}")
        print(f"    on {a.package} {a.version}, applies to {a.entry.version_range}")
        print(f"    {a.entry.fix}")
        print(f"    source: {a.entry.source}\n")
    return 2


def _serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ModuleNotFoundError:
        print("The web UI needs extra packages. Install them with:\n"
              "  pip install 'data-doctor[ui]'", file=sys.stderr)
        return 1
    from data_doctor.server import build_app

    app = build_app(home=Path(args.home) if args.home else None)
    print(f"data-doctor UI on http://{args.host}:{args.port}  (Ctrl-C to stop)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def _version(args: argparse.Namespace) -> int:
    print(f"data-doctor {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="data-doctor", description=__doc__.strip().splitlines()[0])
    p.add_argument("--home", help="Bank directory (default: ~/.data-doctor or $DATA_DOCTOR_HOME)")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("diagnose", help="Match an error against the bank and print the fix")
    d.add_argument("source", nargs="?", help="Error file, or - for stdin (default stdin)")
    d.add_argument("--engine", help="Override the detected engine")
    d.add_argument("--version", help="Your version of the engine, e.g. 1.8.2")
    d.add_argument("--limit", type=int, default=3, help="Max suggestions (default 3)")
    d.add_argument("--semantic", action="store_true",
                   help="Also match by meaning (needs the [semantic] extra)")
    d.add_argument("--json", action="store_true", help="Emit JSON")
    d.set_defaults(func=_diagnose)

    tr = sub.add_parser("triage", help="Scan a log file or directory and find every known failure")
    tr.add_argument("source", nargs="?", help="Log file or directory, or - for stdin (default stdin)")
    tr.add_argument("--engine", help="Force the engine for every failure found")
    tr.add_argument("--version", help="Your version of the engine, e.g. 1.8.2")
    tr.add_argument("--limit", type=int, default=1, help="Max suggestions per failure (default 1)")
    tr.add_argument("--semantic", action="store_true",
                    help="Also match by meaning (needs the [semantic] extra)")
    tr.add_argument("--json", action="store_true", help="Emit JSON")
    tr.set_defaults(func=_triage)

    s = sub.add_parser("search", help="Match free text against the bank")
    s.add_argument("text")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--semantic", action="store_true",
                   help="Also match by meaning (needs the [semantic] extra)")
    s.set_defaults(func=_search)

    a = sub.add_parser("add", help="Add one or more entries from a YAML file")
    a.add_argument("file")
    a.set_defaults(func=_add)

    f = sub.add_parser("feedback", help="Record whether a suggested fix worked")
    f.add_argument("entry_id")
    f.add_argument("result", choices=["worked", "failed"])
    f.set_defaults(func=_feedback)

    se = sub.add_parser("seed", help="Load the bundled seed entries into your bank")
    se.set_defaults(func=_seed)

    st = sub.add_parser("stats", help="Show bank size and the fix-worked rate")
    st.set_defaults(func=_stats)

    ch = sub.add_parser("check", help="Warn about known upgrade risks for a project's versions")
    ch.add_argument("path", nargs="?", default=".", help="Project directory (default .)")
    ch.set_defaults(func=_check)

    vf = sub.add_parser("verify", help="Run an entry's repro to confirm the fix, mark it verified")
    vf.add_argument("entry_id", nargs="?", help="Entry to verify (omit with --all)")
    vf.add_argument("--all", action="store_true", help="Verify every entry that has a repro")
    vf.add_argument("--project", help="Project dir for command-based repros")
    vf.add_argument("--allow-commands", action="store_true", dest="allow_commands",
                    help="Allow repros that run a tool (dbt, spark-submit, …). Off by default.")
    vf.set_defaults(func=_verify)

    sv = sub.add_parser("serve", help="Run the local web UI")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8322)
    sv.set_defaults(func=_serve)

    v = sub.add_parser("version", help="Print the version")
    v.set_defaults(func=_version)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
