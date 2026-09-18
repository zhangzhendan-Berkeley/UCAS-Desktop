// Select the same installed executable for all Playwright task entry points.
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';

export function candidates(platform = process.platform, env = process.env, home = homedir()) {
  if (platform === 'darwin') return [
    ['msedge', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'],
    ['chrome', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'],
    ['msedge', `${home}/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge`],
    ['chrome', `${home}/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`],
  ];
  if (platform === 'win32') {
    const roots = [env['PROGRAMFILES(X86)'] || 'C:/Program Files (x86)', env.PROGRAMFILES || 'C:/Program Files', env.LOCALAPPDATA].filter(Boolean);
    return [...roots.map(root => ['msedge', `${root}/Microsoft/Edge/Application/msedge.exe`]),
      ...roots.map(root => ['chrome', `${root}/Google/Chrome/Application/chrome.exe`])];
  }
  if (platform === 'linux') return [
    ['msedge', '/usr/bin/microsoft-edge'], ['msedge', '/usr/bin/microsoft-edge-stable'],
    ['chrome', '/usr/bin/google-chrome'], ['chrome', '/usr/bin/google-chrome-stable'],
    ['chromium', '/usr/bin/chromium'], ['chromium', '/usr/bin/chromium-browser'],
  ];
  return [];
}

export function channels(platform = process.platform, exists = existsSync) {
  return candidates(platform).filter(([, path]) => exists(path)).map(([channel]) => channel);
}

export function browserChannel(platform = process.platform, exists = existsSync) {
  return channels(platform, exists)[0];
}

export function browserLaunchOptions(platform = process.platform, exists = existsSync, env = process.env, home = homedir()) {
  const selected = candidates(platform, env, home).find(([, path]) => exists(path));
  if (!selected) throw new Error('未找到 Edge、Chrome 或 Linux Chromium，请安装后重试。macOS 请将浏览器放入 Applications。');
  return {channel: selected[0], executablePath: selected[1]};
}

export function configureWorkflowBrowser() {
  const options = browserLaunchOptions();
  process.env.UCAS_BROWSER_CHANNEL = options.channel;
  process.env.UCAS_BROWSER_EXECUTABLE = options.executablePath;
  return options;
}
