// Pick a Playwright browser channel from the browsers actually installed.
// Windows ships Edge, macOS may have neither Edge nor Chrome, Linux varies;
// an undefined channel tells Playwright to use its own bundled Chromium.
import { existsSync } from 'node:fs';

const CANDIDATES = {
  darwin: [
    ['msedge', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'],
    ['chrome', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'],
    ['chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium'],
  ],
  win32: [
    ['msedge', `${process.env['PROGRAMFILES(X86)'] || 'C:/Program Files (x86)'}/Microsoft/Edge/Application/msedge.exe`],
    ['chrome', `${process.env.PROGRAMFILES || 'C:/Program Files'}/Google/Chrome/Application/chrome.exe`],
  ],
  linux: [
    ['msedge', '/usr/bin/microsoft-edge'],
    ['chrome', '/usr/bin/google-chrome'],
    ['chrome', '/usr/bin/chromium'],
  ],
};

export function channels(platform = process.platform, exists = existsSync) {
  return (CANDIDATES[platform] || CANDIDATES.linux)
    .filter(([, path]) => exists(path))
    .map(([channel]) => channel);
}

export function browserChannel(platform = process.platform, exists = existsSync) {
  return channels(platform, exists)[0];
}
