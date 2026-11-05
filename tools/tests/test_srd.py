"""Public SRD contracts. No commercial data, import checkout or goldens required."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from occult import data, text
from occult.rules import character, core, tables


def objects(x):
    yield x
    if isinstance(x, dict):
        for value in x.values():
            yield from objects(value)
    elif isinstance(x, list):
        for value in x:
            yield from objects(value)


class SRD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ix = data.load()
        cls.book = ROOT / 'data/srd-5.2'
        cls.meta = json.loads((cls.book / 'book.json').read_text())
        cls.trees = [json.loads((cls.book / c['file']).read_text()) for c in cls.meta['contents']]

    def cli(self, *args):
        p = subprocess.run([str(ROOT / 'occult'), *map(str,args)], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def test_load_and_validate(self):
        self.assertEqual(self.ix.problems, [])
        p = subprocess.run([sys.executable, 'scripts/build/validate.py'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual([b['id'] for b in self.ix.books], ['srd-5.2'])
        self.assertIn('Creative Commons Attribution', self.meta['license']['attribution'])

    def test_counts(self):
        for kind, count in {'spell':339, 'class':12, 'subclass':12, 'species':9, 'background':4, 'feat':17}.items():
            self.assertEqual(len(self.ix.all(kind)), count, kind)
        self.assertTrue(330 <= len(self.ix.all('creature')) <= 340)
        self.assertTrue(240 <= len(self.ix.all('magic-item')) <= 350)
        classes={e.title for e in self.ix.all('class')}
        for spell in self.ix.all('spell'):
            self.assertTrue(set(spell.classes) <= classes, spell.sid)
        self.assertEqual(len(self.ix.all('weapon-property')), 10)
        self.assertEqual(len(self.ix.all('mastery-property')), 8)
        self.assertEqual(len({e.title.lower() for e in self.ix.all('creature')}), len(self.ix.all('creature')))

    def test_no_commercial_names_pages_or_art(self):
        deny = json.loads((ROOT / 'tools/tests/srd-denylist.json').read_text())
        for path in ROOT.rglob('*'):
            if not path.is_file() or path.name == 'srd-denylist.json' or path.name.upper().startswith(('LICENSE', 'NOTICE', 'README')):
                continue
            try:
                blob = path.read_text(encoding='utf-8').lower().replace('’', "'")
            except (UnicodeDecodeError, OSError):
                continue
            for name in deny:
                # The ordinary word 'sigil' is used throughout the SRD for magic marks.
                if name == 'Si' + 'gil':
                    original = path.read_text(encoding='utf-8')
                    self.assertNotRegex(original, r'\b' + re.escape(name) + r'\b', str(path.relative_to(ROOT)))
                else:
                    self.assertNotIn(name.lower().replace('’', "'"), blob, (str(path.relative_to(ROOT)), name))
        for obj in objects(self.trees):
            if isinstance(obj, dict):
                self.assertNotIn('page', obj)
                self.assertNotIn('images', obj)
                self.assertNotIn('cover', obj)
                self.assertNotEqual(obj.get('type'), 'image')
                self.assertFalse(str(obj.get('path', '')).endswith(('.webp', '.png', '.jpg', '.svg')))
                if isinstance(obj.get('origin'), dict):
                    self.assertEqual(set(obj['origin']), {'source', 'prop', 'name'})
        self.assertEqual(json.loads((self.book / 'images.json').read_text()), [])
        self.assertNotIn('cover', self.meta)

    def test_ids_and_links(self):
        self.assertEqual(len(self.ix.by_sid), len(self.ix.entities))
        nlinks = 0
        for e in self.ix.entities:
            self.assertIs(self.ix.get(e.sid), e)
            self.assertTrue(e.id.startswith('srd-5.2/'))
            for value in objects([e.data, e.content]):
                if isinstance(value, str):
                    for _, target in text.links(value):
                        self.assertIn(target, self.ix.by_id, (e.sid, target))
                        nlinks += 1
        self.assertGreater(nlinks, 1000)
        self.assertEqual(self.ix.get('chapter:srd/07').type, 'chapter')
        self.assertIn('Arcane Hand', self.cli('show', 'spell:arcane-hand'))
        self.assertIn('srd', self.cli('list', 'spells', '--level', '3').lower())
        self.assertEqual([e.slug for e in self.ix.all('chapter')], [f'{n:02}' for n in range(1,len(self.ix.roots)+1)])

    def test_flagged_entry_continuations_and_table_footnotes(self):
        body=' '.join(text.entity_text(e) for e in self.ix.entities)
        self.assertIn('If more than two are combined, roll again',body)
        self.assertIn('Primordial includes the Aquan',body)
        self.assertIn('Appropriate equipment (such as skis)',body)
        self.assertIn('The time and cost are halved',body)

    def test_examples(self):
        for path in sorted((ROOT / 'characters/examples').glob('*.json')):
            with self.subTest(path=path.name):
                sheet = character.build(json.loads(path.read_text()), ix=self.ix)
                self.assertEqual(sheet['warnings'], [])
                self.assertGreater(sheet['hit_points']['max'], 0)

    def test_core_rules_and_tables(self):
        self.assertEqual(core.point_buy_cost(dict(zip(tables.ABILITIES,[15,15,15,8,8,8]))), (27, []))
        self.assertEqual(tables.xp_budget()[3]['high'], 400)
        self.assertEqual(tables.advancement()[5], (6500, 3))
        self.assertEqual(tables.cr_xp()['1/4'], 50)
        self.assertIn('8', self.cli('calc', 'slots', 'wizard=5', 'cleric=3'))
        self.assertNotIn('treasure_hoard', tables.SOURCES)

    def test_collections(self):
        self.cli('make', 'md', '--check')
        self.assertGreater(len(list((ROOT / 'collections').rglob('*.md'))), 40)

    def test_pwa(self):
        from occult import explorer, pipeline
        files = explorer.build(self.ix, pipeline.env())
        doc = json.loads(files['spells.json'])
        self.assertEqual(len(doc['spells']), 339)
        self.assertEqual(doc['meta']['books'], [{'id':'srd', 'abbr':'SRD'}])
        arcane = next(s for s in doc['spells'] if s['id']=='arcane-hand')
        self.assertEqual(arcane['t'], 'Arcane Hand')
        self.assertNotIn('None', arcane['p'])
        self.assertEqual(files['sw.js'], explorer.build(self.ix, pipeline.env())['sw.js'])
        self.assertIn('manifest.webmanifest', files)
        self.assertIn('spells.json', files['sw.js'])

    def test_html_outputs(self):
        from occult import outputs, pipeline, query, views
        from occult.rules import encounter as engine
        from occult.views import charsheet, encounter
        for kind, args in [('spellbook', ('cleric',)), ('class', ('fighter',)),
                           ('equipment', ()), ('quickref', ()), ('glossary', ())]:
            with self.subTest(kind=kind):
                output = outputs.CATALOGUE[kind]
                ctx = output.group(self.ix, *args)
                html = pipeline.book_html(output, ctx, 'color', 'a4')
                self.assertIn('<html', html)
                self.assertNotIn('](srd-', html)
        # Every SRD card model and card template must work, not just the smoke selection.
        models = [views.for_(self.ix,e) for e in self.ix.entities if views.supports(e)]
        html = pipeline.html_for(outputs.CATALOGUE['cards'], models, 'color', 'a4')
        self.assertIn('Arcane Hand', html)
        self.assertNotIn('](srd-', html)
        for path in (ROOT / 'characters/examples').glob('*.json'):
            sheet = character.build(json.loads(path.read_text()), self.ix)
            ctx = charsheet.context(self.ix, sheet)
            html = pipeline.env().get_template('book/character.html.j2').render(
                title=ctx['title'], theme=pipeline.theme('grimoire','character','color','a4'),
                paper='a4', sprite=pipeline.sprite(), book=ctx, book_name='character',
                body_class='book', scripts=[])
            self.assertIn(ctx['title'],html)
        monsters=[(self.ix.get('creature:goblin-warrior'),4)]
        ctx=encounter.context(self.ix,monsters,engine.evaluate([3]*4,monsters))
        html=pipeline.env().get_template('book/encounter.html.j2').render(
            title=ctx['title'],theme=pipeline.theme('grimoire','encounter','color','a4'),
            paper='a4',sprite=pipeline.sprite(),book=ctx,book_name='encounter',
            body_class='book',scripts=[])
        self.assertIn('Goblin Warrior',html)

    def test_skill_ids_exist(self):
        paths=list((ROOT / '.claude/skills').rglob('SKILL.md'))
        self.assertEqual(len(paths),3)
        for path in paths:
            for ref in re.findall(r'\b(?:class|subclass|spell|creature|term|species|background|magic-item):[a-z0-9/-]+', path.read_text()):
                with self.subTest(path=path, ref=ref):
                    self.assertTrue(self.ix.resolve(ref), ref)

    @unittest.skipUnless(os.environ.get('OCCULT_BROWSER_TESTS')=='1', 'requires Chromium')
    def test_render(self):
        jobs = [('make','cards','spells','--class','wizard','--level','1'),
                ('make','spellbook','--class','cleric'), ('make','class','--class','fighter','--level','3'),
                ('character','characters/examples/rowan-fighter-1.json','--pdf'),
                ('encounter','--party','4x3','goblin-warrior','x4','--pdf')]
        for args in jobs:
            with self.subTest(args=args):
                self.cli(*args)
        for folder in ('cards','books','characters','encounters'):
            pdfs = list((ROOT / 'dist' / folder).glob('*.pdf'))
            self.assertTrue(pdfs, folder)
            self.assertTrue(all(p.read_bytes().startswith(b'%PDF-') for p in pdfs))


class Surface(unittest.TestCase):
    """Every advertised verb, output and filter is executable on the shipped data."""
    @classmethod
    def setUpClass(cls):
        cls.ix = data.load()

    def cli(self, *args):
        result = subprocess.run([str(ROOT / 'occult'), *map(str, args)], cwd=ROOT,
                                text=True, capture_output=True)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn('not in this data set', output)
        return output

    def test_advertised_commands(self):
        from occult import cli
        commands = set(cli.COMMANDS) | set(cli.RULES_COMMANDS) | set(cli.EXTRA_COMMANDS) | {'make'}
        advertised = set(re.findall(r'^  ([a-z]+)\b', self.cli('--help'), re.M))
        self.assertEqual(advertised, commands)
        smoke = {'types': [], 'toc': ['--depth', '1', '--limit', '5'], 'find': ['fireball'],
                 'show': ['spell:fireball', '--brief'], 'list': ['spells', '--limit', '1'],
                 'make': ['--list'], 'character': ['characters/examples/rowan-fighter-1.json'],
                 'encounter': ['--party', '4x3', 'goblin-warrior', 'x4'],
                 'calc': ['cr', '1/4'], 'roll': ['1d6', '--seed', '1'], 'table': ['--list']}
        self.assertEqual(commands, set(smoke))
        for name, args in smoke.items():
            with self.subTest(command=name):
                self.cli(name, *args)
                self.cli(name, '--help')
        # The calc operations and table execution have their own input grammars.
        for args in [('mod', '14'), ('pb', '3'), ('level', '6500'), ('slots', 'wizard=5', 'cleric=3'),
                     ('point-buy', '15', '15', '15', '8', '8', '8'), ('budget', '4x3')]:
            with self.subTest(calc=args):
                self.cli('calc', *args)
        self.cli('table', 'Potion Miscibility', '--seed', '2')
        self.cli('character', 'characters/examples/sel-wizard-3.json', '--json')
        self.cli('character', 'characters/examples/rowan-fighter-1.json', '--level-up', 'fighter')

    def test_outputs(self):
        import tempfile
        from occult.outputs import CATALOGUE
        browser_args = {'cards': ['spell:fireball', '--check-fit'], 'spellbook': ['--class', 'cleric'],
                        'class': ['--class', 'fighter', '--level', '3'],
                        'equipment': [], 'quickref': [], 'glossary': []}
        advertised = {line.split()[0] for line in self.cli('make', '--list').splitlines()}
        self.assertEqual(advertised, set(CATALOGUE))
        self.assertEqual(advertised, set(browser_args) | {'md', 'pwa'})
        with tempfile.TemporaryDirectory() as tmp:
            self.cli('make', 'md', '--check')
            self.cli('make', 'pwa', '--out', str(Path(tmp) / 'pwa'))
        for name in advertised:
            with self.subTest(output=name):
                self.cli('make', name, '--help')
                if name in browser_args and os.environ.get('OCCULT_BROWSER_TESTS') == '1':
                    self.cli('make', name, *browser_args[name])

    def test_types_and_all_filters(self):
        from occult import query
        from occult.types import TYPES
        listed = set(re.findall(r'^([a-z][a-z-]*)\s+\d+\s+', self.cli('types'), re.M))
        self.assertEqual(listed, {t for t in TYPES if self.ix.all(t)})
        # A shipped type registration must have a real entity; the data controls the surface.
        self.assertEqual(set(TYPES), listed)
        self.assertNotIn('--book', self.cli('types'))
        for kind in listed:
            self.cli('list', kind, '--limit', '1')
            self.cli('list', kind, '--ids', '--limit', '1')
            self.cli('list', kind, '--json', '--limit', '1')
            for name, spec in query.listed_filters(kind, self.ix).items():
                if spec.op == 'flag':
                    args = []
                else:
                    values = query.known_values(self.ix, kind, name)
                    if not values:
                        # A free-text filter still accepts a query when no value is populated.
                        values = ['1' if spec.op in ('range', 'cr') else 'a']
                    args = [str(values[0])]
                with self.subTest(kind=kind, filter=name):
                    self.cli('list', kind, '--' + name, *args, '--limit', '1')
                    if '|' in spec.metavar and spec.metavar == spec.metavar.lower():
                        for value in spec.metavar.split('|'):
                            self.cli('list', kind, '--' + name, value, '--limit', '1')

    def test_reference_graph(self):
        from occult.references import unreferenced
        self.assertEqual(unreferenced(ROOT), [])
