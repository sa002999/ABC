import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const root = new URL('./', import.meta.url);
const bundled = await build({ absWorkingDir: fileURLToPath(root), entryPoints: ['ui/plan-picker.mjs'], bundle: true, write: false, format: 'esm', platform: 'browser', target: 'es2022', minify: true });
const html = (await readFile(new URL('ui/plan-picker.html', root), 'utf8'))
  .replace('<!-- APP_SCRIPT -->', () => `<script type="module">${bundled.outputFiles[0].text.replace(/<\/script/gi, '<\\/script')}</script>`);
await mkdir(new URL('dist/', root), { recursive: true });
await writeFile(new URL('dist/plan-picker.html', root), html);
await build({ absWorkingDir: fileURLToPath(root), entryPoints: ['tests/host.mjs'], bundle: true, outfile: 'dist/dev-host.js', format: 'esm', platform: 'browser', target: 'es2022' });
console.log('Built dist/plan-picker.html');
const tryOn = await build({ absWorkingDir: fileURLToPath(root), entryPoints: ['ui/try-on.mjs'], bundle: true, write: false, format: 'esm', platform: 'browser', target: 'es2022', minify: true });
await writeFile(new URL('dist/try-on.html', root), (await readFile(new URL('ui/try-on.html', root), 'utf8'))
  .replace('<!-- APP_SCRIPT -->', () => `<script type="module">${tryOn.outputFiles[0].text.replace(/<\/script/gi, '<\\/script')}</script>`));
console.log('Built dist/try-on.html');
