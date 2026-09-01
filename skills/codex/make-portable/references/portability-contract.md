# Portability Contract

## Repository contract

別PC向けの完成形は次を満たす。

| 領域 | 必須条件 |
|---|---|
| Source | 利用に必要な自作ソース、文書、small assetsがremoteにある |
| Dependencies | lockfileまたは厳密なversion制約から復元できる |
| Machine setup | OS別処理が1本の利用者向け入口から選ばれる |
| Secrets | 値をGitへ入れず、必要な名前と再認証方法だけ分かる |
| Local data | commit、再生成、外部private storageのいずれかに所在が定まる |
| Agent integration | 必要なskill、MCP、hook、agent-labが登録・確認される |
| Recovery | 上書き前backupまたは無変更の収束動作がある |
| Verification | `check` が主要な実利用経路を検査し、未確認も隠さない |
| Distribution | private/publicの判断根拠があり、remote上のcommitを確認できる |
| Continuity | 開始時にremote先行・分岐を検知し、終了時にコードと共有対象knowledgeのremote到達を確認できる |

## Install and check behavior

`install` は成功時に、変更した項目、再利用した項目、利用者が行う認証、次の確認コマンドを出す。部分的に失敗した場合は成功終了せず、どこから再実行できるかを出す。

`check` は少なくとも次を区別する。

- PASS: 実行して確認した
- FAIL: 欠損または不一致を観測した
- UNKNOWN: このOSや環境では観測できない
- MANUAL: ログイン、trust、権限許可など利用者の操作が必要

`check` の終了コードは、必須項目がすべてPASSなら0にする。必須項目がFAIL、UNKNOWN、MANUALなら非0にし、任意項目のUNKNOWNとMANUALだけを出力付きの成功にできる。

主要ユースケースは、既存READMEで最初に案内される通常利用、現在の実行入口、ユーザーの直前の指定から決める。必要依存が変わる複数の製品形態が残る場合は、bootstrapを作る前に選択を得る。

## OS separation

共通ロジックはPythonなどのcross-platformな入口へ置き、OS固有処理だけを小さく分ける。

- macOS: Homebrew、`.app`、Keychain、launchd、Apple Silicon/Intelのパス差
- Windows: PowerShell、winget、AppX、`APPDATA`、実行ポリシー、symlink権限
- Linux/WSL: package manager、systemd、GUI不在、WSLとWindows nativeのhome/config分離

OS名だけで分岐せず、利用するコマンド、ファイル、アプリの実在も検出する。WSLはLinuxとして動かす処理とWindows側アプリへの登録を混同しない。

言語packageはlockfileを優先する。Python、Node、Javaなどのruntimeは対応範囲または固定versionを記録して `check` で検査する。Homebrew、winget、aptなどOS package manager自体の完全固定を偽らず、導入したpackageと観測versionを証拠へ残す。GitHub Actionsはcommit SHA固定またはmajor tag固定の選択理由を残す。

## Secret and data audit

push前に、tracked filesと履歴の両方を確認する。ファイル名だけでなく内容も検索し、実値をログへ表示しない。少なくとも次を分類する。

- API keys、OAuth token、session cookie、SSH/private key
- `.env`、認証JSON、OS資格情報ストアからexportした値
- 顧客データ、社内資料、会話ログ、個人情報
- database、download cache、generated dataset、model weights
- `.venv`、`node_modules`、build output、OS metadata

秘密がGit履歴に入っていた場合はpushを止める。値の失効・再発行と履歴除去は影響が大きいため、対象とリスクを示してユーザーへ確認する。第三者データや画像の再配布許諾を根拠から確認できなければGitへ追加しない。

## Minimum acceptance table

| ID | 確認内容 | 合格条件 |
|---|---|---|
| P-01 | 新規PC入口 | READMEのコマンドだけでcloneから開始できる |
| P-02 | Clean install | 空のhome相当で必須依存と設定が導入される |
| P-03 | Idempotence | installを2回実行しても破損や不要なbackupが増えない |
| P-04 | Verification | checkが導入済み状態をPASSし、意図的な欠損をFAILする |
| P-05 | Secrets | remoteと履歴に認証情報がなく、再認証方法が出る |
| P-06 | Data | 必須データが取得または再生成され、主要操作で読める |
| P-07 | Agent dependency | 必須の場合だけagent-lab、skill、MCP、hookが導入・検出される |
| P-08 | OS claims | 対応と記載した各OSに実行証拠がある。なければUNKNOWN表記 |
| P-09 | Remote delivery | 利用者がcloneするbranchに検証済みcommitが存在する |
| P-10 | Main use case | 新規環境からシステムの主要操作を1つ完遂できる |
| P-11 | Multi-PC continuity | 別cloneのpushを開始時に検知し、journal/currentが同じproject IDでprivate remoteへ届く。会話原本と認証状態は同期しない |
