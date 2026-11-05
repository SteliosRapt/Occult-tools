/* Book pages: CSS paged media does the layout, so the page only has to say when it is ready
   (after the web fonts and the ornament images have loaded; margin boxes only paint resources
   the document has already loaded). render.mjs waits for body[data-ready]. */
(async () => {
  await document.fonts.ready;
  await Promise.all([...document.images].map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; }))));
  window.__occultStats = { blocks: document.querySelectorAll('.book-body *').length };
  document.body.dataset.ready = '1';
})();
