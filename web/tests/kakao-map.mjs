import assert from 'node:assert/strict';
import ts from 'typescript';
import { readFileSync } from 'node:fs';
async function moduleWithKey(key) {
  const source = readFileSync(new URL('../lib/kakao-map.ts', import.meta.url), 'utf8').replace('import.meta.env.VITE_KAKAO_MAP_JS_KEY', JSON.stringify(key));
  const built = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  return import('data:text/javascript;base64,' + Buffer.from(built.outputText).toString('base64'));
}
const absent = await moduleWithKey('');
await assert.rejects(absent.loadKakaoMap(), /JavaScript/);
const scripts = [];
globalThis.document = { createElement: () => ({ remove() {} }), head: { appendChild(s) { scripts.push(s); } } };
const maps = { load(callback) { callback(); } };
globalThis.window = { kakao: { maps } };
const sdk = await moduleWithKey('test-key-not-real');
const a = sdk.loadKakaoMap(), b = sdk.loadKakaoMap();
assert.equal(a, b);
assert.equal(scripts.length, 1);
assert.match(scripts[0].src, /^https:\/\/dapi.kakao.com\/v2\/maps\/sdk.js\?/);
scripts[0].onload();
assert.equal(await a, maps);
const failed = await moduleWithKey('test-failure-not-real');
const c = failed.loadKakaoMap();
scripts.at(-1).onerror();
await assert.rejects(c, /불러오지/);
console.log('Kakao SDK loader: 6 checks passed (mock SDK, no real requests)');
