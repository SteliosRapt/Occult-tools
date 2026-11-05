/* Card fitting and sheet imposition. Runs in the page; works the same for every theme.
   1. Shrink: step the body font size from --fs-max down to --fs-min (pt, unitless vars on .card).
   2. Trim: elements with data-short swap to their short form.
   3. Continue: if it still overflows, move trailing blocks to a continuation card (a clone with
      class .cont), splitting the boundary block by list item, table row or word. A run keeps one
      font size; if its last card is under 25% full, the run is re-split 0.1pt smaller (floor 6pt).
   Before fitting, items of a .seps list that wrap onto a new line are marked .line-start.
   4. Number runs ("1/2"), then impose each .deck[data-size] onto sheets of cols x rows with crop marks
      (plus a mirrored back sheet after each front when the deck is followed by .back-designs).
   When done it sets window.__occultStats and body[data-ready] (render.mjs waits for it).
   A card is "clipped" if its text still overflows after all of this. */
(async () => {
  await document.fonts.ready;
  const over = (b) => b.scrollHeight > b.clientHeight + 0.5;
  const num = (el, name, dflt) => parseFloat(getComputedStyle(el).getPropertyValue(name)) || dflt;
  const HARD_MIN = 6.0, WIDOW = 0.25;

  const extension = window.occultCardExtension
    ? await window.occultCardExtension({ over, num, fitCard, runOf, fill }) : null;

  function fitCard(card, start, fixed = false) {
    const body = card.querySelector('.c-body');
    if (!body) return;
    const max = start ?? num(card, '--fs-max', 7.5), min = num(card, '--fs-min', 6.4);
    let fs = max;
    body.style.fontSize = fs + 'pt';
    while (!fixed && over(body) && fs > min + 1e-3) {
      fs = Math.max(min, Math.round((fs - 0.1) * 100) / 100);
      body.style.fontSize = fs + 'pt';
    }
    card.dataset.fs = fs;
    if (!over(body)) return;
    const shorts = [...body.querySelectorAll('[data-short]')];
    if (shorts.length && !fixed) {
      shorts.forEach((el) => { el.innerHTML = el.dataset.short; el.removeAttribute('data-short'); });
      card.classList.add('trimmed');
      return fitCard(card);
    }
    if (fixed) return split(card, body, fs);
    // A run: try every size from --fs-max down to the hard floor; keep the fewest cards, then a run
    // whose last card is not a widow (< 25% full), then the largest size. (Shrinking a run to the
    // floor only to strand one box on the next card reads worse than a larger, even split.)
    fs = max;
    const original = body.innerHTML;
    const reset = (f) => {
      runOf(card).slice(1).forEach((c) => c.remove());
      body.innerHTML = original;
      delete card.dataset.clipped;
      body.style.fontSize = f + 'pt';
      card.dataset.fs = f;
    };
    let best = null;
    for (let f = fs; f >= HARD_MIN - 1e-3; f = Math.round((f - 0.1) * 100) / 100) {
      reset(f);
      if (!over(body)) { best = { f, n: 1, ok: true }; break; }
      split(card, body, f);
      const run = runOf(card), n = run.length, ok = fill(run[n - 1]) >= WIDOW;
      if (!best || n < best.n || (n === best.n && ok && !best.ok)) best = { f, n, ok };
    }
    reset(best.f);
    if (over(body)) split(card, body, best.f);
  }
  function runOf(card) {
    const run = [card];
    for (let n = card.nextElementSibling; n && n.classList.contains('cont') && n.dataset.key === card.dataset.key; n = n.nextElementSibling) run.push(n);
    return run;
  }
  function fill(card) {
    const b = card.querySelector('.c-body'), last = b.lastElementChild;
    if (!last) return 0;
    return (last.getBoundingClientRect().bottom - b.getBoundingClientRect().top) / b.clientHeight;
  }

  function split(card, body, fs) {
    const rest = [];
    while (over(body) && body.children.length > 1) rest.unshift(body.removeChild(body.lastElementChild));
    if (over(body)) rest.unshift(body.removeChild(body.lastElementChild));
    if (rest.length) {
      const parts = splitBlock(rest[0], body);
      if (parts) { body.appendChild(parts[0]); rest[0] = parts[1]; }
    }
    if (!body.children.length && rest.length) {
      // nothing fits, not even part of the first block: keep it here (clipped) so the run ends
      body.appendChild(rest.shift());
      card.dataset.clipped = '1';
    }
    if (!rest.length) return;
    const cont = card.cloneNode(true);
    cont.classList.add('cont');
    delete cont.dataset.clipped;
    cont.querySelector('.c-body').replaceChildren(...rest);
    card.after(cont);
    fitCard(cont, fs, true);     // same size as the first card, so the run reads as one text
  }

  // Try to put a head part of `el` at the end of `body`; return [head, tail] or null.
  function splitBlock(el, body) {
    const tag = el.tagName;
    if (tag === 'UL' || tag === 'OL') return splitChildren(el, body, el.children);
    if (tag === 'TABLE') return splitTable(el, body);
    if (tag === 'DIV' && el.children.length === 1) {   // a wrapper such as .c-upcast > p
      const head = el.cloneNode(false); body.appendChild(head);
      const inner = splitBlock(el.firstElementChild, head);
      head.remove();
      if (!inner) return null;
      const tail = el.cloneNode(false);
      head.replaceChildren(inner[0]); tail.replaceChildren(inner[1]);
      return [head, tail];
    }
    return splitInline(el, body);
  }

  function splitChildren(el, body, kids) {
    kids = [...kids];
    const head = el.cloneNode(false); body.appendChild(head);
    let i = 0;
    for (; i < kids.length; i++) { head.appendChild(kids[i]); if (over(body)) { head.removeChild(kids[i]); break; } }
    let partial = null;
    if (i < kids.length) {
      partial = splitInline(kids[i], head, body);
      if (partial) head.appendChild(partial[0]);
    }
    head.remove();
    if (!head.children.length) { kids.forEach((k) => el.appendChild(k)); return null; }
    const tail = el.cloneNode(false);
    if (partial) tail.appendChild(partial[1]);
    kids.slice(partial ? i + 1 : i).forEach((k) => tail.appendChild(k));
    if (el.tagName === 'OL') tail.start = (el.start || 1) + i;
    return [head, tail];
  }

  function splitTable(el, body) {
    const rows = [...el.tBodies[0].rows];
    const head = el.cloneNode(true); head.tBodies[0].replaceChildren(); body.appendChild(head);
    let i = 0;
    for (; i < rows.length; i++) { head.tBodies[0].appendChild(rows[i]); if (over(body)) { head.tBodies[0].removeChild(rows[i]); break; } }
    head.remove();
    if (i < 2) { el.tBodies[0].replaceChildren(...rows); return null; }   // never leave a lone row behind
    const tail = el.cloneNode(true); tail.tBodies[0].replaceChildren(...rows.slice(i));
    tail.classList.add('cont-t');
    return [head, tail];
  }

  // Word-level split of a block with inline content. `parent` is where the probe goes,
  // `body` is the element whose overflow is tested.
  function splitInline(el, parent, body = parent) {
    const units = [];
    el.childNodes.forEach((n) => {
      if (n.nodeType === 3) n.textContent.split(/(?<=\s)/).forEach((w) => units.push(w.replace(/&/g, '&amp;').replace(/</g, '&lt;')));
      else units.push(n.outerHTML);
    });
    const probe = el.cloneNode(false); probe.classList.add('cut'); parent.appendChild(probe);
    let lo = 0, hi = units.length;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      probe.innerHTML = units.slice(0, mid).join('');
      if (over(body)) hi = mid - 1; else lo = mid;
    }
    probe.remove();
    if (lo < 4 || lo >= units.length) return null;   // too little to be worth a split
    const head = el.cloneNode(false), tail = el.cloneNode(false);
    head.innerHTML = units.slice(0, lo).join('');
    tail.innerHTML = units.slice(lo).join('');
    head.classList.add('cut'); tail.classList.add('cont-p');
    return [head, tail];
  }

  function runs() {
    const cards = [...document.querySelectorAll('.card')], out = [];
    for (let i = 0; i < cards.length;) {
      let j = i + 1;
      while (j < cards.length && cards[j].classList.contains('cont') && cards[j].dataset.key === cards[i].dataset.key) j++;
      out.push(cards.slice(i, j));
      i = j;
    }
    return out;
  }
  function numberRuns(all) {
    all.forEach((run) => {
      const n = run.length;
      if (n > 1) run.forEach((c, k) => {
        const slot = c.querySelector('.c-cont');
        if (slot) slot.textContent = `${k + 1}/${n}`;
        if (k < n - 1) c.classList.add('has-next');
      });
    });
  }

  // Impose each deck onto sheets. With category backs (a .back-designs block after the deck),
  // every front sheet is followed by its back sheet: the same grid with the columns mirrored,
  // so a long-edge duplex flip puts each back behind its card.
  function paginate() {
    let sheets = 0, backSheets = 0;
    document.querySelectorAll('.deck[data-size]').forEach((deck) => {
      const cols = +deck.dataset.cols, rows = +deck.dataset.rows, per = cols * rows;
      const cards = [...deck.children];
      const designs = deck.nextElementSibling?.classList.contains('back-designs') ? deck.nextElementSibling : null;
      const sheet = (cls) => {
        const page = document.createElement('div');
        page.className = `sheet-page sheet-${deck.dataset.size}${cls}`;
        const grid = document.createElement('div');
        grid.className = 'grid';
        grid.style.setProperty('--cols', cols); grid.style.setProperty('--rows', rows);
        page.appendChild(grid);
        return [page, grid];
      };
      const marks = (grid) => {
        for (let i = 0; i <= cols; i++) for (const side of ['top', 'bottom']) grid.appendChild(mark('v', side, i));
        for (let j = 0; j <= rows; j++) for (const side of ['left', 'right']) grid.appendChild(mark('h', side, j));
      };
      for (let p = 0; p < cards.length; p += per) {
        const [page, grid] = sheet('');
        const slice = cards.slice(p, p + per);
        slice.forEach((c) => grid.appendChild(c));
        marks(grid);
        deck.before(page);
        sheets++;
        if (!designs) continue;
        const [bpage, bgrid] = sheet(' sheet-backs');
        slice.forEach((c, k) => {
          const d = designs.querySelector(`.card-back[data-back="${CSS.escape(c.dataset.back || '')}"]`);
          const b = d ? d.cloneNode(true) : document.createElement('article');
          if (!d) b.className = `card-back size-${deck.dataset.size} blank`;
          b.style.gridColumn = String(cols - (k % cols));
          b.style.gridRow = String(Math.floor(k / cols) + 1);
          bgrid.appendChild(b);
        });
        marks(bgrid);
        deck.before(bpage);
        backSheets++;
      }
      deck.remove();
      if (designs) designs.remove();
    });
    return [sheets, backSheets];
  }
  function mark(dir, side, i) {
    const m = document.createElement('i');
    m.className = `crop crop-${dir} crop-${side}`;
    m.style.setProperty('--i', i);
    return m;
  }

  function clipped(card) {
    const b = card.querySelector('.c-body');
    return card.dataset.clipped === '1' || (b && over(b)) || card.scrollHeight > card.clientHeight + 0.5;
  }

  // Separated lists (flex rows, .seps: "Very Rare · Requires Attunement · 3 charges"): an item that
  // wraps to start a new line gets .line-start, so the theme can drop its leading separator, and a
  // .sep-break before it, so the line stays broken once the separator is gone.
  document.querySelectorAll('.seps').forEach((list) => {
    [...list.children].forEach((el) => {
      const prev = el.previousElementSibling;
      if (!prev || el.offsetTop <= prev.offsetTop + 1) return;
      const br = document.createElement('i');
      br.className = 'sep-break';
      el.before(br);
      el.classList.add('line-start');
    });
  });

  [...document.querySelectorAll('.card')].forEach((card) => {
    if (extension) extension.fit(card); else fitCard(card);
  });
  const all = runs();
  numberRuns(all);
  const hist = {};
  all.forEach((r) => { hist[r.length] = (hist[r.length] || 0) + 1; });
  const cards = [...document.querySelectorAll('.card')];
  const sizes = cards.map((c) => parseFloat(c.dataset.fs)).filter((x) => !isNaN(x));
  const stats = {
    entities: all.length,
    cards: cards.length,
    runs: hist,
    multi: all.filter((r) => r.length > 1).map((r) => ({ key: r[0].dataset.key, n: r.length })),
    trimmed: cards.filter((c) => c.classList.contains('trimmed')).map((c) => c.dataset.key),
    clipped: [...new Set(cards.filter(clipped).map((c) => c.dataset.key))],
    minFs: sizes.length ? Math.min(...sizes) : null,
    sheets: 0,
    backs: 0,
    ...(extension ? extension.stats() : {}),
  };
  [stats.sheets, stats.backs] = paginate();
  window.__occultStats = stats;
  document.body.dataset.ready = '1';
})();
