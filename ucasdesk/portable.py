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

REQUIRED = {
    'lecture': ['dist/src/workflow.js','dist/src/login.js','dist/src/background.js','dist/src/portal.js',
                'dist/src/campus.js','dist/src/config.js','scripts/solve-captcha.py','node_modules/playwright/package.json',
                'node_modules/playwright-core/package.json','node_modules/zod/package.json'],
    'mooc': ['package.json','node_modules/playwright/package.json','node_modules/playwright-core/package.json','node_modules/chalk/package.json'],
    'selection': ['main.py','course_flow.py'],
    'planner': ['src/coursesystem/__init__.py','data/2026年秋季学期课表.xlsx'],
}


def recipe_hash(root, module):
    paths = [root/'ucasdesk/module_build.py'] if module['id'] in ('lecture','mooc') else []
    if module['id']=='lecture': paths += sorted((root/'patches').glob('lecture-*'))
    digest=hashlib.sha256(module['commit'].encode())
    for path in paths:
        digest.update(path.name.encode());digest.update(path.read_bytes().replace(b'\r\n',b'\n'))
    return digest.hexdigest()


def module_issues(root, module):
    if module['id']=='iclass': return [] if (root/'ucasdesk/iclass.py').is_file() else ['课程组件缺失']
    target=root/module['path'];issues=[]
    for relative in REQUIRED.get(module['id'],[]):
        if not (target/relative).is_file():issues.append(relative)
    if module['id']=='mooc' and not (root/'adapters/mooc_helpers.mjs').is_file():issues.append('adapters/mooc_helpers.mjs')
    try:
        stamp=json.loads((target/'.ucas-build.json').read_text(encoding='utf-8'))
        if stamp.get('recipe')!=recipe_hash(root,module):issues.append('组件需要随应用更新重新准备')
    except (OSError,ValueError):issues.append('缺少完整安装记录')
    return issues


def ready(root, module):
    return not module_issues(root,module)


def stamp_module(root, module, target=None):
    target=target or root/module['path']
    (target/'.ucas-build.json').write_text(json.dumps({'commit':module['commit'],'recipe':recipe_hash(root,module)}),encoding='utf-8')


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
    for name in ('lecture-local.patch', 'lecture-sep-workbench.patch', 'lecture-table.patch', 'lecture-campus.patch', 'lecture-browser.patch', 'lecture-captcha-runtime.patch', 'lecture-department.patch', 'lecture-background.patch'):
        apply_patch_file(directory, root / 'patches' / name)
    for source, destination in [('lecture-register.test.ts', 'tests/register.test.ts'),
                                ('lecture-portal.ts', 'src/portal.ts'), ('lecture-portal.test.ts', 'tests/portal.test.ts'),
                                ('lecture-campus.ts', 'src/campus.ts'), ('lecture-campus.test.ts', 'tests/campus.test.ts')]:
        shutil.copy2(root / 'patches' / source, directory / destination)
    from .module_build import prepare_science_lecture
    prepare_science_lecture(directory)


def install_module(root, module, manifest=None, log=print, force=False):
    """Prepare and validate separately; swap only a complete fixed-version module."""
    from .core import child_env, NODE, write_json
    from .module_build import prepare_mooc
    from datetime import datetime
    if ready(root,module) and not force:
        log(module['name']+'已就绪。');return
    target=(root/module['path']).resolve()
    if not target.is_relative_to((root/'vendor').resolve()):raise ValueError('模块必须安装在 vendor 内')
    manifest=manifest or json.loads((root/'modules-downloads.json').read_text(encoding='utf-8'))
    entry=manifest[module['id']]
    if entry['commit']!=module['commit']:raise ValueError('模块校验清单与固定版本不一致')
    cache=root/'data/module-downloads';cache.mkdir(parents=True,exist_ok=True)
    archive=cache/(module['id']+'-'+module['commit']+'.zip')
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest()!=entry['archive_sha256']:
        log('下载固定版本：'+module['name'])
        archive.write_bytes(download(archive_url(module),entry['archive_sha256']))
    target.parent.mkdir(exist_ok=True,parents=True)
    with tempfile.TemporaryDirectory(prefix='.module-',dir=target.parent) as tmp:
        staging=Path(tmp)/'source';unpack_repo(archive.read_bytes(),staging)
        if module['id']=='lecture':prepare_lecture(root,staging)
        if module['id'] in ('lecture','mooc'):
            dependencies=root/'runtime'/(module['id']+'-node')/'node_modules'
            if dependencies.is_dir():shutil.copytree(dependencies,staging/'node_modules')
            else:
                npm=Path(NODE).parent/'node_modules/npm/bin/npm-cli.js'
                command=[str(NODE),str(npm)] if npm.is_file() else [shutil.which('npm.cmd' if __import__('os').name=='nt' else 'npm') or 'npm']
                subprocess.run(command+['ci','--ignore-scripts','--no-audit','--no-fund'],cwd=staging,env=child_env({'PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD':'1'}),check=True,**_child_options())
            if module['id']=='lecture':
                log('构建讲座组件…')
                subprocess.run([str(NODE),str(staging/'node_modules/typescript/bin/tsc'),'-p',str(staging/'tsconfig.json')],cwd=staging,env=child_env(),check=True,**_child_options())
        if module['id'] in ('lecture','mooc'):
            entrypoint='./dist/src/workflow.js' if module['id']=='lecture' else './node_modules/playwright/index.mjs'
            subprocess.run([str(NODE),'--input-type=module','-e','await import('+json.dumps(entrypoint)+')'],cwd=staging,env=child_env(),check=True,timeout=30,**_child_options())
        helper=None
        if module['id']=='mooc':
            generated=Path(tmp)/'generated';(generated/'adapters').mkdir(parents=True)
            prepare_mooc(generated,staging);helper=generated/'adapters/mooc_helpers.mjs'
        missing=[p for p in REQUIRED.get(module['id'],[]) if not (staging/p).is_file()]
        if missing:raise RuntimeError('组件构建不完整：'+', '.join(missing))
        stamp_module(root,module,staging)
        write_json(staging/'.ucas-source.json',{'commit':module['commit'],'source':module['source']})
        backup=root/'data/module-backups'/(module['id']+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        old_helper=(root/'adapters/mooc_helpers.mjs').read_bytes() if helper and (root/'adapters/mooc_helpers.mjs').exists() else None
        moved=False;installed=False
        try:
            if target.exists():backup.parent.mkdir(parents=True,exist_ok=True);target.rename(backup);moved=True
            staging.rename(target);installed=True
            if helper:
                out=root/'adapters/mooc_helpers.mjs';out.parent.mkdir(parents=True,exist_ok=True)
                temporary=out.with_suffix('.mjs.tmp');shutil.copy2(helper,temporary);temporary.replace(out)
        except Exception:
            if installed:target.rename(Path(tmp)/'failed')
            if moved:backup.rename(target)
            if helper and old_helper is not None:(root/'adapters/mooc_helpers.mjs').write_bytes(old_helper)
            raise
    log(module['name']+'已准备完成；原模块如有内容已备份，账号与浏览器登录状态未改动。')
