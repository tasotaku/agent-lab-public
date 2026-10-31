# Slackへ作業中の独り言を投稿する（任意）

Claude Code / Codexのメイン会話が、本人が示した判断と理由を1〜2文で下書きし、話題ごとの
Slackスレッドへ投稿します。追加のAI呼び出しや会話ログの再読込はありません。
各プロジェクトを明示的に有効化し、勤務日時と投稿先を各PCで設定します。
通常の `bootstrap.py install` では導入されません。

Python 3.9以上、Git、Slackアプリの投稿権限が必要です。macOSでローカル検証済み。
Windows/Linuxは公開CIで同じ合成テストを実行します。実際のエージェントによる下書き生成と
Slack配送は勤務先の認証・hook承認後に確認してください。

## 導入

```bash
git clone https://github.com/tasotaku/agent-lab-public.git
cd agent-lab-public
python3 tools/slack_soliloquy/slack_soliloquy.py install --agent codex
```

Claude Codeでは `--agent claude`、Windows PowerShellでは `python3` を `python` に変更します。
両方使う場合はそれぞれ実行します。既存hookは保持し、変更前の設定と更新前のツールは
`~/.agent-lab-public/backups/` に保存します。エージェントがhook承認を求めたら本人が確認します。
`--home ./sandbox-home` を付ければ隔離homeに試せます。

## 勤務先ごとの認証とプロジェクト設定

勤務先で承認されたSlackアプリを作り、投稿先ワークスペースで新しく認証します。
[chat.postMessageの公式説明](https://docs.slack.dev/reference/methods/chat.postMessage/)に従い、
User TokenまたはBot Tokenへ `chat:write` を付け、投稿先チャンネルへ参加してください。
User Tokenは本人名義、Bot Tokenはアプリ名義になります。
過去の勤務先のトークン・設定は読み込みません。

トークンは環境変数 `SLACK_SOLILOQUY_TOKEN` をエージェント起動前の環境に設定します。
環境変数を設定したターミナルからエージェントを起動してください。
macOSでは「キーチェーンアクセス」で種類「アプリケーションパスワード」、サービス名
`agent-lab-public-slack-token` の項目を作る方法もあります。トークンをGitやコマンド履歴へ入れないでください。

勤務日時はGit外のJSONファイルへ保存します。日付は各PCのローカル日時です。
例の日時を実際の勤務日に置き換えます。日付をまたぐ勤務は日別に分けます。
空の予定は自動投稿を停止します。

```json
{
  "2026-11-02": [["09:00", "12:00"], ["13:00", "18:00"]]
}
```

```bash
python3 tools/slack_soliloquy/slack_soliloquy.py configure --project /path/to/work-repo --channel CEXAMPLE --schedule /path/to/schedule.json
python3 tools/slack_soliloquy/slack_soliloquy.py check --project /path/to/work-repo --agent codex
```

`CEXAMPLE` はSlackでコピーしたチャンネルIDに置き換えます。プロジェクトはGitリポジトリが必要です。
設定・下書き・スレッドIDはユーザーhome内の `.agent-lab-public/slack/` に保存し、リポジトリには書き込みません。
同じGit worktree群は同じ設定を使います。別cloneや別PCは個別に設定します。
`configure` は予定全体を差し替え、既存設定を同じフォルダへbackupします。

初期値 `confirm` は下書きだけです。勤務時間内に会話で作業の判断をした後、次で確認して送信できます。

```bash
python3 tools/slack_soliloquy/slack_soliloquy.py list --project /path/to/work-repo
python3 tools/slack_soliloquy/slack_soliloquy.py send --project /path/to/work-repo
```

`send` はoutbox全件の明示的な送信です。勤務時間外でも実行できます。
自動投稿にするには、同じ設定コマンドへ `--mode auto` を付けます。
勤務時間外の下書きは `held` に保存し、自動でも `send` でも送りません。
当日以外のoutboxも自動再送しません。`list` で本文を確認したうえで `send` を使います。
AIには私生活・認証情報・社外秘を含めず、本人が示していない考えや感情を創作しないよう指示します。
下書きの内容判断にはAIが関わるため、最初は `confirm` で勤務先に合うことを確認してください。

## 動作と確認範囲

勤務日時内のUserPromptSubmit hookが下書きコマンドをAIへ案内します。
`auto` なら下書き作成時に送信し、Stop hookが当日分の失敗を再送します。
同じ話題は同じスレッドを再利用します。投稿先を変えた場合、以前のチャンネル向け下書きは
送信を止めます。自動的な宛先変更はしません。
通信失敗時は下書きを保持しますが、Slackが受信した直後に応答が失われた場合などは
再試行で重複する可能性があります。`send.lock` が残った場合は他の送信プロセスがないことを
確認してからそのファイルだけを削除します。

`check` は導入済みツール、hook、設定と認証情報の存在を確認します。
ネットワーク送信をせず、ワークスペースの許可・配送結果は `UNKNOWN` と表示します。
認証情報がない場合や導入が欠ける場合は終了コード1です。

```bash
python3 tests/validate_slack_soliloquy.py
```

合成データとモックAPIで、勤務時間境界、手動/自動モード、再送、宛先変更防止、hook保持・再導入・解除を確認します。
本物のSlackへテスト投稿はしません。

## 更新・停止

`git pull` 後に同じ `install` と `check` を実行します。
停止する場合は使っている各エージェントについて解除します。保存済み下書き・設定は保持します。

```bash
python3 tools/slack_soliloquy/slack_soliloquy.py remove --agent codex
```
