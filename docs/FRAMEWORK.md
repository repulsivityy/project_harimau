# Project Harimau — Documentation Framework

Rules for maintaining `implementation_plan_v2.md`.

---

## Structure

- **Pillars** — stable system domains (e.g. "Persistence & State Management"). Don't create pillars based on time, temporary efforts, or individual tools. Assign a single primary owner when features span multiple pillars.
- **Milestones** — capability snapshots within a pillar. Descriptive names first; numbers are secondary.
- **Tasks** — atomic checkboxes (`[x]` / `[ ]`). Keep specific and actionable. Add timestamps for significant changes.

---

## Status Indicators

| Symbol | Meaning |
|--------|---------|
| ✅ | Completed |
| 🚧 / [/] | In Progress |
| ⏳ | Planned |
| ❌ | Blocked |
| 🧪 | Experimental |
| [LEGACY] | Superseded but preserved |
| [ABANDONED] | Dropped — include a reason |

---

## Decision Rules

| Change type | Action |
|---|---|
| Bug fix / small improvement | Add task to existing milestone |
| Major capability evolution | Create new milestone in same pillar |
| Refactor / rewrite | New milestone + mark old as `[LEGACY]` |
| Dropped approach | Mark as `[ABANDONED]` with explanation — **never delete** |
| Entirely new system domain | Create new pillar |

---

## Golden Rules

- **Preserve history** — never overwrite or delete milestones.
- **Avoid fragmentation** — don't create milestones for minor tweaks.
- **Milestones are not timelines** — they represent capability states, not phases.
- **Single owner** — one pillar owns each feature; no duplication.
- **Attach learnings** — add a "Challenges & Learnings" note when something non-obvious was discovered.
