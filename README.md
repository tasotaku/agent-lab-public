# agent-lab-public

[![Cross-platform install](https://github.com/tasotaku/agent-lab-public/actions/workflows/ci.yml/badge.svg)](https://github.com/tasotaku/agent-lab-public/actions/workflows/ci.yml)

Claude CodeとCodexへ、汎用ルールと再利用可能なスキルを安全に導入する公開版です。
private版のknowledge、個人設定、顧客情報、会話履歴、認証情報は含みません。公開内容は
`python tools/audit_public.py` で、作業ツリー・全Git ref・commit messageまで再検査できます。

## 3分セットアップ

前提はGitとPython 3.9以上です。Claude CodeとCodexへのログインは導入後に各アプリで行います。
インストーラーは既存設定を変更する前に `~/.agent-lab-public/backups/` へ保存し、管理対象の
ブロックとスキルだけを更新します。既存の別スキルは削除しません。

### Windows（PowerShell）

```powershell
git clone https://github.com/tasotaku/agent-lab-public.git
Set-Location agent-lab-public
python bootstrap.py install
python bootstrap.py check
python bootstrap.py smoke
```

### macOS / Linux

```bash
git clone https://github.com/tasotaku/agent-lab-public.git
cd agent-lab-public
python3 bootstrap.py install
python3 bootstrap.py check
python3 bootstrap.py smoke
```

正常時、`check` はClaude Code/Codexそれぞれのrules・skillsと再利用ツールを項目別に
`PASS`表示します。`smoke` はインストール先の `test` スキルを実際に読み、利用可能な
capability名とパスを表示します。失敗時は不足項目と次に再実行するコマンドを表示します。

## 対応状況

Windows、macOS、Linuxを同じcommitの公開CIで検査します。上のバッジからmatrixを開くと、
各OSのinstall、check、smoke、privacy audit、unit testを確認できます。CIは資格情報を使わず、
隔離したhomeへだけ導入します。

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
- 自動push、会話保存、常駐メニューバーなどprivate運用機能

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

