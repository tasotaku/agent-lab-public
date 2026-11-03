# agent-lab-public

[![Cross-platform install](https://github.com/tasotaku/agent-lab-public/actions/workflows/ci.yml/badge.svg)](https://github.com/tasotaku/agent-lab-public/actions/workflows/ci.yml)

Claude CodeとCodexへ、汎用ルールと再利用可能なスキルを安全に導入する公開版です。
private版のknowledge、個人設定、顧客情報、会話履歴、認証情報は含みません。公開内容は
`python tools/audit_public.py` で、作業ツリー・全Git ref・commit messageまで再検査できます。

## Slackへ作業中の独り言を投稿する（任意）

[Slack独り言ツール](tools/slack_soliloquy/README.md)で、Claude Code / Codexの作業中の判断を
話題ごとのSlackスレッドへ共有できます。勤務先の認証・投稿先・勤務日時を各PCで設定します。
既定は下書きのみで、自動投稿は明示的に有効化します。通常のセットアップでは導入しません。

## Codexの定額使用率を記録する（任意）

[使用量モニター](tools/usage_monitor/README.md)を追加しています。Python 3.10以上とCodex CLIの既存ログインを使い、
macOS・Windowsで1分ごとに使用率をCSVへ記録し、約10分の増加量をオフラインのグラフで表示します。
AIの会話は開始しません。記録・認証情報は各PCへ残り、公開リポジトリには入りません。
閾値による警告・AI実行停止は未実装です。通常のセットアップとは独立して、明示的に導入します。

## セッション自動記録フックの廃止

更新後に `python bootstrap.py install` を実行すると、公開版が登録した Claude Code と Codex の記録・再注入フックだけを解除します。作成済みの journal/current と他のフックは保持します。`remove-memory --agent claude` または `remove-memory --agent codex` でも解除できます。旧 `install-memory` は解除へ移行しました。`check-memory`、`memory-record`、`memory-context` は手動操作用に残しています。

## Codex のモデル混雑からの再試行

[再試行ツール](tools/capacity_resume/README.md)は、ローカル履歴に保存された容量不足による失敗を検知し、180秒後に同じチャットへ一度だけ「再開」を送ります。デスクトップが実際に利用している共有 App Server が必要で、通常のインストールでは無効です。

## 3分セットアップ（まず隔離して試す）

前提はGitとPython 3.9以上です。Claude CodeとCodexへのログインは導入後に各アプリで行います。
最初の経路はclone内の `sandbox-home` だけへ導入し、通常のClaude/Codex profileを触りません。
動作確認後に本導入できます。本導入時も既存設定を変更する前に
`~/.agent-lab-public/backups/` へ保存し、管理対象のブロックとスキルだけを更新します。
既存の別スキルは削除しません。

### Windows（PowerShell）

```powershell
git clone https://github.com/tasotaku/agent-lab-public.git
Set-Location agent-lab-public
python bootstrap.py --home "$PWD\sandbox-home" install
python bootstrap.py --home "$PWD\sandbox-home" check
python bootstrap.py --home "$PWD\sandbox-home" smoke
python bootstrap.py --home "$PWD\sandbox-home" targets --format json
```

### macOS / Linux

```bash
git clone https://github.com/tasotaku/agent-lab-public.git
cd agent-lab-public
python3 bootstrap.py --home ./sandbox-home install
python3 bootstrap.py --home ./sandbox-home check
python3 bootstrap.py --home ./sandbox-home smoke
python3 bootstrap.py --home ./sandbox-home targets --format json
```

隔離試用がPASSしたら、通常profileへ本導入します。

```powershell
python bootstrap.py install
python bootstrap.py check
python bootstrap.py smoke
```

macOS/Linuxでは上の `python` を `python3` にします。

正常時、`check` はClaude Code/Codexそれぞれのrules・skillsと再利用ツールを項目別に
`PASS`表示します。`smoke` はインストール先の `test` スキルを実際に読み、利用可能な
capability名とパスを表示します。失敗時は不足項目と次に再実行するコマンドを表示します。

## 対応状況

Windows、macOS、Linuxを同じcommitの公開CIで検査します。上のバッジからmatrixを開けます。
GitHubのraw log画面が未ログイン利用者へsign-inを求める場合も、次の公開Jobs API検査なら認証なしで
同じcommitの各OS・各stepの成否を確認できます。

```bash
python tools/compatibility.py
```

CIは資格情報を使わず、read-only checkoutから隔離homeへ導入します。WindowsではREADMEと同じ
`python`、macOS/Linuxでは同じ `python3` コマンドでinstall、check、smoke、privacy audit、unit testを実行します。

## 公開内容を自分で監査する

clone後、次の1コマンドで公開対象を再検査できます。

```bash
python tools/audit_public.py
```

監査結果は最初に次の5分類を表示します。

- credentials
- personal configuration
- private knowledge / customer data
- conversations
- private dependencies

続いて、走査したGit refs・commits・filesと、問題がある場合のref、path、lineを表示します。
機械処理用には `python tools/audit_public.py --format json` を使えます。

## 入るもの / 入らないもの

入るもの:

- [rules/core.md](rules/core.md): 安全性・スコープ・検証を中心にした汎用ルール
- `skills/shared/`: Claude CodeとCodexで使える共有スキル
- `skills/codex/`: Codex向けに手順が異なるスキルのoverride
- [bootstrap.py](bootstrap.py): 標準ライブラリだけで動くinstall/check/smoke
- [tools/audit_public.py](tools/audit_public.py): 公開payloadとGit履歴の監査
- [tools/slack_soliloquy/](tools/slack_soliloquy/README.md): 勤務日時とプロジェクトで制限するSlack独り言投稿（任意）
- [tools/usage_monitor/](tools/usage_monitor/README.md): Codexの定額使用率の記録とグラフ生成（任意）

入らないもの:

- 個人・顧客・案件のknowledge、journal、対話レビュー
- トークン、cookie、資格情報、通常のClaude/Codex profile
- 個人・勤務先のSlackトークン、チャンネル台帳、勤務予定、会社アカウント設定
- 自動push、会話原本の保存、常駐メニューバーなどprivate運用機能

## 更新と復旧

更新はclone内で `git pull` 後、installとcheckを再実行します。既存ファイルを変更する前の
backupは `~/.agent-lab-public/backups/` に残ります。通常profileを触らず試す場合は、次のように
隔離homeを明示できます。

```bash
python bootstrap.py --home ./sandbox-home install
python bootstrap.py --home ./sandbox-home check
python bootstrap.py --home ./sandbox-home smoke
```

## License

[MIT](LICENSE)
