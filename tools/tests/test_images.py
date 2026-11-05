"""`./occult fetch images` and occult.images on a temp repo: a fake 5etools-img checkout with two
files and a manifest with one good, one missing and one wrong-hash entry. No network.

Run: python3 -m unittest tools.tests.test_images (or discover tools/tests)
"""
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from occult import fetch, images  # noqa: E402

GOOD = "items/XDMG/Bag of Holding.webp"
WRONG = "bestiary/XMM/Goblin.webp"
ABSENT = "covers/XPHB.webp"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def book(root, name, rows, commit=None):
    d = root / "data" / name
    d.mkdir(parents=True)
    meta = {"id": name, "title": name, "built_from": {"5etools_img_commit": commit} if commit else {}}
    (d / "book.json").write_text(json.dumps(meta))
    (d / "images.json").write_text(json.dumps(rows))


class FetchImages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.root = Path(self.tmp.name)
        self.src, self.img = t / "checkout", t / "repo" / "img"
        self.good = b"good image bytes"
        for rel, body in ((GOOD, self.good), (WRONG, b"not what the manifest says")):
            (self.src / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.src / rel).write_bytes(body)
        entry = {"path": GOOD, "bytes": len(self.good), "sha256": sha(self.good)}
        book(t / "repo", "phb-2024", [
            entry,
            {"path": ABSENT, "bytes": 10, "sha256": sha(b"0123456789")},
            {"path": WRONG, "bytes": 26, "sha256": sha(b"x" * 26)},
        ], commit="678def0a")
        book(t / "repo", "dmg-2024", [entry])

    def tearDown(self):
        self.tmp.cleanup()

    def run_fetch(self, *args, src=True):
        argv = ["images", *args] + (["--from", str(self.src)] if src else [])
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = fetch.main(argv, data_root=self.root / "repo" / "data", img_root=self.img,
                              root=self.root / "repo", env={})
        return code, out.getvalue(), err.getvalue()

    def test_copy_and_missing_report(self):
        code, out, _ = self.run_fetch()
        self.assertEqual(code, 1)
        self.assertIn("fetched 1 (0.0 MB), up to date 0, missing 2", out)
        self.assertIn(f"missing  {ABSENT}  (not in the checkout)", out)
        self.assertIn(f"missing  {WRONG}  (checkout file differs", out)
        self.assertEqual((self.img / GOOD).read_bytes(), self.good)
        self.assertEqual((self.img / GOOD).stat().st_ino, (self.src / GOOD).stat().st_ino)  # hardlinked
        self.assertFalse((self.img / WRONG).exists())
        self.assertFalse((self.img / ABSENT).exists())

    def test_idempotent_and_repairs(self):
        self.run_fetch()
        code, out, _ = self.run_fetch()
        self.assertIn("fetched 0 (0.0 MB), up to date 1, missing 2", out)
        (self.img / GOOD).unlink()
        (self.img / GOOD).write_bytes(b"corrupt bytes, same length")
        code, out, _ = self.run_fetch("--book", "dmg")
        self.assertEqual((code, (self.img / GOOD).read_bytes()), (0, self.good))
        self.assertIn("fetched 1", out)

    def test_check(self):
        code, out, _ = self.run_fetch("--check", src=False)
        self.assertEqual(code, 1)
        self.assertIn("up to date 0, missing 3", out)
        self.assertNotIn("fetched", out)
        self.assertFalse(self.img.exists())               # wrote nothing
        self.run_fetch("--book", "dmg")
        self.assertEqual(self.run_fetch("--book", "dmg", "--check", src=False)[0], 0)
        self.assertEqual(self.run_fetch("--book", "phb", "--check", src=False)[0], 1)

    def test_prune(self):
        self.run_fetch()
        stray = self.img / "stray" / "old.png"
        stray.parent.mkdir(parents=True)
        stray.write_bytes(b"x")
        code, out, _ = self.run_fetch("--check", "--prune", src=False)
        self.assertIn("would prune 1", out)
        self.assertTrue(stray.exists())
        code, out, _ = self.run_fetch("--prune", "--book", "dmg")
        self.assertEqual(code, 0)
        self.assertIn("pruned 1", out)
        self.assertFalse(stray.parent.exists())
        self.assertTrue((self.img / GOOD).exists())       # listed: kept
        self.assertTrue(self.src.joinpath(GOOD).exists())  # outside img/: untouched

    def test_missing_list_is_capped(self):
        rows = [{"path": f"x/{i:02}.webp", "bytes": 1, "sha256": sha(b"%d" % i)} for i in range(25)]
        (self.root / "repo" / "data" / "dmg-2024" / "images.json").write_text(json.dumps(rows))
        code, out, _ = self.run_fetch("--book", "dmg")
        self.assertEqual(out.count("  missing  "), 20)
        self.assertIn("  +5 more", out)

    def test_usage_errors(self):
        self.assertEqual(self.run_fetch("--book", "xyz")[0], 2)
        self.assertEqual(self.run_fetch("--bogus")[0], 2)
        code, _, err = self.run_fetch("--from", str(self.root / "nope"), src=False)
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error: --from"))

    def test_bad_manifest(self):
        (self.root / "repo" / "data" / "dmg-2024" / "images.json").write_text(
            json.dumps([{"path": "../escape.png", "bytes": 1, "sha256": "0" * 64}]))
        code, _, err = self.run_fetch()
        self.assertEqual(code, 1)
        self.assertEqual(len(err.strip().splitlines()), 1)

    def test_helpers(self):
        self.assertEqual(fetch.raw_url("abc", GOOD), fetch.RAW + "/abc/items/XDMG/Bag%20of%20Holding.webp")
        wt = self.root / "main" / ".claude" / "worktrees" / "w"
        wt.mkdir(parents=True)
        (wt / ".git").write_text(f"gitdir: {self.root / 'main' / '.git' / 'worktrees' / 'w'}\n")
        self.assertEqual(fetch.main_repo(wt), self.root / "main")
        self.run_fetch()
        self.assertEqual(images.local_path(GOOD, root=self.img), self.img / GOOD)
        self.assertIsNone(images.local_path(ABSENT, root=self.img))
        self.assertIsNone(images.local_path("../checkout/" + GOOD, root=self.img))


class ManifestCoversData(unittest.TestCase):
    """Every image path the data refers to (node `images`, image blocks, `data.variants[].images`, card
    children, deity symbols, the cover) is in its book's images.json, so `fetch images` copies it."""

    def test_every_referenced_image_is_in_the_manifest(self):
        ext = (".webp", ".png", ".jpg", ".jpeg", ".gif", ".svg")

        def paths(x, out):
            if isinstance(x, dict):
                p = x.get("path")
                if isinstance(p, str) and p.lower().endswith(ext):
                    out.add(p)
                for v in x.values():
                    paths(v, out)
            elif isinstance(x, list):
                for v in x:
                    paths(v, out)
            return out

        books = sorted((TOOLS.parent / "data").glob("*/images.json"))
        self.assertTrue(books)
        for man in books:
            d = man.parent
            with self.subTest(d.name):
                listed = {r["path"] for r in json.loads(man.read_text(encoding="utf-8"))}
                meta = json.loads((d / "book.json").read_text(encoding="utf-8"))
                used = paths(meta, set())
                for c in meta["contents"]:
                    paths(json.loads((d / c["file"]).read_text(encoding="utf-8")), used)
                self.assertEqual(sorted(used - listed), [])


@unittest.skipUnless(images.have_pillow(), "Pillow is not installed (print copies fall back to the source)")
class PrintCopies(unittest.TestCase):
    """images.derived: a copy sized for its box at 300 dpi, JPEG when opaque, palette PNG with the empty
    margins trimmed when transparent, cached by source and box; the source itself when unreadable."""

    def setUp(self):
        from PIL import Image
        self.Image = Image
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cache = self.dir / "cache"

    def tearDown(self):
        self.tmp.cleanup()

    def test_target_px(self):
        self.assertEqual(images.target_px((2000, 1000), (25.4, 25.4)), (300, 150))
        self.assertEqual(images.target_px((100, 400), (25.4, 25.4)), (75, 300))
        self.assertEqual(images.target_px((100, 50), (254, 254)), (100, 50))     # never upscaled

    def test_opaque_becomes_a_sized_jpeg(self):
        src = self.dir / "a.webp"
        self.Image.new("RGB", (2000, 1000), (200, 40, 40)).save(src)
        out, size = images.derived(src, (25.4, 25.4), cache=self.cache)
        self.assertEqual((out.suffix, size), (".jpg", (300, 150)))
        with self.Image.open(out) as im:
            self.assertEqual((im.format, im.size), ("JPEG", (300, 150)))
        self.assertEqual(images.derived(src, (25.4, 25.4), cache=self.cache), (out, size))   # cached
        self.assertNotEqual(images.derived(src, (50.8, 50.8), cache=self.cache)[0], out)    # per box

    def test_cutout_is_trimmed_palette_png(self):
        src = self.dir / "b.webp"
        im = self.Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
        im.paste((10, 120, 30, 255), (250, 400, 750, 600))          # a 500x200 item in the middle
        im.save(src)
        out, size = images.derived(src, (254, 254), cache=self.cache)
        self.assertEqual(out.suffix, ".png")
        self.assertEqual(size, (520, 220))                           # trimmed, 2% of 500 padding
        with self.Image.open(out) as c:
            self.assertEqual(c.mode, "P")

    def test_unreadable_source_is_used_as_is(self):
        src = self.dir / "broken.webp"
        src.write_bytes(b"not an image")
        self.assertEqual(images.derived(src, (25.4, 25.4), cache=self.cache), (src, None))
        self.assertEqual(images.derived(src, None, cache=self.cache), (src, None))


if __name__ == "__main__":
    unittest.main()
