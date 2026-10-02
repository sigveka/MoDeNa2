"""
test_docs.py — the documentation must agree with the repository and the CLI
-----------------------------------------------------------------------------
A documentation audit found the docs drifted in ways nobody noticed for
months, every one of them mechanically detectable:

  * `modena freeze` / `modena restore` documented as top-level commands,
    though they are `modena model freeze` / `modena model restore`;
  * links to a LICENSE file and to `src/src/CLAUDE.md`, neither in the repo;
  * table-of-contents links that resolved in only one renderer -- GitHub
    keeps the `--` an em dash leaves behind, mkdocs collapses it to `-` --
    so each page was broken wherever it was read;
  * a 627-line guide missing from the mkdocs nav, unreachable on the site.

These checks read only files: no MongoDB, no build, no git (the clean
container in ci/docker-tests has no .git), so they run in the unit tier.
"""

import argparse
import re
import unicodedata
from pathlib import Path

import pytest

import modena.__main__ as cli

_REPO = Path(__file__).resolve().parents[3]


def _docs():
    out = [_REPO / 'README.md', _REPO / 'src/tests/README.md']
    out += sorted((_REPO / 'docs').glob('*.md'))
    out += sorted((_REPO / 'examples').glob('*/README.md'))
    return [p for p in out if p.exists()]


_DOCS = _docs()
_IDS = [str(p.relative_to(_REPO)) for p in _DOCS]


def _strip_code_blocks(text):
    """Text with fenced code blocks blanked (line numbers preserved)."""
    out, in_code = [], False
    for line in text.split('\n'):
        if line.lstrip().startswith('```'):
            in_code = not in_code
            out.append('')
        else:
            out.append('' if in_code else line)
    return '\n'.join(out)


# --------------------------------------------------------------------------- #
# Links and anchors
# --------------------------------------------------------------------------- #

def _headings(text):
    for line in _strip_code_blocks(text).split('\n'):
        m = re.match(r'^#{1,6}\s+(.*?)\s*#*\s*$', line)
        if m:
            yield m.group(1)


def _plain(heading):
    heading = re.sub(r'`([^`]*)`', r'\1', heading)
    return re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', heading)


def _slug_mkdocs(heading):
    """python-markdown's toc slugify, which mkdocs uses."""
    v = unicodedata.normalize('NFKD', _plain(heading)).encode('ascii', 'ignore').decode()
    v = re.sub(r'[^\w\s-]', '', v).strip().lower()
    return re.sub(r'[-\s]+', '-', v)


def _slug_github(heading):
    v = re.sub(r'[^\w\- ]', '', _plain(heading).strip().lower())
    return v.replace(' ', '-')


def _anchors(text):
    """(mkdocs ids, GitHub ids) of a page, explicit <a id> included in both."""
    explicit = set(re.findall(r'<a\s+id="([^"]+)"', text))
    heads = list(_headings(text))
    return ({_slug_mkdocs(h) for h in heads} | explicit,
            {_slug_github(h) for h in heads} | explicit)


_LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')


@pytest.mark.parametrize('doc', _DOCS, ids=_IDS)
def test_relative_links_resolve(doc):
    """A link to a file or directory in the repository must reach one."""
    text = _strip_code_blocks(doc.read_text())
    missing = []
    for target in _LINK.findall(text):
        if re.match(r'^[a-z]+:', target) or target.startswith('#'):
            continue
        path = target.split('#', 1)[0]
        if not (doc.parent / path).exists():
            missing.append(target)
    assert not missing, f'links to nothing: {missing}'


@pytest.mark.parametrize('doc', _DOCS, ids=_IDS)
def test_anchors_resolve_on_github_and_in_mkdocs(doc):
    """`#fragment` links must work in both renderers the docs are read in.

    The two slug a heading differently when it contains punctuation such as
    an em dash; an explicit <a id="..."></a> before the heading works in both.
    """
    text = _strip_code_blocks(doc.read_text())
    broken = []
    for target in _LINK.findall(text):
        if re.match(r'^[a-z]+:', target) or '#' not in target:
            continue
        path, frag = target.split('#', 1)
        page = (doc.parent / path) if path else doc
        if not page.is_file() or page.suffix != '.md':
            continue
        mk, gh = _anchors(page.read_text())
        where = [name for name, ids in (('mkdocs', mk), ('GitHub', gh)) if frag not in ids]
        if where:
            broken.append(f'{target} (broken in {" and ".join(where)})')
    assert not broken, f'unresolved anchors: {broken}'


_REPO_PATH = re.compile(r'`((?:src|docs|examples|applications|ci|cmake)/[A-Za-z0-9_./\-\[\]]+)`')


@pytest.mark.parametrize('doc', _DOCS, ids=_IDS)
def test_backticked_repo_paths_exist(doc):
    """`src/...`, `docs/...` etc. written as a path must name something."""
    missing = sorted({
        p for p in _REPO_PATH.findall(doc.read_text())
        if '*' not in p and '<' not in p and not (_REPO / p.rstrip('/.')).exists()
    })
    assert not missing, f'paths that do not exist: {missing}'


def test_every_docs_page_is_in_the_mkdocs_nav():
    nav = set(re.findall(r':\s*([\w\-/]+\.md)', (_REPO / 'mkdocs.yml').read_text()))
    pages = {p.name for p in (_REPO / 'docs').glob('*.md')}
    assert nav <= pages, f'nav entries with no page: {sorted(nav - pages)}'
    assert pages <= nav, f'pages missing from the mkdocs nav: {sorted(pages - nav)}'


# --------------------------------------------------------------------------- #
# The CLI
# --------------------------------------------------------------------------- #

def _command_tree():
    """{command path tuple: set of option strings} from the real parser."""
    tree = {}

    def walk(parser, path):
        opts = set()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    walk(sub, path + (name,))
            else:
                opts.update(action.option_strings)
        tree[path] = opts

    walk(cli._build_parser(), ())
    return tree


_TREE = _command_tree()


#: A shell command that runs the CLI: `modena ...` or `python[3] -m modena ...`.
_INVOCATION = re.compile(r'^(?:\$\s+)?(?:python3?\s+-m\s+)?modena((?:\s+[^\s#|;&)`]+)*)')


def _code_commands(text):
    """`modena ...` invocations written as shell commands.

    Only where a shell would run them: an inline code span that starts with
    the command, or a line -- or a `&&` / `;` segment of one -- of a fenced
    code block.  `import modena`, diagrams and prose are not invocations.
    """
    chunks = re.findall(r'`([^`\n]+)`', text)
    in_code = False
    for line in text.split('\n'):
        if line.lstrip().startswith('```'):
            in_code = not in_code
        elif in_code:
            chunks.extend(re.split(r'&&|;', line))
    found = []
    for chunk in chunks:
        m = _INVOCATION.match(chunk.strip())
        if m and m.group(1).strip():
            found.append(m.group(1).split())
    return found


@pytest.mark.parametrize('doc', _DOCS, ids=_IDS)
def test_documented_cli_commands_and_options_exist(doc):
    """Every `modena <command> [--option]` shown as code must parse."""
    problems = []
    for words in _code_commands(doc.read_text()):
        path = ()
        for w in words:
            if path + (w,) in _TREE:
                path += (w,)
            else:
                break
        if not path:
            # `modena ...` / `modena <command>` are placeholders, not commands.
            if not words[0].startswith(('-', '<', '[', '...', '…')):
                problems.append(f'modena {words[0]}: no such command')
            continue
        rest = words[len(path):]
        has_sub = any(len(p) > len(path) and p[:len(path)] == path for p in _TREE)
        if has_sub and rest and not rest[0].startswith('-') and '<' not in rest[0]:
            problems.append(f'modena {" ".join(path)} {rest[0]}: no such subcommand')
        valid = set().union(*(_TREE.get(path[:i], set()) for i in range(len(path) + 1)))
        for tok in rest:
            flag = tok.split('=')[0].rstrip('.,:)\'"')
            if flag.startswith('--') and len(flag) > 2 and flag not in valid:
                problems.append(f'modena {" ".join(path)}: no option {flag}')
    assert not problems, '\n  '.join(['documented CLI usage the parser rejects:']
                                     + sorted(set(problems)))
