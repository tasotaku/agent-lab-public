"""No credentials or network: verify Slack opt-in, queues, retries, hooks."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('slack_soliloquy', ROOT / 'tools/slack_soliloquy/slack_soliloquy.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SlackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'
        self.project = Path(self.temp.name) / 'project with spaces'
        self.project.mkdir()
        subprocess.run(['git', 'init', str(self.project)], check=True, capture_output=True)
        self.folder = s.store(self.home, self.project)
        self.config = {'channel': 'CEXAMPLE', 'mode': 'auto', 'schedule': {}}
        s.write(self.folder / 'config.json', self.config)

    def cli(self, *args, body=''):
        with patch('sys.stdin', io.StringIO(body)), patch('sys.stdout', io.StringIO()):
            return s.main([*args, '--home', str(self.home), '--project', str(self.project)])

    def test_off_shift_held_and_no_send(self):
        with patch.object(s, 'post') as post:
            self.cli('draft', '--topic', 'work', body='a decision')
            self.cli('flush', body=json.dumps({'cwd': str(self.project)}))
            post.assert_not_called()
        self.assertEqual(len(list((self.folder / 'held').glob('*.json'))), 1)

    def test_confirm_queues_and_manual_send(self):
        self.config['mode'] = 'confirm'
        s.write(self.folder / 'config.json', self.config)
        with patch.object(s, 'on_shift', return_value=True), patch.object(s, 'post', return_value='123') as post:
            self.cli('draft', '--topic', 'work', body='decision')
            post.assert_not_called()
            self.cli('send')
            self.assertEqual(post.call_count, 2)
        self.assertFalse(list((self.folder / 'outbox').glob('*.json')))

    def test_retry_reuses_created_parent(self):
        with patch.object(s, 'on_shift', return_value=True), patch.object(s, 'post', side_effect=['123', ValueError('failure')]):
            with self.assertRaises(ValueError):
                self.cli('draft', '--topic', 'work', body='decision')
        self.assertEqual(len(list((self.folder / 'outbox').glob('*.json'))), 1)
        with patch.object(s, 'post', return_value='124') as post:
            s.send(self.folder, self.config)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(post.call_args.args[2], '123')

    def test_changed_channel_cannot_retarget_queue(self):
        with patch.object(s, 'on_shift', return_value=True):
            self.config['mode'] = 'confirm'
            s.write(self.folder / 'config.json', self.config)
            self.cli('draft', '--topic', 'work', body='decision')
        self.config['channel'] = 'COTHER'
        with patch.object(s, 'post') as post, self.assertRaises(ValueError):
            s.send(self.folder, self.config)
        post.assert_not_called()

    def test_hooks_preserved_idempotent_and_removed(self):
        for agent in ('claude', 'codex'):
            settings = self.home / ('.claude/settings.json' if agent == 'claude' else '.codex/hooks.json')
            original = {'custom': True, 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo keep'}]}]}}
            s.write(settings, original)
            s.install(self.home, agent)
            first = settings.read_text()
            backups = list((self.home / '.agent-lab-public/backups').glob('*'))
            s.install(self.home, agent)
            self.assertEqual(settings.read_text(), first)
            self.assertEqual(len(list((self.home / '.agent-lab-public/backups').glob('*'))), len(backups))
            s.install(self.home, agent, remove=True)
            result = s.read(settings)
            self.assertTrue(result['custom'])
            self.assertEqual(result['hooks']['Stop'], original['hooks']['Stop'])

    def test_invalid_config(self):
        for config in ({'channel': 'bad', 'mode': 'auto'}, {'channel': 'CEXAMPLE', 'mode': 'bad'},
                       {'channel': 'CEXAMPLE', 'mode': 'auto', 'schedule': {'2026-01-01': [['22:00', '02:00']]}}):
            with self.assertRaises(ValueError):
                s.validate(config)

    def test_shift_boundaries(self):
        from datetime import datetime
        config = {'schedule': {'2026-01-01': [['09:00', '17:00']]}}
        self.assertTrue(s.on_shift(config, datetime(2026, 1, 1, 9)))
        self.assertFalse(s.on_shift(config, datetime(2026, 1, 1, 17)))

    def test_check_installed_and_missing_tool(self):
        s.install(self.home, 'codex')
        with patch.object(s, 'token', return_value='fixture'):
            self.assertEqual(self.cli('check'), 0)
            (self.home / '.agent-lab-public/tools/slack_soliloquy.py').unlink()
            with self.assertRaises(ValueError):
                self.cli('check')

    def test_auto_reuses_thread(self):
        with patch.object(s, 'on_shift', return_value=True), patch.object(s, 'post', return_value='123') as post:
            self.cli('draft', '--topic', 'work', body='first')
            self.cli('draft', '--topic', 'work', body='second')
            self.assertEqual(post.call_count, 3)

    def test_api_payload(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = io.StringIO('{"ok": true, "ts": "123"}')
        with patch.object(s, 'token', return_value='fixture'), patch.object(s.urllib.request, 'urlopen', return_value=response) as urlopen:
            self.assertEqual(s.post('CEXAMPLE', 'decision', '100'), '123')
            request = urlopen.call_args.args[0]
            self.assertEqual(json.loads(request.data)['thread_ts'], '100')
            self.assertEqual(request.full_url, 'https://slack.com/api/chat.postMessage')

    def test_missing_credential_fails_without_network(self):
        s.install(self.home, 'codex')
        with patch.dict('os.environ', {'SLACK_SOLILOQUY_TOKEN': ''}), patch.object(s.sys, 'platform', 'linux'):
            with self.assertRaises(ValueError):
                self.cli('check')

    def test_unconfigured_hook_is_silent(self):
        (self.folder / 'config.json').unlink()
        self.assertEqual(self.cli('remind', body=json.dumps({'cwd': str(self.project)})), 0)

    def test_non_git_hook_is_silent(self):
        self.assertEqual(self.cli('remind', body=json.dumps({'cwd': str(self.home)})), 0)

    def test_parallel_sender_rejected(self):
        with s.lock(self.folder):
            with self.assertRaises(ValueError):
                s.send(self.folder, self.config)


if __name__ == '__main__':
    unittest.main()
