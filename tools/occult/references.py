"""Repository reference graph for distribution pruning and orphan checks (stdlib only).

Runtime imports, installed component registrations, catalogue templates, theme stylesheets,
CSS URLs and literal template/script paths are edges. Tests and executable scripts are roots;
package initializers and retained font licences are implicit edges. No file is its own edge.
"""
import ast
import json
from pathlib import Path
import re

from . import components

ASSET_SUFFIXES = {'.j2', '.css', '.svg', '.ttf', '.woff', '.woff2', '.js', '.mjs', '.png'}


def module_path(root, name):
    path = root / 'tools' / name.replace('.', '/')
    return next((p for p in (path.with_suffix('.py'), path / '__init__.py') if p.is_file()), None)


def imports(root, path):
    """Local Python import targets, including `from package import module` and package parents."""
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except (UnicodeDecodeError, SyntaxError):
        return set()
    relative = path.relative_to(root)
    package = '.'.join(relative.with_suffix('').parts[1:-1]) if relative.parts[0] == 'tools' else ''
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package.split('.')[:len(package.split('.')) - node.level + 1] if node.level else []
            prefix = '.'.join([*base, *([node.module] if node.module else [])])
            names.add(prefix)
            names.update(prefix + '.' + alias.name for alias in node.names)
    targets = set()
    for name in names:
        target = module_path(root, name)
        if target:
            targets.add(target)
            targets.update(p / '__init__.py' for p in target.parents if p != root and
                           p.is_relative_to(root / 'tools') and (p / '__init__.py').is_file())
    return targets


def text_paths(root, source, candidates):
    """Resolve literal paths/basenames against the containing file and common resource roots.

    Basenames are accepted for template catalogues and dynamically assembled font paths. A
    directory name alone does not retain its contents. Declarations in the ownership manifest
    are intentionally not reference edges.
    """
    if source.name == 'components.py':
        return set()
    try:
        content = source.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        return set()
    # Strip comments so a stale explanation cannot keep a dead asset alive.
    if source.suffix == '.py':
        tree = ast.parse(content)
        literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        content = '\n'.join(literals)
    else:
        content = re.sub(r'/\*.*?\*/|\{#.*?#\}', '', content, flags=re.S)
    hits = set()
    for candidate in candidates:
        if candidate == source:
            continue
        rel = candidate.relative_to(root).as_posix()
        # Require an entire filename, not a coincidental suffix in another filename.
        if re.search(r'(?<![\w.-])' + re.escape(candidate.name) + r'(?![\w.-])', content):
            hits.add(candidate)
        elif rel in content:
            hits.add(candidate)
    return hits


def graph(root):
    """Return (reachable files, referenceable files); paths are relative to root."""
    root = Path(root).resolve()
    from . import collections, data, outputs, views
    ix = data.load()
    candidates = {p for folder in ('tools', 'templates', 'style', 'scripts')
                  for p in (root / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts
                  and (p.suffix in ASSET_SUFFIXES | {'.py'} or p.name.startswith('OFL-'))}
    assets = {p for p in candidates if p.suffix in ASSET_SUFFIXES}
    roots = {root / 'occult', root / 'tools/occult/cli.py', root / 'scripts/build/validate.py',
             *root.glob('tools/tests/test_*.py')}
    # Registered templates have computed names in the selector and collection paths.
    roots.update(root / 'templates' / out.template for out in outputs.CATALOGUE.values() if out.template)
    roots.update(root / 'templates/cards' / (fn.__module__.rsplit('.', 1)[-1] + '.j2') for fn in views.CARDS.values())
    roots.update(root / 'templates/md' / template for _, template, _ in collections.catalogue(ix))
    roots.add(root / 'templates/md/readme.md.j2')
    template_globals = {}
    components.apply('template_globals', template_globals)
    def registered_templates(value):
        if isinstance(value, dict):
            for child in value.values():
                registered_templates(child)
        elif isinstance(value, str) and value.endswith('.j2'):
            roots.add(root / 'templates' / value)
    registered_templates(template_globals)
    for theme in (root / 'style/themes').glob('*/theme.json'):
        roots.add(theme)
        spec = json.loads(theme.read_text())
        def styles(value):
            if isinstance(value, list):
                for entry in value:
                    if isinstance(entry, str) and entry.endswith('.css'):
                        roots.add((theme.parent / entry).resolve())
                    elif isinstance(entry, dict) and 'component' in entry:
                        if {entry['component'], *entry.get('requires', ())} <= {m.__name__.rsplit('.', 1)[-1] for m in components.installed()}:
                            styles(entry['files'])
            elif isinstance(value, dict):
                for child in value.values():
                    styles(child)
        styles(spec)
    # This manifest intentionally enumerates dynamic icon ids; prune unavailable class icons
    # before scanning it, rather than treating every SVG in its directory as reachable.
    roots.add(root / 'style/icons/manifest.json')
    roots.update(Path(m.__file__).resolve() for m in components.installed())
    reachable, pending = set(), list(roots)
    while pending:
        source = pending.pop()
        if source in reachable or not source.is_file():
            continue
        reachable.add(source)
        if source.suffix == '.py' or source.name == 'occult':
            pending.extend(imports(root, source) - reachable)
        # Package initializers for dynamically registered modules too.
        pending.extend(p / '__init__.py' for p in source.parents if p.is_relative_to(root / 'tools')
                       and p != root / 'tools' and (p / '__init__.py').is_file() and p / '__init__.py' not in reachable)
        pending.extend(text_paths(root, source, assets) - reachable)
    # OFL licence names identify font families; each retained family keeps its licence.
    for font in [p for p in reachable if p.suffix in {'.ttf', '.woff', '.woff2'}]:
        family = re.sub(r'[^a-z]', '', font.stem.split('-')[0].lower())
        reachable.update(p for p in font.parent.glob('OFL-*') if p.stem.lower() == 'ofl-' + family)
    return ({p.relative_to(root) for p in reachable}, {p.relative_to(root) for p in candidates})


def unreferenced(root):
    reachable, candidates = graph(root)
    return sorted(candidates - reachable)
