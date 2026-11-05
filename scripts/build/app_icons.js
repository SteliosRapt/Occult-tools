// Rasterize style/icons/app/icon.svg to the PNG app icons beside it (Spell Explorer, `make pwa`).
// Run after changing the SVG: node scripts/build/app_icons.js style/icons/app
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const dir = process.argv[2];
  const svg = fs.readFileSync(path.join(dir, 'icon.svg'), 'utf8');
  const b = await chromium.launch();
  for (const [name, size] of [['icon-192.png', 192], ['icon-512.png', 512], ['apple-touch-icon.png', 180], ['favicon-32.png', 32]]) {
    const p = await b.newPage({ viewport: { width: size, height: size } });
    await p.setContent(`<html><body style="margin:0">${svg.replace('width="512" height="512"', `width="${size}" height="${size}"`)}</body></html>`);
    await p.screenshot({ path: path.join(dir, name), clip: { x: 0, y: 0, width: size, height: size } });
  }
  await b.close();
})();
