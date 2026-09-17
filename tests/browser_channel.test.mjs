import test from 'node:test';
import assert from 'node:assert/strict';
import { browserChannel } from '../adapters/browser_channel.mjs';

const darwinEdge = '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge';
const darwinChrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

test('prefers Edge when it is installed', () => {
  assert.equal(browserChannel('darwin', path => path === darwinEdge || path === darwinChrome), 'msedge');
});

test('falls back to Chrome when only Chrome is installed', () => {
  assert.equal(browserChannel('darwin', path => path === darwinChrome), 'chrome');
});

test('uses the bundled browser when neither is installed', () => {
  assert.equal(browserChannel('darwin', () => false), undefined);
});

test('detects Windows and Linux installs', () => {
  assert.equal(browserChannel('win32', path => path.endsWith('msedge.exe')), 'msedge');
  assert.equal(browserChannel('linux', path => path === '/usr/bin/google-chrome'), 'chrome');
});
