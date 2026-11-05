"""Local copies of the art the data refers to (stdlib only).

Image paths in the data (node `images`, `image` blocks, data/<book>/images.json) are relative to the
5etools-img root; `./occult fetch images` copies them to the same relative path under img/
(gitignored). Templates and views use `local_path` and fall back to no image when it is None.
"""
from pathlib import Path

from .data import ROOT

IMG_ROOT = ROOT / "img"


def local_path(rel, root=None):
    """img/<rel> when that file exists, else None. `rel` must stay inside the image root."""
    root = Path(root) if root is not None else IMG_ROOT
    rel = str(rel or "").replace("\\", "/")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or ".." in parts or rel.startswith("/"):
        return None
    p = root.joinpath(*parts)
    return p if p.is_file() else None


# Print copies: each image is embedded at the size it prints. Chromium stores every image it does not
# get as a JPEG as raw pixels (Flate), so a 850x2087 WebP printed 1 inch wide was a 3 MB object.
# `derived` makes, once per source and box, a copy at DPI for that box (never larger than the source):
# opaque art as a JPEG (embedded as is), cut-outs as a 256-colour PNG (alpha kept, about a quarter of
# the pixels' size). Copies live in dist/cache/img/ (gitignored); without Pillow the source is used.
DPI = 300
JPEG_QUALITY = 85
CACHE = ROOT / "dist" / "cache" / "img"
_VERSION = 2                                         # bump when the encoding below changes
_PIL = None


def _pil():
    """PIL.Image, or False when Pillow is not installed (then `derived` returns the source)."""
    global _PIL
    if _PIL is None:
        try:
            from PIL import Image
            _PIL = Image
        except ImportError:
            _PIL = False
    return _PIL


def have_pillow():
    return bool(_pil())


def target_px(size, box_mm, dpi=DPI):
    """The (w, h) that fits `size` (source px) inside box_mm (w, h in mm) at dpi, aspect kept, never
    larger than the source."""
    w, h = size
    bw, bh = (round(v / 25.4 * dpi) for v in box_mm)
    s = min(1.0, bw / w, bh / h)
    return max(1, round(w * s)), max(1, round(h * s))


def _cache_name(src, box_mm, dpi):
    import hashlib
    st = src.stat()
    key = f"{_VERSION}|{src.resolve()}|{st.st_size}|{st.st_mtime_ns}|{box_mm[0]}x{box_mm[1]}|{dpi}"
    return f"{src.stem[:40]}-{hashlib.sha1(key.encode()).hexdigest()[:12]}"


def _size(p):
    with _pil().open(p) as im:
        return im.size


def trim_box(alpha, pad=0.02, floor=8):
    """The bounding box of the visible pixels of an alpha channel (alpha > floor), padded by `pad` of
    the larger side and kept inside the image; None when nothing is visible."""
    bb = alpha.point(lambda v: 255 if v > floor else 0).getbbox()
    if not bb:
        return None
    w, h = alpha.size
    d = round(max(bb[2] - bb[0], bb[3] - bb[1]) * pad)
    return max(0, bb[0] - d), max(0, bb[1] - d), min(w, bb[2] + d), min(h, bb[3] + d)


def derived(src, box_mm, dpi=DPI, cache=None):
    """The print copy of image file `src` for a box of box_mm (w, h in mm) -> (path, (w, h) px): a
    cached JPEG (opaque) or palette PNG (transparent, its empty margins trimmed so a cut-out fills its
    frame), or (src, None) without Pillow or when the file cannot be read."""
    src = Path(src)
    Image = _pil()
    if not Image or not box_mm:
        return src, None
    cache = Path(cache) if cache is not None else CACHE
    name = _cache_name(src, box_mm, dpi)
    for ext in (".jpg", ".png"):
        if (cache / (name + ext)).is_file():
            return cache / (name + ext), _size(cache / (name + ext))
    try:
        im = Image.open(src)
        im.load()
    except OSError:
        return src, None
    alpha = "A" in im.getbands() or "transparency" in im.info
    if alpha:
        im = im.convert("RGBA")
        alpha = im.getchannel("A").getextrema()[0] < 250
        bb = trim_box(im.getchannel("A")) if alpha else None
        if bb and bb != (0, 0) + im.size:
            im = im.crop(bb)
    im = im.convert("RGBA" if alpha else "RGB")
    size = target_px(im.size, box_mm, dpi)
    if size != im.size:
        im = im.resize(size, Image.LANCZOS)
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / (name + (".png" if alpha else ".jpg"))
    tmp = out.with_name(out.name + ".tmp")
    if alpha:
        im.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG).save(
            tmp, "PNG", optimize=True)
    else:
        im.save(tmp, "JPEG", quality=JPEG_QUALITY, optimize=True)
    tmp.replace(out)                                 # atomic: a parallel render never reads half a file
    return out, size
