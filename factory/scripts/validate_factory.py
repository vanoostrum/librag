#!/usr/bin/env python3
"""Validate factory assets; --runtime also requires populated bindings/probe evidence."""

import argparse
from pathlib import Path
import re
import sys

import yaml


def validate(root, runtime=False):
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    def load(relative):
        try:
            value = yaml.safe_load((root / relative).read_text())
            require(isinstance(value, dict), f'{relative}: expected mapping')
            return value if isinstance(value, dict) else {}
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f'{relative}: {exc}')
            return {}

    cfg = load('factory/config.yaml')
    linear = load('factory/linear.yaml')
    graph = load('factory/stages.yaml')
    require(cfg.get('repository') == 'vanoostrum/librag', 'Wrong destination repository')
    require(linear.get('team', {}).get('name') == 'LibRag', 'Expected dedicated LibRag team')
    require(bool(re.fullmatch(r'[A-Z][A-Z0-9]*', str(linear.get('team', {}).get('key', '')))),
            'Invalid issue key')
    for binding, name in (('interface', 'librag'), ('log', 'librag-log')):
        require(cfg.get('slack', {}).get(binding, {}).get('name') == name, f'Wrong {binding} channel')
    ready = cfg.get('readiness', {})
    step = ready.get('step')
    require(step in (1, 2, 3), 'Readiness must be step 1, 2 or 3')
    require(ready.get('publishing_enabled') is False, 'Publishing must stay disabled')
    checks = cfg.get('checks', {})
    require(checks.get('factory_required') == ['Factory Contracts'], 'Missing stable factory check')
    if step in (1, 2):
        require(ready.get('application_implementation_enabled') is False,
                'Application automation cannot run before step 3')
        require(not checks.get('project_required') and not checks.get('project_verify_skill'),
                'Project verification belongs in step 3')
    if ready.get('application_implementation_enabled'):
        require(step == 3 and bool(checks.get('project_required')), 'Missing project required checks')
        adapter = checks.get('project_verify_skill')
        require(bool(adapter) and (root / str(adapter)).is_file(), 'Missing actual project verify adapter')
    stages = graph.get('stages', [])
    require(isinstance(stages, list), 'Stages must be a list')
    names = [s.get('name') for s in stages if isinstance(s, dict)]
    require(len(names) == len(set(names)), 'Duplicate stage name')
    required_states = {'Triage', 'Specifying', 'Spec review', 'Building', 'Verifying', 'Reviewing',
                       'Ready to merge', 'Done', 'Needs human', 'Canceled'}
    require(required_states <= set(linear.get('states', {})), 'Missing required tracker state')
    require('Shipping' not in linear.get('states', {}), 'Shipping is outside current scope')
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        name = stage.get('name')
        reference = stage.get('skill')
        if reference:
            require((root / '.agents/skills' / reference / 'SKILL.md').is_file(), f'{name}: missing skill')
        if stage.get('enabled'):
            for field in ('linear_state', 'next_state'):
                state = stage.get(field)
                require(state is None or state in linear.get('states', {}), f'{name}: unknown {field}')
        if name in ('ship', 'release-notes'):
            require(stage.get('enabled') is False, f'{name}: publishing stage must be disabled')
    by_name = {s['name']: s for s in stages if isinstance(s, dict) and 'name' in s}
    require(by_name.get('merge-gate', {}).get('next_state') is None,
            'Merge gate must wait for confirmed completion')
    require(by_name.get('merge-completed', {}).get('next_state') == 'Done', 'Missing merge completion')
    require(by_name.get('merge-completed', {}).get('enabled') is True, 'Completion handler disabled')
    for name in ('front-desk', 'spec', 'build', 'ci-fixer', 'spec-reviewer', 'comment-fixer', 'merge-completed'):
        require((root / f'factory/automations/{name}.md').is_file(), f'Missing {name} automation spec')
    skill_dir = root / '.agents/skills/factory'
    skills = list(skill_dir.glob('*/SKILL.md'))
    require(len(skills) == 8, 'Expected eight reused factory skills')
    for path in skills:
        text = path.read_text()
        match = re.match(r'^---\n(.*?)\n---\n', text, re.S)
        require(bool(match), f'{path.name}: invalid frontmatter')
        if match:
            front = yaml.safe_load(match[1])
            require(isinstance(front, dict) and front.get('name') == path.parent.name,
                    f'{path.parent.name}: frontmatter name mismatch')
            require(isinstance(front, dict) and bool(front.get('description')), f'{path}: no description')
        for section in ('Purpose', 'Inputs', 'Outputs', 'Done criteria', 'Steps', 'Escalation', 'Reporting'):
            require(f'## {section}' in text, f'{path.parent.name}: missing {section}')
    workflow = load('.github/workflows/factory-contracts.yml')
    # PyYAML parses an unquoted YAML 1.1 `on` key as True; GitHub uses YAML 1.2.
    events = workflow.get('on', workflow.get(True, {}))
    require('pull_request' in events and not events.get('pull_request'),
            'Factory check must run on all PRs without paths/branch filters')
    jobs = workflow.get('jobs', {})
    require(any(job.get('name') == 'Factory Contracts' for job in jobs.values()), 'Missing required job name')
    scope_paths = [root / 'AGENTS.md', root / 'docs', root / 'factory', root / '.agents/skills/factory']
    legacy = re.compile(r'\b(?:SwiftUI|SwiftLint|XcodeGen|TestFlight|NapTime)\b|vanoostrum/nap-time(?:-certificates)?|#factory(?:-log)?\b')
    for base in scope_paths:
        for path in ([base] if base.is_file() else base.rglob('*')):
            if path.suffix not in ('.md', '.yaml', '.yml'):
                continue
            # Provenance explicitly identifies the source repo; no runtime binding does.
            content = '\n'.join(line for line in path.read_text().splitlines()
                                if not line.startswith('Prepared files') and 'Source:' not in line)
            require(not legacy.search(content), f'Legacy project binding in {path.relative_to(root)}')
    if runtime or cfg.get('runtime', {}).get('activated'):
        team = linear.get('team', {})
        require(bool(team.get('id')), 'Runtime: team ID missing')
        for name, value in linear.get('states', {}).items():
            require(bool(value.get('id')), f'Runtime: state ID missing: {name}')
        for label, value in linear.get('labels', {}).items():
            require(bool(value), f'Runtime: label ID missing: {label}')
        for binding in ('interface', 'log'):
            require(bool(cfg.get('slack', {}).get(binding, {}).get('id')), f'Runtime: {binding} ID missing')
        require(bool(cfg.get('approvals', {}).get('slack_user_ids')), 'Runtime: no named approvers')
        models = cfg.get('models', {})
        for name in ('reasoning', 'coding', 'review-different-family', 'fast'):
            require(bool(models.get(name, {}).get('id')) and bool(models.get(name, {}).get('vendor')),
                    f'Runtime: model mapping missing: {name}')
        require(models.get('coding', {}).get('vendor') != models.get('review-different-family', {}).get('vendor'),
                'Runtime: builder and reviewer need different vendors')
        state = cfg.get('runtime', {})
        for mechanism in ('serialization', 'receipts'):
            require(bool(state.get(mechanism, {}).get('mechanism')) and bool(state.get(mechanism, {}).get('evidence')),
                    f'Runtime: {mechanism} mechanism/evidence missing')
        for capability in ('slack_threads', 'linear_write', 'protected_merge', 'revision_approval',
                           'event_deduplication', 'run_serialization'):
            require(state.get('capabilities', {}).get(capability) is True, f'Runtime: unverified {capability}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', action='store_true')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    errors = validate(args.root, args.runtime)
    if errors:
        for error in errors:
            print(f'ERROR: {error}', file=sys.stderr)
        return 1
    print('Factory assets valid' + ('; configured runtime prerequisites recorded' if args.runtime else
                                  '; live runtime bindings are not verified by this check'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
