# Codex の容量不足からの再試行

`python tools/capacity_resume/monitor.py check` で共有 App Server の接続条件を確認できます。

Codex デスクトップが実際に使っている共有 Unix ソケットを確認できた場合は、`python -m pip install -r tools/capacity_resume/requirements.txt` で依存を導入し、`python tools/capacity_resume/monitor.py run --socket /path/to/shared.sock` で監視を開始します。デスクトップへの送信は実環境での確認が必要です。Windows ではデスクトップへの接続と再開が未検証です。

ローカル履歴の容量不足による失敗から180秒後、最新ターンがその失敗のままでチャットが待機中なら、同じチャットへ「再開」を一度だけ送ります。監視を始める前の失敗は対象外です。台帳は `~/.agent-lab-public/capacity-resume/ledger.sqlite` に保存します。送信結果が不明なときは自動で再送しません。送信直前に手動で再開した場合には競合の余地があります。
