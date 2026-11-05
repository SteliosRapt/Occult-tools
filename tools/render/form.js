/* Form overlays (the official character sheet): every value must stay inside its printed box.
   .fit      one line: the font shrinks until the text fits the box's width (down to MIN_LINE pt).
   .fit-box  a text box: the font shrinks until it fits (down to MIN_BOX pt); if it still overflows,
             each entry keeps only its first paragraph (class `firsts`), then only its title (class
             `titles`), fitting again each time.
   Stats: {fields, shrunk, firsts, titles, clipped: [class names], minFs}. render.mjs waits for body[data-ready]. */
(async () => {
  const MIN_LINE = 5, MIN_BOX = 5.5, STEP = 0.25;
  await document.fonts.ready;
  const pt = (el) => parseFloat(getComputedStyle(el).fontSize) * 0.75;
  // Bottom-aligned cells overflow upwards, which scrollHeight misses: measure the text itself too.
  const over = (el) => {
    if (el.scrollWidth > el.clientWidth + 0.5 || el.scrollHeight > el.clientHeight + 0.5) return true;
    const r = document.createRange();
    r.selectNodeContents(el);
    const t = r.getBoundingClientRect(), b = el.getBoundingClientRect();
    return t.height > 0 && (t.top < b.top - 0.5 || t.bottom > b.bottom + 0.5 || t.left < b.left - 0.5 || t.right > b.right + 0.5);
  };
  const shrink = (el, min) => {
    let fs = pt(el);
    while (over(el) && fs - STEP >= min) { fs -= STEP; el.style.fontSize = fs + 'pt'; }
    return fs;
  };
  const st = { fields: 0, shrunk: 0, firsts: 0, titles: 0, clipped: [], minFs: null };
  const note = (el, start, fs) => {
    st.fields++;
    if (fs < start) { st.shrunk++; st.minFs = Math.min(st.minFs ?? fs, fs); }
    if (over(el)) st.clipped.push(el.className);
  };
  for (const el of document.querySelectorAll('.fit')) {
    if (!el.textContent.trim()) continue;
    const start = pt(el);
    note(el, start, shrink(el, MIN_LINE));
  }
  for (const el of document.querySelectorAll('.fit-box')) {
    if (!el.textContent.trim()) continue;
    const start = pt(el);
    let fs = shrink(el, MIN_BOX);
    for (const cut of ['firsts', 'titles']) {
      if (!over(el) || !el.querySelector(cut === 'firsts' ? '.entry p + p' : '.entry p')) continue;
      el.classList.remove('firsts');
      el.classList.add(cut);
      el.style.fontSize = start + 'pt';
      fs = shrink(el, MIN_BOX);
    }
    for (const cut of ['firsts', 'titles']) if (el.classList.contains(cut)) st[cut]++;
    note(el, start, fs);
  }
  window.__occultStats = st;
  document.body.dataset.ready = '1';
})();
