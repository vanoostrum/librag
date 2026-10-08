"""Read or replace the `## Spec (rev N)` section of a Linear issue description.

The agent reads and writes the description through the Linear tool; this script
only does the text transform so revision numbering and section boundaries stay
consistent across runs.
"""

import argparse
import re
import sys

HEADING = re.compile(r'^## Spec \(rev (\d+)\)[ \t]*$', re.M)
NEXT_SECTION = re.compile(r'^## ', re.M)
END_MARK = '<!-- /spec -->'
END_MARK_RE = re.compile(r'^<!-- /spec -->[ \t]*$', re.M)


def find(description):
    """Return (rev, start, end) of the spec section, or (0, None, None).

    A `<!-- /spec -->` line ends the section, so later markdown headings stay
    inside the spec. With no marker, the next level-2 heading ends it.
    """
    match = HEADING.search(description)
    if not match:
        return 0, None, None
    marker = END_MARK_RE.search(description, match.end())
    if marker:
        end = marker.end()
        if end < len(description) and description[end:end + 1] == '\n':
            end += 1
        return int(match[1]), match.start(), end
    following = NEXT_SECTION.search(description, match.end())
    end = following.start() if following else len(description)
    return int(match[1]), match.start(), end


def _section_text(section):
    if '\n' not in section:
        return ''
    text = END_MARK_RE.sub('', section.split('\n', 1)[1])
    return text.strip()


def body(description):
    rev, start, end = find(description)
    if start is None:
        return 0, ''
    return rev, _section_text(description[start:end])


def update(description, spec):
    """Return (new_description, rev, changed). Identical spec text keeps the revision."""
    spec = HEADING.sub('', spec, count=1)
    spec = END_MARK_RE.sub('', spec).strip()
    if not spec:
        raise ValueError('spec is empty')
    rev, start, end = find(description)
    if start is not None and body(description)[1] == spec:
        return description, rev, False
    section = f'## Spec (rev {rev + 1})\n{spec}\n{END_MARK}\n'
    if start is None:
        base = description.rstrip()
        return (f'{base}\n\n{section}' if base else section), 1, True
    rest = description[end:]
    gap = '' if not rest or rest.startswith('\n') else '\n'
    return description[:start] + section + gap + rest, rev + 1, True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    show = sub.add_parser('show', help='print the revision and the spec text')
    show.add_argument('--description', required=True, help='file with the current issue description')
    upd = sub.add_parser('update', help='replace the spec section and increment the revision')
    upd.add_argument('--description', required=True, help='file with the current issue description')
    upd.add_argument('--spec', required=True, help='file with the new spec text, without the heading')
    upd.add_argument('--out', help='where to write the new description (default: overwrite --description)')
    args = parser.parse_args()
    with open(args.description) as handle:
        description = handle.read()
    if args.command == 'show':
        rev, text = body(description)
        if not rev:
            print('no spec')
            return 2
        print(f'rev {rev}\n{text}')
        return 0
    with open(args.spec) as handle:
        spec = handle.read()
    try:
        new, rev, changed = update(description, spec)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    with open(args.out or args.description, 'w') as handle:
        handle.write(new)
    print(f'{"rev" if changed else "unchanged rev"} {rev}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
