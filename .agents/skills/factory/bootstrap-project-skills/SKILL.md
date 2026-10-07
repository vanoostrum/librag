---
name: bootstrap-project-skills
description: At readiness step 3, derive a verified project verification skill from the real project and CI. Do not scaffold an application or create publishing adapters.
---

# bootstrap-project-skills

1. Before step 3 is authorized, report that this is deferred and stop.
2. Read the actual manifests, task runners, and CI. Keep the human's architecture and notes.
3. Run the install, build, lint, and test commands. Record the results. A command that has not run is not verified.
4. Write the `verify-*` skill and the `checks.project_required` mapping in a PR, with the command evidence.
5. Raise readiness to 3 only after the human reviews it. Publishing stays disabled.
