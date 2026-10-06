# ADR 0001: Portable factory, configured before the application

- Status: Accepted
- Date: 2026-10-06

## Context

Reuse the existing factory contracts for a Python/FastAPI project without repeating document generation. The application architecture and plan already exist outside this setup task. A working integration lifecycle should precede application scaffolding and stack-specific verification.

## Decision

| Layer | Role |
|---|---|
| Slack `#librag`, `#librag-log` | Human requests, threaded feedback, approvals and logs. |
| Linear team `LibRag` | Workflow state and audit records. |
| Repository | Reused docs, `AGENTS.md`, stage definitions and skills. |
| Cursor cloud agents and automations | Stage execution; concrete capabilities are probed during setup. |
| GitHub | PRs, generic contract check and protected human-approved merges. |

Lifecycle: Triage → Specifying → Spec review (Gate 1) → Building → Verifying → Reviewing → Ready to merge (Gate 2) → Done. Needs human and Canceled are alternate states. Spec PRs never enter implementation review. A merge-completed handler confirms implementation merges and reports completion; no publishing stage is active.

Factory files describe neutral contracts; project instance values live in `factory/config.yaml` and `factory/linear.yaml`, and Cursor bindings live in automation specifications. Factory skills delegate stack craft only after a verified project adapter exists. Reviewer and builder must use different model vendors.

Order: (1) generic factory and docs/config smoke test, (2) separately authorized initial project setup using the supplied architecture/plan and local Docker, (3) separately authorized build/lint/test adapter and CI. No application framework tooling is needed to establish the factory lifecycle.

## Consequences

- At readiness 1, only documentation/factory tasks run; application requests remain in Triage.
- Factory contract validation is distinct from future application verification.
- `Done` means merged and reported, with no claim about local execution or shipping.
- Event receipts, run ownership, exact-head checks and revision-bound approvals are required; capability gaps are recorded and resolved before activation.
- Runtime automation state is captured in the setup log; checked-in definitions are not evidence that integrations are active.
- Shipping and release-note stages remain disabled reference contracts, with no deployment workflows or release adapters.
