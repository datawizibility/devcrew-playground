# Plan 1 Handoff — Dev Crew Instructions

**Date:** 2026-11-02
**Plan:** `docs/superpowers/plans/2026-11-02-plan1-foundation.md`
**Spec:** `docs/superpowers/specs/2026-11-02-ap-automation-saas-design.md`
**Reviewer:** OpenWork agent (verification checklist below)

---

## Ground Rules for the Dev Crew

1. **Read the spec first** (Section 4 Architecture + Global Constraints in the plan header), then execute Plan 1 tasks **in order, 1 → 8**.
2. **Follow TDD exactly as written**: write the failing test, run it, see it fail, implement, run again, see it pass, commit. Do not batch tasks.
3. **One commit per task**, conventional commit messages as given in each task's final step.
4. **Do not redesign.** If a step's code doesn't work as written, fix minimally and note the deviation in the commit message body (`Deviation: <reason>`).
5. **Never commit secrets.** `.env` is gitignored; use `.env.example` values for dev.
6. **Tests run against `smartap_test` only** (auto-created/dropped). Docker `db` service must be up.
7. If blocked >30 minutes on a step, stop, document the blocker in `BLOCKERS.md` (create at repo root), and move to the next independent task if possible.

## Progress Reporting

Maintain a checkbox log in `PROGRESS.md` at repo root:

```markdown
- [x] Task 1 — commit <sha>
- [ ] Task 2 — in progress
```

Update after every task. The reviewer reads this first.

---

## Reviewer Verification Checklist (run per completed task)

The reviewer (agent or tech lead) runs these after each task lands. A task is **accepted** only when its check passes on a clean checkout.

### Task 1 — Scaffold
```bash
git log --oneline -1                      # conventional commit message
uv run pytest tests/test_health.py -v     # PASS
docker compose ps                         # db healthy, redis running
```

### Task 2 — Settings
```bash
uv run pytest tests/test_config.py -v     # PASS (2 tests)
```

### Task 3 — DB + Alembic
```bash
uv run pytest tests/test_db.py -v         # PASS (2 tests)
ls alembic/versions/                      # exists
```

### Task 4 — Tenancy + RLS  ⚠️ critical gate
```bash
uv run pytest tests/test_tenancy.py -v    # PASS — cross-tenant read MUST be blocked
# Manual spot-check (optional but recommended):
docker compose exec db psql -U smartap -d smartap_test -c "\d users"
# Expect: rowsecurity=true, policy tenant_isolation present
```
**Reject if:** RLS test passes but `FORCE ROW LEVEL SECURITY` is missing, or the no-tenant case returns rows.

### Task 5 — Auth
```bash
uv run pytest tests/test_auth.py -v       # PASS (3 tests)
# Manual: bootstrap + login via curl, confirm /auth/me returns claims
```

### Task 6 — Vendors
```bash
uv run pytest tests/test_vendors.py -v    # PASS
# Manual: create vendor as tenant A, list as tenant B → must be empty
```

### Task 7 — Audit  ⚠️ critical gate
```bash
uv run pytest tests/test_audit.py -v      # PASS — UPDATE/DELETE must raise
# Manual spot-check:
docker compose exec db psql -U smartap -d smartap_test -c "\d audit_events"
# Expect: trigger audit_events_no_update_delete present
```
**Reject if:** trigger missing, or `/audit-events` reachable by non-admin role.

### Task 8 — README + full suite
```bash
uv run pytest -v                          # ALL PASS, zero skips, zero warnings-as-errors
```

### Final acceptance (whole plan)
```bash
git log --oneline        # 8+ conventional commits, one per task
uv run pytest            # green from clean checkout
docker compose down -v && docker compose up -d db redis && uv run alembic upgrade head && uv run pytest
# ^ full cold-start reproducibility: fresh volumes, fresh migrations, green suite
```

---

## Acceptance Criteria Summary

| # | Criterion |
|---|---|
| A1 | All 8 tasks committed in order with conventional messages |
| A2 | Full pytest suite green from a cold start (fresh DB, fresh migrations) |
| A3 | RLS enforced with FORCE; cross-tenant reads return empty (tested) |
| A4 | audit_events immutable via DB trigger (tested) |
| A5 | No secrets in git history (`git log -p -- .env` empty) |
| A6 | Deviations documented in commit bodies; BLOCKERS.md explains anything unfinished |
