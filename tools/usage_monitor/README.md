# Codexの定額使用率を記録・グラフ表示する

Codex CLIの既存ログインを使い、アカウント全体の定額プラン使用率を1分ごとに記録します。
AIの会話は開始せず、APIキーは不要です。Python 3.10以上とCodex CLIが必要です。
このツールは明示的に導入する任意機能で、通常の `bootstrap.py install` では起動しません。

**現在は記録・グラフ表示までです。閾値を超えた際の警告とAI実行の停止は未実装です。**
Claudeの定額プラン使用率は取得しません。

## 導入と確認

Windows（PowerShell）：

```powershell
git clone https://github.com/tasotaku/agent-lab-public.git
Set-Location agent-lab-public
codex login
python tools/usage_monitor/codex_usage.py install --plan 'ChatGPT Pro $200'
python tools/usage_monitor/codex_usage.py check --plan 'ChatGPT Pro $200'
python tools/usage_monitor/graph.py
```

macOS：

```bash
git clone https://github.com/tasotaku/agent-lab-public.git
cd agent-lab-public
codex login
python3 tools/usage_monitor/codex_usage.py install --plan 'ChatGPT Pro $200'
python3 tools/usage_monitor/codex_usage.py check --plan 'ChatGPT Pro $200'
python3 tools/usage_monitor/graph.py
```

既にclone・ログイン済みなら該当手順を省略できます。Codex CLIが未導入でNode.jsがある場合は
`npm install -g @openai/codex` で導入します。プラン名は本人が指定するラベルで、APIから価格を推定しません。
省略時のラベルは `ChatGPT`。自分の契約に合わせて `--plan` を変更してください。

Windowsは通常ユーザーのタスク、macOSはLaunchAgentへ登録します。管理者権限・パスワード保存・
スリープ解除は使いません。ログイン中に動作し、スリープ中は記録できません。
Linuxは `once` とグラフ生成を利用できますが、自動登録は未提供です。

## グラフを見る

出力先は `~/.agent-lab/usage-monitor/usage-graph.html`。
Windowsでは `%USERPROFILE%\.agent-lab\usage-monitor\usage-graph.html` です。
ブラウザで開くと、使用率と直近約10分の増加ポイントを上下に表示します。
全体・24時間・6時間・1時間の切り替えと、カーソル／タップによる記録詳細の表示ができます。
追加ライブラリやネット接続は不要です。AIに「使用量をグラフにして」と依頼する場合も、この入口で生成します。
最新記録を見るには再生成します。

```bash
python3 tools/usage_monitor/graph.py --csv /path/to/codex-usage.csv --output /path/to/usage-graph.html
```

Windowsでは `python3` を `python` に置き換えます。別PCの履歴は自動集約されません。

## 記録の意味

CSVは同じフォルダの `codex-usage.csv`、動作ログは `collector.log` に保存します。
これらは各PCのローカルデータであり、この公開リポジトリには含みません。

| 列 | 意味 |
|---|---|
| `observed_at` | 観測時刻（日本時間） |
| `account` | アカウント識別子のハッシュ。メール・認証情報は保存しない |
| `declared_plan` | 本人が指定したプラン名 |
| `bucket`, `window`, `window_minutes` | 使用枠と期間。週間枠は10080分 |
| `resets_at` | リセット予定時刻（Unix秒） |
| `used_percent` | 使用済みの割合（%） |
| `delta_10m_points` | 約10分の増加ポイント。24%→26%なら2 |
| `measured_seconds` | 差分比較の実際の間隔（通常600秒前後） |
| `status` | `ok`、`warming_up`、`gap`、`counter_decreased`、`fetch_error` |

同じアカウント・使用枠・リセット期間の約10分前と比較します。90秒を超える記録の空白、
比較期間が690秒超、取得失敗、リセット、使用率の減少では比較を作り直します。
不明な使用率・差分を0として扱いません。グラフの灰色は記録間隔が90秒を超えた区間です。

使用率は**アカウント全体**の値です。記録したPC・特定のチャットだけの消費量ではありません。
トークン数・API料金には換算しません。提供側の丸めや反映遅れがあるため、10分の増加量は近似です。

## 状態確認・停止・更新

```bash
python3 tools/usage_monitor/codex_usage.py status
python3 tools/usage_monitor/codex_usage.py stop
git pull --ff-only
```

Windowsの `stop` はタスク登録を解除し、履歴を残します。
macOSの `stop` は現在の記録を止めます。次回ログイン時も止める場合は
`~/Library/LaunchAgents/com.agent-lab.codex-usage.plist` を削除します。
更新後はinstall/checkを再実行してください。独自配置のCLIは `--codex` で指定できます。

private版と公開版のcollectorは同じタスク名・保存先を使います。同じPCで二重に導入せず、
移行時は元のcollectorを停止してから新しいcloneで導入してください。履歴は継続利用できます。

## 検証範囲

公開CIで合成CSVからのグラフ生成をmacOS・Windows・Linuxで検証します。
Windowsは `verify-windows.ps1` で、合成応答を返す実行ファイルを使い、プロセス起動・
ファイルロック・タスク登録・記録・グラフ生成・停止まで検証します。
認証情報やAI実行は使いません。本人の契約での取得は各PCの `check` で確認してください。

取得メソッドはCodex App Serverの `account/read` と `account/rateLimits/read` です。
[公式ドキュメント](https://learn.chatgpt.com/docs/app-server#auth-endpoints)
