#!/usr/bin/env python3
"""Opt-in, local-configured Slack working notes. Python standard library only."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid
from typing import Any, Iterator, Optional, Sequence, cast

MANAGED_ID = 'agent-lab-public-slack-soliloquy'
KEYCHAIN_SERVICE = 'agent-lab-public-slack-token'


def read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Expected JSON object: ' + str(path))
    return cast(dict[str, Any], value)


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    try:
        temp.chmod(0o600)
    except OSError:
        pass
    temp.replace(path)


def project_root(project: Path) -> Path:
    result = subprocess.run(['git', '-C', str(project), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                            capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise ValueError('Project must be a Git repository')
    return Path(result.stdout.strip()).resolve().parent


def store(home: Path, project: Path) -> Path:
    identity = str(project_root(project))
    key = hashlib.sha256(identity.encode()).hexdigest()
    return home / '.agent-lab-public/slack/projects' / key


def validate(config: dict[str, Any]) -> dict[str, Any]:
    if not re.fullmatch(r'[CG][A-Z0-9]+', config.get('channel', '')):
        raise ValueError('channel must be a Slack channel ID')
    if config.get('mode') not in ('confirm', 'auto'):
        raise ValueError('mode must be confirm or auto')
    schedule = config.get('schedule', {})
    if not isinstance(schedule, dict):
        raise ValueError('schedule must map YYYY-MM-DD to lists of [HH:MM, HH:MM]')
    for day, windows in schedule.items():
        datetime.strptime(day, '%Y-%m-%d')
        if not isinstance(windows, list):
            raise ValueError('schedule windows must be a list')
        for start, end in windows:
            for value in (start, end):
                if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
                    raise ValueError('Invalid schedule time')
            if start >= end:
                raise ValueError('Use separate daily windows for overnight work')
    return config


def on_shift(config: dict[str, Any], now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    return any(start <= now.strftime('%H:%M') < end
               for start, end in config.get('schedule', {}).get(now.strftime('%Y-%m-%d'), []))


def token() -> str:
    value = os.environ.get('SLACK_SOLILOQUY_TOKEN', '').strip()
    if not value and sys.platform == 'darwin':
        result = subprocess.run(['security', 'find-generic-password', '-s', KEYCHAIN_SERVICE, '-w'],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            value = result.stdout.strip()
    if not value:
        raise ValueError('Set SLACK_SOLILOQUY_TOKEN or the dedicated macOS Keychain item')
    return value


def post(channel: str, text: str, thread: Optional[str] = None) -> str:
    payload = {'channel': channel, 'text': text, 'unfurl_links': False, 'unfurl_media': False}
    if thread:
        payload['thread_ts'] = thread
    request = urllib.request.Request('https://slack.com/api/chat.postMessage',
                data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json; charset=utf-8', 'Authorization': 'Bearer ' + token()})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response)
    if not data.get('ok'):
        raise ValueError('Slack API: ' + str(data.get('error', 'unknown_error')))
    return str(data['ts'])


@contextmanager
def lock(folder: Path) -> Iterator[None]:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'send.lock'
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('Sender already active, or interrupted: inspect and remove ' + str(path))
    try:
        os.close(descriptor)
        yield
    finally:
        path.unlink()


def send(folder: Path, config: dict[str, Any], automatic: bool = False) -> None:
    if automatic and (config['mode'] != 'auto' or not on_shift(config)):
        return
    with lock(folder):
        state = read(folder / 'threads.json')
        for path in sorted((folder / 'outbox').glob('*.json')):
            item = read(path)
            # Never send a queue entry to a replacement channel.
            if item['channel'] != config['channel']:
                raise ValueError('Queued channel differs; review local outbox before sending')
            # Automatic retry never publishes notes from a different work day.
            if automatic and item['day'] != datetime.now().strftime('%Y-%m-%d'):
                continue
            key = config['channel'] + ':' + item['topic']
            if key not in state:
                state[key] = post(config['channel'], '▶︎ ' + item['topic'])
                write(folder / 'threads.json', state)
            post(config['channel'], item['text'], state[key])
            path.unlink()
            print('sent: ' + item['topic'])


def hook_command(home: Path, action: str, agent: str) -> dict[str, Any]:
    parts = ['python3', str(home / '.agent-lab-public/tools/slack_soliloquy.py'), action,
             '--home', str(home), '--managed-id', MANAGED_ID]
    posix = ' '.join(shlex.quote(p) for p in parts)
    windows = '& ' + ' '.join("'" + p.replace("'", "''") + "'" for p in ['python'] + parts[1:])
    result: dict[str, Any] = {'type': 'command', 'command': posix, 'timeout': 30}
    if agent == 'codex':
        result['commandWindows'] = windows
    elif sys.platform == 'win32':
        result.update(command=windows, shell='powershell')
    return result


def install(home: Path, agent: str, remove: bool = False) -> None:
    destination = home / '.agent-lab-public/tools/slack_soliloquy.py'
    settings = home / ('.codex/hooks.json' if agent == 'codex' else '.claude/settings.json')
    data = read(settings)
    before = json.dumps(data, sort_keys=True)
    hooks = data.setdefault('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('Existing hooks must be a JSON object')
    for event, action in [('UserPromptSubmit', 'remind'), ('Stop', 'flush')]:
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            raise ValueError('Existing event hooks must be a list')
        cleaned = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get('hooks'), list):
                raise ValueError('Unsupported existing hook shape; left unchanged')
            copy = dict(group)
            copy['hooks'] = [h for h in group['hooks'] if MANAGED_ID not in str(h)]
            if copy['hooks']:
                cleaned.append(copy)
        if not remove:
            cleaned.append({'hooks': [hook_command(home, action, agent)]})
        hooks[event] = cleaned
    if not remove:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if Path(__file__).resolve() != destination.resolve():
            if destination.exists() and destination.read_bytes() != Path(__file__).read_bytes():
                backup = home / '.agent-lab-public/backups' / (str(time.time_ns()) + '-slack-tool.py')
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
            shutil.copy2(__file__, destination)
    if json.dumps(data, sort_keys=True) != before:
        if settings.exists():
            backup = home / '.agent-lab-public/backups' / (str(time.time_ns()) + '-' + agent + '-slack.json')
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(settings, backup)
            print('backup: ' + str(backup))
        write(settings, data)
    print(('removed: ' if remove else 'installed: ') + str(settings))
    if not remove:
        print('MANUAL: approve hooks in the agent when requested; configure each project separately')


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'remove', 'configure', 'check', 'remind', 'draft', 'list', 'send', 'flush'])
    parser.add_argument('--home', type=Path)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--agent', choices=['claude', 'codex'], default='codex')
    parser.add_argument('--channel')
    parser.add_argument('--mode', choices=['confirm', 'auto'], default='confirm')
    parser.add_argument('--schedule', type=Path, help='JSON mapping dates to work windows; local timezone')
    parser.add_argument('--topic')
    parser.add_argument('--managed-id', default=MANAGED_ID)
    args = parser.parse_args(argv)
    home = (args.home or Path.home()).expanduser().resolve()
    if args.action in ('install', 'remove'):
        install(home, args.agent, args.action == 'remove')
        return 0
    project = args.project
    if args.action in ('remind', 'flush'):
        event = json.load(sys.stdin)
        project = Path(event.get('cwd') or project)
    try:
        folder = store(home, project)
    except ValueError:
        if args.action in ('remind', 'flush'):
            return 0
        raise
    if args.action == 'configure':
        config = validate({'channel': args.channel, 'mode': args.mode,
                           'schedule': read(args.schedule) if args.schedule else {}})
        if (folder / 'config.json').exists():
            shutil.copy2(folder / 'config.json', folder / ('config-' + str(time.time_ns()) + '.backup'))
        write(folder / 'config.json', config)
        print('configured: ' + str(folder / 'config.json'))
        return 0
    config = read(folder / 'config.json')
    if not config and args.action in ('remind', 'flush'):
        return 0
    validate(config)
    if args.action == 'check':
        settings = home / ('.codex/hooks.json' if args.agent == 'codex' else '.claude/settings.json')
        hooks = read(settings).get('hooks', {})
        for event in ('UserPromptSubmit', 'Stop'):
            if sum(MANAGED_ID in str(hook) for group in hooks.get(event, []) for hook in group.get('hooks', [])) != 1:
                raise ValueError('Missing or duplicate managed hook: ' + event)
        if not (home / '.agent-lab-public/tools/slack_soliloquy.py').is_file():
            raise ValueError('Installed tool missing; run install')
        print('PASS: installed tool, hooks, project opt-in, channel, mode, schedule syntax')
        print('mode: ' + config['mode'] + '; in work window: ' + str(on_shift(config)))
        token()
        print('PASS: credential available (value hidden)')
        print('UNKNOWN: Slack identity, workspace permission and delivery; no network request made')
        return 0
    if args.action == 'remind':
        if on_shift(config):
            script = home / '.agent-lab-public/tools/slack_soliloquy.py'
            command = [sys.executable, str(script), 'draft', '--home', str(home), '--project', str(project), '--topic', '<topic>']
            print('[Slack独り言] このプロジェクトは投稿対象。本人が会話で示した判断・理由を1〜2文で残す。'
                  '私生活・認証情報・社外秘・自動投稿の設定作業は除く。本人の考えや感情を創作しない。'
                  '本文をstdinに渡して次を実行（topicは同じ作業なら同じ名前）: ' + (subprocess.list2cmdline(command) if sys.platform == 'win32' else ' '.join(shlex.quote(p) for p in command)))
        return 0
    if args.action == 'draft':
        if not args.topic or not args.topic.strip():
            raise ValueError('--topic required')
        text = sys.stdin.read().strip()
        if not text:
            raise ValueError('Draft body on stdin required')
        day = datetime.now().strftime('%Y-%m-%d')
        queue = 'outbox' if on_shift(config) else 'held'
        write(folder / queue / (str(time.time_ns()) + '-' + uuid.uuid4().hex + '.json'),
              {'topic': args.topic, 'text': text, 'channel': config['channel'], 'day': day})
        print('saved: ' + queue)
        if queue == 'outbox':
            send(folder, config, automatic=True)
    elif args.action == 'list':
        for queue in ('outbox', 'held'):
            for path in sorted((folder / queue).glob('*.json')):
                item = read(path)
                print(queue + ' [' + item['topic'] + '] ' + item['text'])
    elif args.action == 'send':
        send(folder, config)
    elif args.action == 'flush':
        send(folder, config, automatic=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        # HTTP errors may contain response text; print only the exception type for network failures.
        message = type(error).__name__ if isinstance(error, urllib.error.URLError) else str(error)
        print('ERROR: ' + message, file=sys.stderr)
        raise SystemExit(1)
