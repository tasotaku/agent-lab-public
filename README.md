# agent-lab-public

[![Cross-platform install](https://github.com/tasotaku/agent-lab-public/actions/workflows/ci.yml/badge.svg)](https://github.com/tasotaku/agent-lab-public/actions/workflows/ci.yml)

Claude CodeとCodexへ、汎用ルールと再利用可能なスキルを安全に導入する公開版です。
private版のknowledge、個人設定、顧客情報、会話履歴、認証情報は含みません。公開内容は
`python tools/audit_public.py` で、作業ツリー・全Git ref・commit messageまで再検査できます。

## セッションの判断経緯をローカルに残す（任意）

この公開版には、セッション終了時に「完了したこと」「判断と理由」「次の作業」を
project別のjournal/currentへ整理し、次回開始時に同じprojectへ再注入する仕組みもあります。
会話原本は保存せず、明記されていない判断を推測しません。通信、外部同期、自動pushは行いません。

通常の `install` と独立したopt-inです。まず隔離homeと対象projectを指定して導入・確認します。

```powershell
python bootstrap.py --home "$PWD\sandbox-home" install-memory --agent claude
python bootstrap.py --home "$PWD\sandbox-home" check-memory --agent claude --project "$PWD"
```

macOS/LinuxまたはCodexでは `python3` と `--agent codex` を使います。Claude Codeは
`~/.claude/settings.json`、Codexは `~/.codex/hooks.json` の既存内容を保ったまま、管理対象の
SessionEnd/SessionStart hookを各1個追加します。

安全な合成eventで終了・開始処理だけを確認できます。`event.json` には `cwd`、一意な
`session_id`、合成JSONLへの `transcript_path` を入れます。JSONLには例えば
`fixture task complete`、`use local journal because fixture must not send externally`、
`Next: verify start injection` の3行を別messageとして入れてください。

```powershell
python bootstrap.py --home "$PWD\sandbox-home" memory-record --agent claude --event event.json
python bootstrap.py --home "$PWD\sandbox-home" memory-context --agent claude --event event.json
python bootstrap.py --home "$PWD\sandbox-home" check-memory --agent claude --project "$PWD"
python bootstrap.py --home "$PWD\sandbox-home" remove-memory --agent claude
```

各コマンドは生成したjournal/currentの絶対path、対象agent/project、hook数を表示します。
同じsession eventを再投入してもentryは増えません。`remove-memory` はこの仕組みのhookだけを外し、
作成済みjournal/currentは利用者データとして保持します。詳しい安全境界は
[SESSION_MEMORY_CONTRACT.md](SESSION_MEMORY_CONTRACT.md) にあります。

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

入らないもの:

- 個人・顧客・案件のknowledge、journal、対話レビュー
- トークン、cookie、資格情報、通常のClaude/Codex profile
- Slack、Keychain、会社アカウントなど個人環境への連携
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
