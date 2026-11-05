"""Exercise a small, renumbered, page-free book through the public CLI."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PortableData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        book = root / 'srd-5.2'
        book.mkdir()
        wanted = {'fireball', 'goblin-warrior', 'fighter', 'level-advancement',
                  'carrying-capacity', 'generate-your-scores', 'assign-ability-scores'}
        children = []

        def copy_node(node, keep=False):
            keep = keep or node['id'].rsplit('/', 1)[-1] in wanted
            descendants = [n for c in node.get('children', []) if (n := copy_node(c, keep))]
            if not keep and not descendants:
                return None
            out = dict(node)
            out['id'] = 'srd-5.2/99/' + node['id'].split('/', 2)[-1]
            out['page'] = None
            out['children'] = descendants
            return out

        folders = [p.parent.name for p in (ROOT / 'data').glob('*/book.json')]
        for folder in [f for f in ('phb-2024', 'mm-2025', 'srd-5.2') if f in folders]:
            meta = json.loads((ROOT / 'data' / folder / 'book.json').read_text())
            for item in meta['contents']:
                node = json.loads((ROOT / 'data' / folder / item['file']).read_text())
                for child in node.get('children', []):
                    result = copy_node(child)
                    if result:
                        children.append(result)
        chapter = {'id': 'srd-5.2/99', 'type': 'chapter', 'title': 'Selections',
                   'page': None, 'content': [], 'children': children}
        (book / '99-selections.json').write_text(json.dumps(chapter))
        (book / 'book.json').write_text(json.dumps({'id': 'srd-5.2', 'title': 'SRD',
                                                    'contents': [{'file': '99-selections.json'}]}))
        (book / 'images.json').write_text('[]')
        cls.env = dict(os.environ, OCCULT_DATA=str(root))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([str(ROOT / 'occult'), *args], cwd=ROOT, env=self.env,
                              text=True, capture_output=True)

    def test_reading_and_rules(self):
        for args in [('types',), ('toc',), ('find', 'bat guano'), ('show', 'spell:fireball'),
                     ('list', 'spells'), ('list', 'spells', '--class', 'wizard'), ('calc', 'mod', '14'), ('roll', '1d6'),
                     ('fetch', 'images', '--check')]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn('None', result.stdout)

    def test_missing_table(self):
        for args in [('npc',), ('loot', 'hoard', '--cr', '7')]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('is not in this data set', result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    @unittest.skipUnless(os.environ.get('OCCULT_BROWSER_TESTS') == '1', 'requires Chromium')
    def test_stat_blocks(self):
        result = self.run_cli('encounter', 'goblin-warrior', '--pdf', str(Path(self.tmp.name) / 'encounter.pdf'))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_character(self):
        spec = Path(self.tmp.name) / 'character.json'
        spec.write_text(json.dumps({'classes': [{'class': 'fighter', 'level': 1}],
                                    'abilities': dict.fromkeys(('str', 'dex', 'con', 'int', 'wis', 'cha'), 10)}))
        result = self.run_cli('character', str(spec))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_make_md(self):
        result = self.run_cli('make', 'md', '--out', str(Path(self.tmp.name) / 'collections'))
        self.assertEqual(result.returncode, 0, result.stderr)
