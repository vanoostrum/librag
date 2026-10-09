# Factory handoff

You decide when the factory moves to the next readiness step, and the current step is recorded as `readiness.step` in `factory/config.yaml`.

## Step 1. Factory first

This step covers integrations, automations, and contracts. The factory exercises the lifecycle with documentation or configuration work and changes only factory and docs files, while you approve the spec and the merge. It is the current step while `readiness.step` is 1, and it is left when that value becomes 2. Application implementation stays blocked until step 3, project verification, is finished, and an application request made before then stays in Triage with the `needs-project-setup` label.

## Step 2. Initial project setup

This step covers the initial setup of the project from the architecture and plan that already exist. You supply the existing architecture and project plan, and you run Docker locally; the factory must not invent or overwrite them. It is entered when `readiness.step` becomes 2, and it is left when that value becomes 3. At this step a setup PR may create any project file, including its own CI workflow, and other application requests still wait in Triage.

## Step 3. Project verification

This step covers build, lint, and test. The factory derives those commands from the implemented project and its CI, and you leave the step only once it is finished. It is entered when `readiness.step` becomes 3, and it is finished only when `factory/config.yaml` names a `checks.project_verify_skill`, lists at least one entry under `checks.project_required`, and that verify skill exists in the repo.

Publishing is out of scope.
