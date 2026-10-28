# Models

Which model runs each part of the factory and of pstack. Change a model here, in a PR. Model names are the Claude Code family names: `opus`, `fable`, `sonnet`, `haiku`.

## Factory steps

Each `factory-*` skill has the same model in its `model:` header, and Claude Code runs the step on it. A test fails CI when a header and this table differ.

| Step | Skill | Model |
|---|---|---|
| Plan | `factory-plan` | opus |
| Spec | `factory-spec` | opus |
| Design | `factory-design` | opus |
| Build | `factory-build` | sonnet |
| Review | `factory-review` | opus |
| Merge | `factory-merge` | haiku |

## Factory subagents

A factory step starts each of these subagents with the model in this table.

| Subagent | Started by | Model |
|---|---|---|
| verify | `factory-build` | sonnet |
| app driver | `factory-build` | sonnet |
| CI polling and log reading | `factory-build` | haiku |
| fresh reviewer | `factory-review` | opus |
| plan reviewer | `factory-plan` | opus |

## pstack roles

pstack reads the lines below, in the format of its `setup-pstack` skill. `inherit-parent` runs the role on the model of the step that calls it. A panel role starts one subagent per list entry, and bstack asks before it starts more than one.

feature, refactoring: inherit-parent
bug-fix: inherit-parent
perf-issue: inherit-parent
hillclimb: inherit-parent
judgment and prose: inherit-parent
strongest judgment: inherit-parent
how explorer: inherit-parent
how explainer: inherit-parent
why investigators: inherit-parent
why synthesizer: inherit-parent
reflect tooling: inherit-parent
reflect judgment, divergent, synthesizer: inherit-parent
arena runners: opus, sonnet
arena cross-judge pool: opus, sonnet
swarm workers: inherit-parent
architect runners: opus, sonnet
interrogate reviewers: opus, sonnet

default effort: session
