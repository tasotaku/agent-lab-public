#!/usr/bin/env python3
"""Local capacity recovery. No model/heartbeat, no private desktop IPC.

Only an explicitly configured shared App Server control socket may send turns.
An absent connection is a hard failure, never replaced by a second app-server.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

from capacity_resume_policy import is_capacity_error
DEFAULT_STATE = Path.home() / '.agent-lab-public/capacity-resume'


def database(root: Path, prefix: str) -> Path:
    files = list(root.glob(prefix + '_*.sqlite'))
    if not files:
        raise RuntimeError(f'{prefix} database unavailable')
    return max(files, key=lambda p: int(p.stem.rsplit('_', 1)[1]))


@contextmanager
def readonly(path: Path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=3)
    try:
        yield db
    finally:
        db.close()


def failures(home: Path, enabled_at: float) -> list[dict]:
    # Canonical structured history, never grepping transcripts or quoted errors.
    with readonly(database(home, 'state')) as db:
        allowed = {r[0] for r in db.execute('SELECT id FROM threads WHERE archived=0')}
    with readonly(database(home, 'thread_history')) as db:
        rows = db.execute('''SELECT thread_id,turn_id,status,error_json,completed_at
            FROM thread_turns t WHERE completed_at >= ? AND status='failed'
            AND NOT EXISTS (SELECT 1 FROM thread_turns newer
              WHERE newer.thread_id=t.thread_id AND newer.rollout_ordinal>t.rollout_ordinal)''', (enabled_at,))
        result = []
        for tid, turn, status, error, ended in rows:
            try:
                err = json.loads(error) if error else None
            except (TypeError, ValueError):
                continue
            if tid in allowed and is_capacity_error(err):
                result.append(dict(thread_id=tid, turn_id=turn, completed_at=ended))
        return result


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value REAL)')
        self.db.execute('''CREATE TABLE IF NOT EXISTS attempts (
            thread_id TEXT, turn_id TEXT, due REAL, status TEXT, updated REAL,
            result TEXT, PRIMARY KEY(thread_id,turn_id))''')
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('enabled_at',?)", (time.time(),))
        self.db.commit()
        self.enabled_at = self.db.execute("SELECT value FROM meta WHERE key='enabled_at'").fetchone()[0]

    def enqueue(self, item, now):
        self.db.execute("INSERT OR IGNORE INTO attempts VALUES (?,?,?,'pending',?,NULL)",
                        (item['thread_id'], item['turn_id'], item['completed_at'] + 180, now))
        self.db.commit()

    def due(self, now):
        return self.db.execute("SELECT thread_id,turn_id FROM attempts WHERE status='pending' AND due<=?", (now,)).fetchall()

    def claim(self, tid, turn, now):
        # Commit BEFORE network mutation: a crash/timeout must never duplicate a send.
        with self.db:
            cursor = self.db.execute("UPDATE attempts SET status='claimed',updated=? WHERE thread_id=? AND turn_id=? AND status='pending'", (now, tid, turn))
        return cursor.rowcount == 1

    def finish(self, tid, turn, state, result, now):
        with self.db:
            self.db.execute('UPDATE attempts SET status=?,updated=?,result=? WHERE thread_id=? AND turn_id=?',
                            (state, now, result, tid, turn))


def current_failure(thread: dict, turn_id: str, now: float) -> bool:
    if thread.get('status', {}).get('type') != 'idle':
        return False
    turns = thread.get('turns', [])
    if not turns:
        return False
    turn = turns[-1]  # App Server returns oldest-to-newest, unlike desktop read_thread.
    ended = turn.get('completedAt')
    if not isinstance(ended, (float, int)):
        return False
    if ended > 1e12:
        ended /= 1000
    return (turn.get('id') == turn_id and turn.get('status') == 'failed'
            and is_capacity_error(turn.get('error')) and now - ended >= 180)


class SharedServer:
    def __init__(self, codex: str, sock: Path):
        if not sock.exists() or not sock.is_socket():
            raise RuntimeError('shared App Server socket unavailable; desktop stdio cannot be attached')
        # The daemon control socket carries WebSocket frames, NOT JSONL stdio.
        # Connect only to the user-owned Unix socket; no private app-tools pipe.
        from websockets.sync.client import unix_connect
        self.connection = unix_connect(str(sock), uri='ws://localhost/rpc', open_timeout=5)
        self.sequence = 0
        self.notifications = []
        try:
            self.request('initialize', {'clientInfo': {'name': 'agent_lab_capacity_resume', 'version': '1.0.0'}})
            self._send({'method': 'initialized', 'params': {}})
        except Exception:
            self.close()
            raise

    def _send(self, data):
        self.connection.send(json.dumps(data, ensure_ascii=False))

    def request(self, method, params):
        self.sequence += 1
        self._send(dict(id=self.sequence, method=method, params=params))
        until = time.monotonic() + 15
        while time.monotonic() < until:
            item = json.loads(self.connection.recv(timeout=max(0.01, until-time.monotonic())))
            if item.get('id') != self.sequence:
                if 'method' in item and 'id' not in item:
                    self.notifications.append(item)
                    self.notifications = self.notifications[-100:]
                elif 'id' in item and 'method' in item:
                    # Never approve an action on behalf of the user.
                    self._send({'id': item['id'], 'error': {'code': -32601, 'message': 'Observer cannot handle approval requests'}})
                continue
            if 'error' in item:
                raise RuntimeError(f'{method} rejected (code {item["error"].get("code")})')
            return item['result']
        raise TimeoutError(method)

    def read(self, tid):
        thread = self.request('thread/read', {'threadId': tid, 'includeTurns': False})['thread']
        page = self.request('thread/turns/list', {'threadId': tid, 'limit': 1, 'sortDirection': 'desc', 'itemsView': 'notLoaded'})
        thread['turns'] = list(reversed(page['data']))
        return thread

    def send(self, tid):
        # No model, reasoning, cwd, sandbox or permission overrides.
        return self.request('turn/start', {'threadId': tid, 'input': [{'type': 'text', 'text': '再開'}]})

    def close(self):
        self.connection.close()


def step(home: Path, ledger: Ledger, server, now=None):
    now = time.time() if now is None else now
    fresh = failures(home, ledger.enabled_at)
    latest = {(x['thread_id'], x['turn_id']) for x in fresh}
    for item in fresh:
        ledger.enqueue(item, now)
    for tid, turn in ledger.due(now):
        if (tid, turn) not in latest:
            ledger.finish(tid, turn, 'cancelled', 'newer turn or archive', now)
            continue
        if not current_failure(server.read(tid), turn, now):
            ledger.finish(tid, turn, 'cancelled', 'latest live state changed', now)
            continue
        # Read again immediately before claiming. Busy rejects remain terminal, not retried.
        if not current_failure(server.read(tid), turn, now):
            ledger.finish(tid, turn, 'cancelled', 'changed before send', now)
            continue
        if not ledger.claim(tid, turn, now):
            continue
        try:
            response = server.send(tid)
            new_id = response.get('turn', {}).get('id')
            if not new_id:
                raise RuntimeError('missing accepted turn id')
            ledger.finish(tid, turn, 'sent', new_id, now)
        except Exception as exc:
            ledger.finish(tid, turn, 'unknown', type(exc).__name__, now)
            # At-most-once. A lost acknowledgement is not permission to send again.


def check(home, socket, codex):
    failures(home, time.time())
    if not codex:
        raise RuntimeError('codex executable unavailable')
    if socket is None or not socket.exists():
        raise RuntimeError('BLOCKED: no shared desktop App Server socket. No background sender installed.')
    server = SharedServer(codex, socket)
    server.close()
    return {'history': 'PASS', 'shared_connection': 'PASS', 'same_desktop_delivery': 'UNVERIFIED'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['check', 'run', 'status'])
    p.add_argument('--codex-home', type=Path, default=Path(os.environ.get('CODEX_HOME', Path.home()/'.codex')))
    p.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    p.add_argument('--socket', type=Path)
    p.add_argument('--codex', default=shutil.which('codex'))
    args = p.parse_args()
    try:
        if args.command == 'status':
            path = args.state_dir/'ledger.sqlite'
            if not path.exists():
                print(json.dumps({'running': False, 'attempts': []})); return
            with readonly(path) as db:
                print(json.dumps({'attempts': db.execute('SELECT thread_id,turn_id,status,result FROM attempts').fetchall()})); return
        print(json.dumps(check(args.codex_home, args.socket, args.codex)), flush=True)
        if args.command == 'check': return
        args.state_dir.mkdir(parents=True, exist_ok=True)
        import fcntl
        with (args.state_dir/'service.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            ledger = Ledger(args.state_dir/'ledger.sqlite')
            try:
                server = SharedServer(args.codex, args.socket)
                try:
                    while True:
                        step(args.codex_home, ledger, server)
                        time.sleep(1)
                finally:
                    server.close()
            finally:
                ledger.db.close()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
