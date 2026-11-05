"""Explicit optional features and their files, shared by runtime and distribution builds.

Only installed modules register hooks. Imports inside a hook stay local so registries can be
assembled without circular imports or loading the data. Paths are relative to the repository.
"""
from functools import lru_cache
from importlib import import_module
from pathlib import Path

COMPONENTS = {
    'loot': ('rules/loot.py',),
    'generators': ('rules/generate.py',),
    'images': ('fetch.py', 'images.py', 'views/art.py'),
    'proof': (),
    'deities': ('views/deity.py',),
    'bastions': ('views/facility.py',),
    'misc_types': (),
    'deck_cards': ('views/deck_card.py',),
    'lore': (),
}
# Non-Python resources owned by the same features. One ownership manifest, no builder denylist.
RESOURCES = {
    'images': ('templates/art/', 'style/base/art.css', 'style/themes/grimoire/art.css',
               'style/themes/grimoire/book-art.css', 'style/themes/grimoire/deities-art.css', 'style/themes/grimoire/encounter-art.css',
               'tools/render/art.js', 'tools/tests/test_images.py'),
    'proof': ('tools/tests/visual/',),
    'deities': ('templates/cards/deity.j2', 'templates/md/deities.md.j2', 'style/themes/grimoire/deities.css'),
    'bastions': ('templates/cards/facility.j2', 'templates/md/bastions.md.j2', 'style/themes/grimoire/bastions.css'),
    'deck_cards': ('templates/cards/deck_card.j2', 'style/themes/grimoire/deck-cards.css'),
}


def files(name):
    """Owned files/directories, including the registration module itself."""
    return (f'tools/occult/extras/{name}.py',
            *('tools/occult/' + p for p in COMPONENTS[name]), *RESOURCES.get(name, ()))


@lru_cache(maxsize=None)
def installed():
    return tuple(import_module('.extras.' + name, __package__) for name in COMPONENTS
                 if (Path(__file__).parent / 'extras' / (name + '.py')).is_file())


def apply(hook, *args):
    for module in installed():
        fn = getattr(module, hook, None)
        if fn:
            fn(*args)


def values(hook, *args):
    """Flatten contributions, in component order."""
    return [value for module in installed() if (fn := getattr(module, hook, None))
            for value in fn(*args)]


def mapping(hook, *args):
    return dict(pair for module in installed() if (fn := getattr(module, hook, None))
                for pair in fn(*args).items())


def transform(hook, value, *args):
    for module in installed():
        fn = getattr(module, hook, None)
        if fn:
            value = fn(value, *args)
    return value
