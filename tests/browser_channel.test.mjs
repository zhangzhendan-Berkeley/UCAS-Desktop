import test from 'node:test';
import assert from 'node:assert/strict';
import { browserChannel, browserLaunchOptions } from '../adapters/browser_channel.mjs';

const darwinEdge = '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge';
const darwinChrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

test('prefers Edge when it is installed', () => {
  assert.equal(browserChannel('darwin', path => path === darwinEdge || path === darwinChrome), 'msedge');
});

test('falls back to Chrome when only Chrome is installed', () => {
  assert.equal(browserChannel('darwin', path => path === darwinChrome), 'chrome');
});

test('reports no channel when neither browser is installed', () => {
  assert.equal(browserChannel('darwin', () => false), undefined);
});

test('detects Windows and Linux installs', () => {
  assert.equal(browserChannel('win32', path => path.endsWith('msedge.exe')), 'msedge');
  assert.equal(browserChannel('linux', path => path === '/usr/bin/google-chrome'), 'chrome');
});

test('launch uses actual executable, including per-user installs; missing browser is explicit', () => {
  assert.equal(browserLaunchOptions('darwin', p=>p.startsWith('/Users/fixture/'),{},'/Users/fixture').executablePath,
    '/Users/fixture/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge');
  assert.equal(browserLaunchOptions('win32',p=>p.startsWith('D:/Apps'),{PROGRAMFILES:'D:/Apps'}).channel,'msedge');
  assert.throws(()=>browserLaunchOptions('darwin',()=>false),/未找到/);
});


test('Linux stable browser names and Chromium use the detected executable', () => {
  for (const [name, channel] of [['microsoft-edge-stable','msedge'],['google-chrome-stable','chrome'],['chromium','chromium'],['chromium-browser','chromium']]) {
    const executablePath = '/usr/bin/' + name;
    assert.deepEqual(browserLaunchOptions('linux', path => path === executablePath), {channel, executablePath});
  }
});

test('Linux prefers Chrome when Edge is also installed', () => {
  assert.equal(browserLaunchOptions('linux', () => true).executablePath, '/usr/bin/google-chrome');
});
