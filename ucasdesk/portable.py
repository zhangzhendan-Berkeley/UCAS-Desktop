"""Git-free fixed-revision module downloads and strict patching for portable builds."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import zipfile

from .core import _child_options

MARKERS = {'lecture': 'dist/src/workflow.js', 'selection': 'course_flow.py', 'mooc': 'package.json'}


def ready(root, module):
    if module['id'] == 'iclass':
        return (root / 'ucasdesk/iclass.py').is_file()
    target = root / module['path']
    if module['id'] not in MARKERS:
        return target.is_dir()
    return (target / MARKERS[module['id']]).is_file() and (
        module['id'] != 'mooc' or (root / 'adapters/mooc_helpers.mjs').is_file())


def download(url, expected=None):
    import requests
    if not url.startswith('https://'):
        raise ValueError('Only HTTPS downloads are supported')
    # Normal proxy settings first, then direct HTTPS if that transport fails.
    error = None
    for use_env in (True, False):
        try:
            with requests.Session() as session:
                session.trust_env = use_env
                response = session.get(url, timeout=(15, 120))
                response.raise_for_status()
                content = response.content
            if expected and hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('下载内容 SHA256 不一致，未安装。')
            return content
        except requests.RequestException as exc:
            error = exc
    raise RuntimeError('下载失败，请检查网络后重试：' + url) from error


def archive_url(module):
    match = re.fullmatch(r'https://github.com/([\w.-]+/[\w.-]+?)(?:\.git)?', module['source'])
    if not match or not re.fullmatch('[0-9a-f]{40}', module['commit']):
        raise ValueError('模块来源或固定提交无效')
    return f'https://codeload.github.com/{match[1]}/zip/{module["commit"]}'


def unpack_repo(content, destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in item.filename or ':' in item.filename:
                raise ValueError('压缩包包含非法路径')
            if len(name.parts) < 2:
                continue
            relative = Path(*name.parts[1:])
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination):
                raise ValueError('压缩包越界')
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))


def apply_patch_file(directory, patch_path):
    """Apply our fixed unified diffs. Match every original line; no fuzzy patches."""
    lines = patch_path.read_text(encoding='utf-8').splitlines()
    pos = 0
    while pos < len(lines):
        if not lines[pos].startswith('--- '):
            pos += 1
            continue
        before = lines[pos][4:]
        after = lines[pos + 1][4:]
        if not after.startswith('b/'):
            raise ValueError('不支持的补丁目标')
        target = (directory / after[2:]).resolve()
        if not target.is_relative_to(directory.resolve()):
            raise ValueError('补丁路径越界')
        original = [] if before == '/dev/null' else target.read_text(encoding='utf-8').splitlines()
        output = []
        consumed = 0
        pos += 2
        while pos < len(lines) and not lines[pos].startswith(('diff --git', '--- ')):
            header = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', lines[pos])
            if not header:
                pos += 1
                continue
            start = max(0, int(header[1]) - 1)
            old, new = [], []
            pos += 1
            while pos < len(lines) and not lines[pos].startswith(('@@ ', 'diff --git', '--- ')):
                line = lines[pos]
                if line.startswith(' '): old.append(line[1:]); new.append(line[1:])
                elif line.startswith('-'): old.append(line[1:])
                elif line.startswith('+'): new.append(line[1:])
                elif line.startswith('\\ No newline'): pass
                else: break
                pos += 1
            if len(old) != int(header[2] or 1) or len(new) != int(header[4] or 1):
                raise ValueError('补丁行数校验失败：' + after)
            if start < consumed or original[start:start + len(old)] != old:
                raise ValueError('补丁上下文不匹配：' + after)
            output.extend(original[consumed:start]); output.extend(new)
            consumed = start + len(old)
        output.extend(original[consumed:])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('\n'.join(output) + '\n', encoding='utf-8')


def prepare_lecture(root, directory):
    for name in ('lecture-local.patch', 'lecture-sep-workbench.patch', 'lecture-table.patch', 'lecture-campus.patch'):
        apply_patch_file(directory, root / 'patches' / name)
    for source, destination in [('lecture-register.test.ts', 'tests/register.test.ts'),
                                ('lecture-portal.ts', 'src/portal.ts'), ('lecture-portal.test.ts', 'tests/portal.test.ts'),
                                ('lecture-campus.ts', 'src/campus.ts'), ('lecture-campus.test.ts', 'tests/campus.test.ts')]:
        shutil.copy2(root / 'patches' / source, directory / destination)


def install_module(root, module, manifest, log=print):
    from .core import child_env, NODE
    if ready(root, module):
        log(module['name'] + '已就绪，保留现有模块。')
        return
    target = root / module['path']
    if not target.resolve().is_relative_to((root / 'vendor').resolve()):
        raise ValueError('模块必须安装在 vendor 内')
    if target.exists():
        raise RuntimeError('模块目录不完整，请先备份并移走该目录后重试：' + str(target))
    entry = manifest[module['id']]
    log('正在从上游下载固定版本：' + module['name'], flush=True)
    data = download(archive_url(module), entry['archive_sha256'])
    target.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(prefix='.module-', dir=target.parent) as tmp:
        staging = Path(tmp) / 'source'
        unpack_repo(data, staging)
        if module['id'] == 'lecture':
            prepare_lecture(root, staging)
            shutil.copytree(root / 'runtime/lecture-node/node_modules', staging / 'node_modules')
            log('正在准备讲座模块…', flush=True)
            subprocess.run([str(NODE), str(staging / 'node_modules/typescript/bin/tsc'), '-p', str(staging / 'tsconfig.json')],
                           cwd=staging, env=child_env(), check=True, **_child_options())
        (staging / '.ucas-source.json').write_text(json.dumps({'commit': module['commit'], 'source': module['source']}) + '\n')
        # Only rename into a previously absent, verified target; failed builds stay temporary.
        staging.rename(target)
    log(module['name'] + '已启用。', flush=True)
