# data-doctor roadmap

## North star

A data engineer never debugs the same failure twice.

data-doctor catches a break, explains the real cause, proves the fix against a repro,
and with your approval applies it. Every fix flows back to the bank, so the same
failure never bites you or the community again. The far goal is prevention: a
warning before the upgrade or the schema change breaks you. The number that tracks
it is time-to-recovery trending to near zero.

## Phases

Shipped so far: Phase 1, plus verified fixes (a sandboxed repro runner), proactive
changelog alerts, and a local web UI. Still ahead in Phase 2: the semantic match
tier, and repro coverage for the heavier engines through the command verifier.

### Phase 1 - diagnose and suggest (v1, now)
- Fingerprint an error, match the bank, suggest the exact fix with provenance.
- Local offline match. Airflow, dbt, Spark, Iceberg.
- Feedback loop and a fix-worked rate.
- Private and shared entries, with redaction before sharing.

### Phase 2 - verified fixes and prevention
- Verified fixes. Reproduce the error in a tiny local case and confirm the fix
  passes before it is shown. For example a dbt parse and compile, a DuckDB run, a
  small Iceberg table, or a minimal local Spark session.
- Proactive changelog alerts. Read the versions in your lockfiles and dbt
  packages and warn before an upgrade is likely to break you.
- A semantic match tier for the fuzzy cases the local pass misses.

### Phase 3 - in the flow
- Change context from JIRA and chat, so a break is tied to the story, ticket, or
  deploy that caused it. This is what makes the version-aware root cause fast.
- Sit in the incident path. Ingest alerts from a pager and respond in a channel.
- Read logs directly from the common log sources, to move from reactive to
  proactive and catch a break before anyone pastes it.

### Phase 4 - with approval, it fixes
- Apply the fix behind your approval and a dry run. Suggest first stays the
  default. Nothing runs on your systems without a yes.
- Then prevent. Warn ahead of the change that would have broken you.

## Design principles

- Version-aware first. Tie the error to a recent version or changelog change.
  This is the core advantage over a general model.
- Local and fast. The common case matches offline in milliseconds. A model is a
  fallback, not the default.
- Provenance on everything. Source, version, confidence, last verified. No blind
  "try this".
- Suggest, do not act. The tool proposes. You approve. This holds until a repro
  and an approval gate make auto-fix safe.
- Secrets never leave. Shared entries are redacted first.

## What data-doctor is not

Not a general coding agent. Not an incident bot. The edge is a curated,
version-aware data-engineering bank with an instant local match and verified
fixes. Keep that edge or it is just another error helper.
