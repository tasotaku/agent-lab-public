import json
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools/capacity_resume'))
import monitor

class FakeServer:
    def __init__(self, thread): self.thread=thread; self.sent=[]; self.reads=0; self.after_read=None; self.fail=False
    def read(self, tid):
        self.reads+=1
        if self.after_read and self.reads>1: return self.after_read
        return self.thread
    def send(self, tid):
        self.sent.append(tid)
        if self.fail: raise TimeoutError()
        return {'turn': {'id':'resumed'}}

class MonitorTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        with closing(sqlite3.connect(self.root/'state_5.sqlite')) as d, d:
            d.execute('CREATE TABLE threads(id TEXT,archived INTEGER)');d.execute("INSERT INTO threads VALUES ('chat',0)")
        with closing(sqlite3.connect(self.root/'thread_history_1.sqlite')) as d, d:
            d.execute('CREATE TABLE thread_turns(thread_id TEXT,turn_id TEXT,status TEXT,error_json TEXT,completed_at REAL,rollout_ordinal INTEGER)')
        with patch.object(monitor.time,'time',return_value=1000): self.ledger=monitor.Ledger(self.root/'ledger.sqlite')
        self.addCleanup(lambda: self.ledger.db.close())
        self.thread={'id':'chat','status':{'type':'idle'},'turns':[{'id':'failed','status':'failed','completedAt':1010,'error':{'codexErrorInfo':'serverOverloaded'}}]}
        self.server=FakeServer(self.thread)
        self.row('failed','failed',{'codexErrorInfo':'serverOverloaded'},1010,1)
    def row(self,tid,status,error,ended,ordinal):
        with closing(sqlite3.connect(self.root/'thread_history_1.sqlite')) as d, d:
            d.execute('INSERT INTO thread_turns VALUES (?,?,?,?,?,?)',('chat',tid,status,json.dumps(error),ended,ordinal))
    def test_exactly_180_seconds_and_at_most_once(self):
        monitor.step(self.root,self.ledger,self.server,1189.999); self.assertEqual(self.server.sent,[])
        monitor.step(self.root,self.ledger,self.server,1190); self.assertEqual(self.server.sent,['chat'])
        monitor.step(self.root,self.ledger,self.server,1500); self.assertEqual(self.server.sent,['chat'])
        self.assertEqual(self.server.reads,2)
    def test_newer_turn_cancels(self):
        monitor.step(self.root,self.ledger,self.server,1100)
        self.row('new','completed',None,1150,2)
        monitor.step(self.root,self.ledger,self.server,1200);self.assertEqual(self.server.sent,[])
        self.assertEqual(self.ledger.db.execute('SELECT status FROM attempts').fetchone()[0],'cancelled')
    def test_archive_cancels(self):
        monitor.step(self.root,self.ledger,self.server,1100)
        with closing(sqlite3.connect(self.root/'state_5.sqlite')) as d, d:d.execute('UPDATE threads SET archived=1')
        monitor.step(self.root,self.ledger,self.server,1200);self.assertEqual(self.server.sent,[])
    def test_active_waiting_interrupted_and_changed_error_rejected(self):
        for status in ['active','waitingOnApproval','notLoaded','systemError']:
            t={**self.thread,'status':{'type':status}}
            self.assertFalse(monitor.current_failure(t,'failed',1190))
        for status in ['completed','interrupted','inProgress']:
            t={**self.thread,'turns':[{**self.thread['turns'][0],'status':status}]}
            self.assertFalse(monitor.current_failure(t,'failed',1190))
        for message in ['usage_limit_exceeded','authentication_error','safety refusal']:
            t={**self.thread,'turns':[{**self.thread['turns'][0],'error':{'message':message}}]}
            self.assertFalse(monitor.current_failure(t,'failed',1190))
    def test_changed_at_second_read_cancels(self):
        self.server.after_read={**self.thread,'status':{'type':'active'}}
        monitor.step(self.root,self.ledger,self.server,1190);self.assertEqual(self.server.sent,[])
    def test_send_timeout_is_unknown_never_repeated_after_restart(self):
        self.server.fail=True
        monitor.step(self.root,self.ledger,self.server,1190)
        self.ledger.db.close()
        self.ledger=monitor.Ledger(self.root/'ledger.sqlite')
        monitor.step(self.root,self.ledger,self.server,1300)
        self.assertEqual(self.server.sent,['chat'])
        self.assertEqual(self.ledger.db.execute('SELECT status FROM attempts').fetchone()[0],'unknown')
    def test_old_failures_and_quoted_messages_ignored(self):
        self.ledger.enabled_at=1020
        self.assertEqual(monitor.failures(self.root,self.ledger.enabled_at),[])
        self.row('new','failed',{'message':'normal failure','items':[{'text':'Selected model is at capacity'}]},1050,2)
        self.assertEqual(monitor.failures(self.root,1000),[])
    def test_more_than_fifty_threads(self):
        with closing(sqlite3.connect(self.root/'state_5.sqlite')) as d, d:
            d.executemany('INSERT INTO threads VALUES (?,0)',[(f'chat{i}',) for i in range(70)])
        with closing(sqlite3.connect(self.root/'thread_history_1.sqlite')) as d, d:
            d.executemany('INSERT INTO thread_turns VALUES (?,?,?,?,?,?)',[(f'chat{i}',f't{i}','failed',json.dumps({'code':'server_overloaded'}),1010,1) for i in range(70)])
        self.assertEqual(len(monitor.failures(self.root,1000)),71)
    def test_missing_endpoint_is_hard_block_no_spawn(self):
        with patch('subprocess.Popen') as proc:
            with self.assertRaises(RuntimeError): monitor.check(self.root,None,'codex')
            with self.assertRaises(RuntimeError): monitor.SharedServer('codex',self.root/'absent.sock')
            proc.assert_not_called()
    def test_send_payload_has_no_settings_override(self):
        server=object.__new__(monitor.SharedServer);calls=[]
        server.request=lambda method,params:calls.append((method,params)) or {}
        server.send('chat')
        self.assertEqual(calls,[('turn/start',{'threadId':'chat','input':[{'type':'text','text':'再開'}]})])
    def test_concurrent_claim_only_one_sender(self):
        self.ledger.enqueue({'thread_id':'chat','turn_id':'failed','completed_at':1010},1100)
        other=monitor.Ledger(self.root/'ledger.sqlite');self.addCleanup(other.db.close)
        self.assertTrue(self.ledger.claim('chat','failed',1190));self.assertFalse(other.claim('chat','failed',1190))
    @unittest.skipIf(sys.platform == 'win32', 'Unix App Server socket transport')
    def test_shared_websocket_protocol(self):
        import socket,threading
        from websockets.sync.server import unix_serve
        endpoint=self.root/'shared.sock'
        def handle(connection):
            for raw in connection:
                msg=json.loads(raw)
                if 'id' not in msg: continue
                method=msg['method']; params=msg['params']
                if method=='turn/start':
                    self.assertEqual(params,{'threadId':'chat','input':[{'type':'text','text':'再開'}]})
                    result={'turn':{'id':'accepted'}}
                elif method=='thread/read': result={'thread':{'id':params['threadId']}}
                elif method=='thread/turns/list': result={'data':[]}
                else: result={}
                connection.send(json.dumps({'id':msg['id'],'result':result}))
        with unix_serve(handle,str(endpoint)) as fixture:
            worker=threading.Thread(target=fixture.serve_forever,daemon=True);worker.start()
            server=monitor.SharedServer('unused',endpoint)
            try:
                self.assertEqual(server.read('chat'),{'id':'chat','turns':[]})
                self.assertEqual(server.send('chat'),{'turn':{'id':'accepted'}})
            finally: server.close();fixture.shutdown();worker.join(timeout=3)
    def test_millisecond_timestamp_and_chronological_last(self):
        turn={**self.thread['turns'][0],'completedAt':1793665000000}
        t={**self.thread,'turns':[{'id':'previous','status':'completed'},turn]}
        self.assertTrue(monitor.current_failure(t,'failed',1793665180))
        self.assertFalse(monitor.current_failure(t,'previous',1793665180))

if __name__=='__main__': unittest.main()
