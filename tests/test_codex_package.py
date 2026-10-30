"""Package invariants and updater failure behavior; no account or installed settings are mutated."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = 'video-studio' if (ROOT / 'video-studio').exists() else 'script-studio'
SCRIPTS = ROOT / PRODUCT / 'skills' / PRODUCT / 'scripts'
spec = importlib.util.spec_from_file_location('studio_update_under_test', SCRIPTS / 'update.py')
U = importlib.util.module_from_spec(spec)
spec.loader.exec_module(U)


class PackageTests(unittest.TestCase):
    def test_manifest_and_release_match(self):
        manifest = json.loads((ROOT / PRODUCT / 'plugin.json').read_text())
        compatibility = json.loads((ROOT / PRODUCT / '.codex-plugin/plugin.json').read_text())
        notes = json.loads((ROOT / 'whats-new.json').read_text())
        self.assertEqual(manifest['name'], PRODUCT)
        self.assertEqual(manifest['version'], compatibility['version'])
        self.assertIn(manifest['version'], notes)
        upstream = json.loads((ROOT / PRODUCT / 'upstream.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], upstream['version'])
        catalog = json.loads((ROOT / '.agents/plugins/marketplace.json').read_text())
        self.assertEqual(catalog['name'], U.PRODUCTS[PRODUCT]['marketplace'])
        self.assertEqual(catalog['plugins'][0]['source']['path'], './' + PRODUCT)

    def test_codex_install_has_no_claude_manifest(self):
        self.assertFalse((ROOT / '.claude-plugin').exists())
        self.assertFalse((ROOT / PRODUCT / '.claude-plugin').exists())

    def test_bundled_python_compiles(self):
        for file in (ROOT / PRODUCT).rglob('*.py'):
            with self.subTest(file=str(file.relative_to(ROOT))):
                compile(file.read_text(encoding='utf-8'), str(file), 'exec')


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name)
        self.product = PRODUCT
        self.market = U.PRODUCTS[PRODUCT]['marketplace']

    def manifest(self, folder, version='1.0.1', product=PRODUCT):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'plugin.json').write_text(json.dumps({'name': product, 'version': version}))

    def test_actual_release_is_read_from_local_cache_manifest(self):
        folder = self.base / 'plugins/cache' / self.market / self.product / 'local'
        self.manifest(folder)
        self.assertEqual(U.installed_version(self.product, self.base, entry={'version': 'local'}), '1.0.1')

    def test_versioned_cache_uses_registered_version_not_highest_directory(self):
        folder = self.base / 'plugins/cache' / self.market / self.product
        self.manifest(folder / '1.0.1', version='1.0.1')
        self.manifest(folder / '9.0.0', version='9.0.0')
        self.assertEqual(U.installed_version(self.product, self.base, entry={'version': '1.0.1'}), '1.0.1')

    def test_wrong_product_and_invalid_version_are_rejected(self):
        self.manifest(self.base, product='other-plugin')
        with self.assertRaises(U.UpdateError):
            U.version_at(self.base, self.product)
        self.manifest(self.base, version='local')
        with self.assertRaises(U.UpdateError):
            U.version_at(self.base, self.product)

    def test_official_https_and_ssh_sources(self):
        repo = U.PRODUCTS[self.product]['repo']
        for source in (repo, 'https://github.com/' + repo + '.git', 'git@github.com:' + repo + '.git'):
            self.assertTrue(U.official_source(source, repo))
        self.assertFalse(U.official_source('https://github.com/other/' + self.product, repo))

    def test_untracked_local_source_is_not_silently_replaced(self):
        with self.assertRaises(U.UpdateError):
            U.validate_source({'marketplaceSource': {'sourceType': 'local', 'source': '/tmp/custom'}}, self.product)

    def test_successful_exit_with_refresh_errors_is_failure(self):
        with patch.object(U, 'command', return_value=json.dumps({'errors': ['could not fetch']})):
            with self.assertRaises(U.UpdateError):
                U.codex_json('codex', 'marketplace', 'upgrade', self.market)

    def test_non_json_cli_output_is_failure(self):
        with patch.object(U, 'command', return_value='not JSON'):
            with self.assertRaises(U.UpdateError):
                U.codex_json('codex', 'list')

    def test_missing_plugin_is_skipped_without_installing(self):
        with patch.object(U, 'installed_entry', return_value=None), patch.object(U, 'codex_json') as cli:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(U.update_one('codex', self.product))
            cli.assert_not_called()

    def test_update_verifies_files_and_keeps_external_data(self):
        source = self.base / 'source'
        cached = self.base / 'cached'
        self.manifest(source / self.product)
        self.manifest(cached)
        data = self.base / 'saved-styles.json'
        data.write_text('{"my-style":"keep"}')
        market = {'root': str(source), 'marketplaceSource': {'sourceType': 'git', 'source': U.PRODUCTS[self.product]['repo']}}
        def cli(executable, *args):
            return {'installedPath': str(cached), 'version': 'local'} if args[0] == 'add' else {'errors': []}
        with patch.object(U, 'installed_entry', return_value={'installed': True}), \
             patch.object(U, 'installed_version', return_value='1.0.0'), \
             patch.object(U, 'marketplace_entry', return_value=market), patch.object(U, 'codex_json', side_effect=cli) as calls:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(U.update_one('codex', self.product))
            self.assertEqual([call.args[1] for call in calls.call_args_list], ['marketplace', 'add'])
        self.assertEqual(data.read_text(), '{"my-style":"keep"}')

    def test_does_not_claim_success_for_stale_installed_files(self):
        source = self.base / 'source'
        cached = self.base / 'cached'
        self.manifest(source / self.product, '1.0.2')
        self.manifest(cached, '1.0.1')
        market = {'root': str(source), 'marketplaceSource': {'sourceType': 'git', 'source': U.PRODUCTS[self.product]['repo']}}
        with patch.object(U, 'installed_entry', return_value={'installed': True}), \
             patch.object(U, 'installed_version', return_value='1.0.0'), \
             patch.object(U, 'marketplace_entry', return_value=market), \
             patch.object(U, 'codex_json', return_value={'installedPath': str(cached)}):
            with self.assertRaises(U.UpdateError):
                U.update_one('codex', self.product)

    def test_combined_update_attempts_second_after_first_fails(self):
        calls = []
        def one(executable, product, install=False):
            calls.append(product)
            if product == 'video-studio':
                raise U.UpdateError('Offline')
        with patch.object(U, 'codex_program', return_value='codex'), patch.object(U, 'update_one', side_effect=one):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(U.main(['--all']), 2)
            self.assertIn('FAILED', output.getvalue())
        self.assertEqual(calls, ['video-studio', 'script-studio'])

    def test_offline_release_check_does_not_install_or_block_use(self):
        with patch.object(U, 'codex_program', return_value='codex'), \
             patch.object(U, 'installed_entry', return_value={'installed': True}), \
             patch.object(U, 'installed_version', return_value='1.0.0'), \
             patch.object(U, 'newest', side_effect=U.UpdateError('Offline')), patch.object(U, 'update_one') as update:
            self.assertIn('SKIPPED', U.check(self.base, force=True))
            update.assert_not_called()

    def test_daily_check_preserves_installed_files(self):
        with patch.object(U, 'codex_program', return_value='codex'), \
             patch.object(U, 'installed_entry', return_value={'installed': True}), \
             patch.object(U, 'installed_version', return_value='1.0.0'), \
             patch.object(U, 'newest', return_value=('1.0.1', 'A fix')) as latest:
            self.assertIn('AVAILABLE', U.check(self.base))
            self.assertIn('AVAILABLE', U.check(self.base))
            self.assertEqual(latest.call_count, 1)


if __name__ == '__main__':
    unittest.main()
