"""Exercise real Codex Git marketplace install/refresh with a disposable local HTTP remote.

Only a uniquely named test marketplace is registered; finally removes its plugin and source.
The user's HOME, CODEX_HOME, existing plugins and settings are not redirected or replaced.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import threading
import uuid


def run(args, cwd=None):
    args = [shutil.which(args[0]) or args[0], *args[1:]]
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f'{args[:4]}: {result.stdout} {result.stderr}')
    return result.stdout.strip()


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main(compatibility=False):
    market = 'studio-codex-test-' + uuid.uuid4().hex[:10]
    selector = 'smoke-video@' + market
    with tempfile.TemporaryDirectory(prefix='native-smoke-', dir=Path(__file__).parent) as scratch:
        base = Path(scratch).resolve()
        source = base / 'source'
        source.mkdir()
        run(['git', 'init', '-b', 'main'], source)
        run(['git', 'config', 'user.name', 'Studio test'], source)
        run(['git', 'config', 'user.email', 'test@example.invalid'], source)
        plugin = source / 'video-studio'
        (plugin / 'skills/smoke').mkdir(parents=True)
        (plugin / 'skills/smoke/SKILL.md').write_text('---\nname: smoke\ndescription: Disposable plugin validation.\n---\nTest fixture.\n')
        manifest = {'name': 'smoke-video', 'version': '1.0.0', 'description': 'Disposable Studio test'}
        (plugin / 'plugin.json').write_text(json.dumps(manifest))
        if compatibility:
            (plugin / '.codex-plugin').mkdir()
            (plugin / '.codex-plugin/plugin.json').write_text(json.dumps(dict(manifest, skills='./skills/')))
        catalog = {'name': market, 'plugins': [{'name': 'smoke-video', 'source': {'source': 'local', 'path': './video-studio'},
                    'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_USE'}, 'category': 'Productivity'}]}
        (source / '.agents/plugins').mkdir(parents=True)
        (source / '.agents/plugins/marketplace.json').write_text(json.dumps(catalog))
        run(['git', 'add', '.'], source)
        run(['git', 'commit', '-m', 'Fixture v1'], source)
        remote = base / 'remote.git'
        run(['git', 'clone', '--bare', str(source), str(remote)])
        run(['git', 'update-server-info'], remote)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(base)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        registered = False
        try:
            url = f'http://127.0.0.1:{server.server_port}/remote.git'
            result = json.loads(run(['codex', 'plugin', 'marketplace', 'add', url, '--ref', 'main', '--json']))
            registered = True
            print('REGISTER', result, flush=True)
            first = json.loads(run(['codex', 'plugin', 'add', selector, '--json']))
            print('INSTALL', first, flush=True)
            installed = Path(first['installedPath'])
            assert json.loads((installed / 'plugin.json').read_text())['version'] == '1.0.0'
            manifest['version'] = '1.0.1'
            (plugin / 'plugin.json').write_text(json.dumps(manifest))
            if compatibility:
                (plugin / '.codex-plugin/plugin.json').write_text(json.dumps(dict(manifest, skills='./skills/')))
            (plugin / 'marker.txt').write_text('new files arrived')
            run(['git', 'add', '.'], source)
            run(['git', 'commit', '-m', 'Fixture v2'], source)
            run(['git', 'push', str(remote), 'main'], source)
            run(['git', 'update-server-info'], remote)
            refresh = json.loads(run(['codex', 'plugin', 'marketplace', 'upgrade', market, '--json']))
            print('REFRESH', refresh, flush=True)
            second = json.loads(run(['codex', 'plugin', 'add', selector, '--json']))
            installed = Path(second['installedPath'])
            # Codex calls a local-source cache directory "local" regardless of package version.
            assert json.loads((installed / 'plugin.json').read_text())['version'] == '1.0.1'
            assert (installed / 'marker.txt').read_text() == 'new files arrived'
            print('UPDATE', second, flush=True)
            # Codex-specific packaging changes can retain the shared Claude feature
            # version. An explicit update must still install the new source files.
            (plugin / 'marker.txt').write_text('same version packaging update')
            run(['git', 'add', '.'], source)
            run(['git', 'commit', '-m', 'Packaging update with unchanged feature version'], source)
            run(['git', 'push', str(remote), 'main'], source)
            run(['git', 'update-server-info'], remote)
            run(['codex', 'plugin', 'marketplace', 'upgrade', market, '--json'])
            same_version = json.loads(run(['codex', 'plugin', 'add', selector, '--json']))
            installed = Path(same_version['installedPath'])
            assert json.loads((installed / 'plugin.json').read_text())['version'] == '1.0.1'
            assert (installed / 'marker.txt').read_text() == 'same version packaging update'
            print(f'PASS: native Git install and update replaced cached files (compatibility={compatibility}).', flush=True)
        finally:
            if registered:
                run(['codex', 'plugin', 'remove', selector, '--json'])
                run(['codex', 'plugin', 'marketplace', 'remove', market, '--json'])
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
    main(compatibility=True)
