import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const page = await readFile(new URL('../mobile/index.html', import.meta.url), 'utf8');

test('mobile panel allows selecting the desktop API endpoint', () => {
  assert.match(page, /id="api-url"/);
  assert.match(page, /sessionStorage\.setItem\(['"]ucasApiUrl/);
  assert.match(page, /new URL\(['"]\/v1\/jobs['"],/);
});
