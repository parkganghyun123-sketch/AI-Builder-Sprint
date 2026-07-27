# PairSign Agent Instructions

## Project Mission

PairSign helps first-time part-time workers understand, clarify, confirm, and
sign employment contracts without presenting automated results as legal advice.

## Instruction Order

Every agent must read this file first and then its assigned role file.

When project documents disagree, use this order:

1. `AGENTS.md` for shared safety and collaboration rules
2. `KB.md` for verified legal facts, wording limits, and source status
3. `README.md` for current product scope and priorities
4. `docs/챗봇_설계.md` for the grounded chatbot design
5. Other files in `docs/` for background decisions and unresolved research

Do not silently choose between conflicting documents. Preserve the safer
behavior and report the conflict to the Lead Agent.

## Agent Structure

- Lead Agent: `agents/lead.md`
- Contract Safety Reviewer: `agents/contract-safety.md`
- Implementation Engineer: `agents/implementation.md`
- QA and Demo Reviewer: `agents/qa-demo.md`

The Lead Agent must explicitly tell every specialist to read `AGENTS.md` and
the relevant role file completely.

## Shared Priorities

1. Privacy and user safety
2. Official-source accuracy
3. Working end-to-end MVP
4. Deterministic and explainable results
5. AI usage evidence
6. Maintainability
7. Visual polish

## Shared Rules

- Do not make definitive legal judgments or present PairSign as legal counsel.
- Do not invent facts missing from a contract, user input, or verified source.
- Ground legal explanations and constants in `KB.md`.
- Keep legal calculations deterministic; do not let an LLM decide or calculate.
- Distinguish contract facts, legal standards, calculations, and limitations.
- Display the applicable reference date for time-sensitive standards.
- Treat unsupported or disputed situations as `OUT_OF_SCOPE`.
- Do not expose API keys, contract contents, or personal information in logs.
- Use synthetic contracts and synthetic identities in tests and demos.
- Do not edit files outside the scope assigned by the Lead Agent.
- Do not claim an unexecuted check passed.
- Do not hide mocked, unavailable, or unverified integrations.
- Do not commit `.env` files, credentials, real contracts, or personal data.

## File Ownership

- The Lead Agent assigns explicit file ownership before parallel work.
- Two agents must not edit the same file concurrently.
- Contract Safety and QA reviewers are read-only unless the Lead Agent assigns
  exact files to edit.
- A reviewer who implements a fix must not be the only reviewer of that fix.

## Required Review Format

Every review must return:

```text
Status: PASS | PASS_WITH_CONCERNS | BLOCKED
Files reviewed:
Checks performed:
Findings:
Required changes:
Evidence:
```

Use the statuses as follows:

- `PASS`: no blocking or material unresolved concern
- `PASS_WITH_CONCERNS`: usable, but named risks or follow-up work remain
- `BLOCKED`: unsafe, unverifiable, broken, or missing a required control

The Lead Agent must not complete a task while a required review is `BLOCKED`.

## Minimum Completion Evidence

Report only checks that exist and were run. For application changes, the target
evidence is typecheck, lint, tests, production build, and the relevant demo
flow. For documentation-only changes, check links, internal consistency,
formatting, and `git diff --check`.
