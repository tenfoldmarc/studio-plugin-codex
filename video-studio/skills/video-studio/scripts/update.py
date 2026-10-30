#!/usr/bin/env python3
"""Native Codex install/update helper. Standard library only; no editing tools are needed.

update.py                  update this plugin
update.py --all            update both Studios that are already installed
update.py --install --all  install Creator Studio, then Script Studio
update.py --check          check for a release without changing installed plugin files
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
PRODUCTS = {
    'video-studio': {'marketplace': 'creator-studio-codex', 'repo': 'tenfoldmarc/studio-plugin-codex',
                     'title': 'Creator Studio'},
    'script-studio': {'marketplace': 'script-studio-codex', 'repo': 'tenfoldmarc/script-studio-codex',
                      'title': 'Script Studio'},
}
PLUGIN_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PRODUCT = PLUGIN_ROOT.name if PLUGIN_ROOT.name in PRODUCTS else 'video-studio'


class UpdateError(Exception):
    pass


def read_json(path):
    try:
        with open(path, encoding='utf-8') as stream:
            return json.load(stream)
    except (OSError, ValueError) as exc:
        raise UpdateError('Could not read plugin metadata.') from exc


def version_at(folder, product):
    manifest = read_json(Path(folder) / 'plugin.json')
    if manifest.get('name') != product or not re.fullmatch(r'\d+\.\d+\.\d+', manifest.get('version', '')):
        raise UpdateError('The plugin manifest has an unexpected identity or version.')
    return manifest['version']


def as_tuple(version):
    return tuple(int(part) for part in version.split('.'))


def codex_program():
    candidates = [os.environ.get('STUDIO_CODEX_EXECUTABLE'), shutil.which('codex'),
                  '/Applications/Codex.app/Contents/Resources/codex',
                  '/Applications/ChatGPT.app/Contents/Resources/codex',
                  str(Path.home() / 'Applications/Codex.app/Contents/Resources/codex')]
    return next((item for item in candidates if item and Path(item).is_file()), None)


def command(args, timeout=120, cwd=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    try:
        result = subprocess.run([str(arg) for arg in args], cwd=cwd, env=env,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError('The command could not complete. Check the connection and installed tools.') from exc
    if result.returncode:
        # Do not echo raw credential-helper output or URLs containing secrets.
        raise UpdateError('The command failed. Check GitHub repository access, Git authentication, and the connection.')
    return result.stdout


def codex_json(executable, *args):
    output = command([executable, 'plugin', *args, '--json'])
    try:
        result = json.loads(output)
    except ValueError as exc:
        raise UpdateError('Codex did not return the expected JSON. Install a current Codex CLI.') from exc
    if not isinstance(result, dict) or result.get('errors'):
        raise UpdateError('Codex could not refresh the requested marketplace. Check repository access and try again.')
    return result


def installed_entry(executable, product):
    selector = product + '@' + PRODUCTS[product]['marketplace']
    entries = codex_json(executable, 'list').get('installed', [])
    return next((entry for entry in entries if entry.get('pluginId') == selector), None)


def marketplace_entry(executable, product):
    name = PRODUCTS[product]['marketplace']
    entries = codex_json(executable, 'marketplace', 'list').get('marketplaces', [])
    return next((entry for entry in entries if entry.get('name') == name), None)


def official_source(value, repo):
    value = str(value or '').rstrip('/').removesuffix('.git')
    return value in (repo, 'https://github.com/' + repo, 'ssh://git@github.com/' + repo, 'git@github.com:' + repo)


def validate_source(market, product):
    source = market.get('marketplaceSource') or {}
    if source.get('sourceType') != 'git' or not official_source(source.get('source'), PRODUCTS[product]['repo']):
        raise UpdateError('This marketplace is not tracking the official Codex repository. Follow the portal installation steps.')


def installed_version(product, codex_dir=None):
    # Local entries are cached under "local", not under the package's version number.
    # Read the manifest itself; directory names and CLI version="local" are not release versions.
    codex_dir = Path(codex_dir or os.environ.get('CODEX_HOME') or Path.home() / '.codex')
    cached = codex_dir / 'plugins/cache' / PRODUCTS[product]['marketplace'] / product / 'local'
    return version_at(cached, product)


def update_one(executable, product, install=False):
    info = PRODUCTS[product]
    entry = installed_entry(executable, product)
    if not entry and not install:
        print(f'STATUS update SKIPPED {info["title"]}: not installed.', flush=True)
        return False
    before = installed_version(product) if entry else None
    market = marketplace_entry(executable, product)
    if not market:
        if not install:
            raise UpdateError('The installed plugin has no tracked marketplace. Follow the portal installation steps.')
        codex_json(executable, 'marketplace', 'add', info['repo'], '--ref', 'main')
        market = marketplace_entry(executable, product)
    if not market:
        raise UpdateError('Codex did not register the marketplace.')
    validate_source(market, product)
    codex_json(executable, 'marketplace', 'upgrade', info['marketplace'])
    market = marketplace_entry(executable, product)
    if not market or not market.get('root'):
        raise UpdateError('Could not find the refreshed marketplace.')
    source_root = Path(market['root']) / product
    expected = version_at(source_root, product)
    if before and as_tuple(expected) < as_tuple(before):
        raise UpdateError('The source is older than the installed release. Refusing to downgrade.')
    result = codex_json(executable, 'add', product + '@' + info['marketplace'])
    destination = result.get('installedPath')
    if not destination or version_at(destination, product) != expected:
        raise UpdateError('The installed files did not match the refreshed release. Update could not be verified.')
    if not installed_entry(executable, product):
        raise UpdateError('Codex did not register the installed plugin.')
    action = 'INSTALLED' if before is None else ('DONE' if before != expected else 'CURRENT')
    print(f'STATUS update {action} {info["title"]} {before or "not installed"} -> {expected}', flush=True)
    return before != expected


def newest(product=DEFAULT_PRODUCT):
    """Read release metadata using the customer's Git credentials, including private repos.

    A sparse temporary clone changes no installed plugin or marketplace. Never switch a
    private installation to an unauthenticated raw.githubusercontent.com version check.
    """
    info = PRODUCTS[product]
    with tempfile.TemporaryDirectory(prefix='studio-release-check-') as scratch:
        target = Path(scratch) / 'release'
        command(['git', 'clone', '--depth=1', '--filter=blob:none', '--sparse', '--branch', 'main',
                 'https://github.com/' + info['repo'] + '.git', target], timeout=45)
        command(['git', '-C', target, 'sparse-checkout', 'set', '--no-cone',
                 '/' + product + '/plugin.json', '/whats-new.json'], timeout=30)
        version = version_at(target / product, product)
        try:
            note = str(read_json(target / 'whats-new.json').get(version) or '')[:200]
        except UpdateError:
            note = ''
        return version, note


def state_dir(product=DEFAULT_PRODUCT):
    app = product + '-codex'
    override = os.environ.get('VIDEO_STUDIO_STATE' if product == 'video-studio' else 'SCRIPT_STUDIO_STATE')
    if override and Path(override).is_absolute():
        return Path(override)
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support' / app
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local') / app
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / app


def check(state=None, force=False):
    product = DEFAULT_PRODUCT
    executable = codex_program()
    if not executable:
        return None
    try:
        if not installed_entry(executable, product):
            return None
        before = installed_version(product)
        cache = Path(state or state_dir(product)) / 'update-check.json'
        today = datetime.date.today().isoformat()
        try:
            saved = read_json(cache)
        except UpdateError:
            saved = {}
        if not force and saved.get('checked') == today:
            latest, note = saved['latest'], saved.get('note', '')
        else:
            latest, note = newest(product)
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps({'checked': today, 'latest': latest, 'note': note}), encoding='utf-8')
            except OSError:
                pass
        if as_tuple(latest) <= as_tuple(before):
            return f'STATUS update NONE ({PRODUCTS[product]["title"]} {before} is current)'
        return (f'STATUS update AVAILABLE {PRODUCTS[product]["title"]} {before} -> {latest}. {note} '
                'Offer the update once. If the user already requested an update, run it without asking again.')
    except (UpdateError, KeyError, TypeError, ValueError):
        return 'STATUS update SKIPPED (release check unavailable; continue with the installed version)'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--all', action='store_true', help='process both Studios, Creator Studio first')
    parser.add_argument('--install', action='store_true', help='also install missing plugins')
    parser.add_argument('--check', action='store_true', help='check this plugin without modifying its installed files')
    parser.add_argument('--force', action='store_true', help='ignore the daily release-check cache')
    args = parser.parse_args(argv)
    if args.check:
        print(check(force=args.force) or 'STATUS update SKIPPED (plugin not installed)', flush=True)
        return 0
    executable = codex_program()
    if not executable:
        print('STATUS update FAILED: Codex CLI was not found. Install it or set STUDIO_CODEX_EXECUTABLE to its absolute path.', flush=True)
        return 2
    products = list(PRODUCTS) if args.all or (args.install and DEFAULT_PRODUCT == 'script-studio') else [DEFAULT_PRODUCT]
    errors = 0
    for product in products:
        try:
            update_one(executable, product, install=args.install)
        except UpdateError as exc:
            errors += 1
            print(f'STATUS update FAILED {PRODUCTS[product]["title"]}: {exc}', flush=True)
    if errors:
        print('Some requested updates failed. Report each result; do not claim both plugins updated.', flush=True)
        return 2
    print('Finished. Start a new Codex chat to load the installed instructions. Saved settings and projects were not changed.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
