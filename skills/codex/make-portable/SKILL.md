---
name: make-portable
description: Codexと一緒に開発・運用しているシステムを別PCへ再現可能にする。ユーザーが「他のPCでも使いたい」「GitHubへ上げて移行したい」「セットアップコマンドを作って」「macOS/Windows/Linux対応にして」「agent-labを含む依存をまとめて導入したい」と依頼した時に使う。リポジトリの可搬性監査、必要なprivate GitHub配布、OS別bootstrap、秘密情報の分離、クリーン環境検証まで実行する。
---

# Make Portable

現在動いている端末を複製せず、リポジトリから別PCへ再構築できる状態まで仕上げる。調査や提案だけで終えず、許可された対象リポジトリへ実装・検証・反映する。

開始前に [references/portability-contract.md](references/portability-contract.md) を読む。

## 1. 完成条件を置く

ユーザーの目的を「認証済みの別PCで、提示した1本の入口からclone、導入、確認まで完遂できる」と定義する。

- 対象は現在のリポジトリ。複数ある場合はユーザーが挙げたものを順に扱う。
- 対象OSが未指定なら、現在のOSに加えてmacOS、Windows、Linuxの成立可否を調査する。実際に提供できるOSだけを対応対象にする。
- GUIアプリ、ゲーム、OSサービスなどの制約で対応不能なOSは、理由と代替経路を明記する。未確認の想像で非対応にしない。
- 最終成果はセットアップ用ソースではなく、別PCで利用者が実行するコマンドと、その実行結果である。

既存README、実行入口、直前の会話から主要ユースケースを1つに絞る。拡張単体、エージェント統合、研究環境のように必要依存が大きく変わる利用形態が複数残る場合は、背景 / 方針 / タスク / ゴールを持つ2〜4案を提示し、選択されるまで編集しない。同様に、同一データの再現と常に最新データを取得する運用が分かれる場合も先に選択を得る。

## 2. 現在のシステムを監査する

最初にプロジェクトの `AGENTS.md` / `CLAUDE.md` とREADMEを読み、次を実測する。

1. Git状態、remote、GitHub visibility、未追跡・未コミット変更
   - 作業開始前にfetchし、現在PCのHEADだけでなくremote先行・分岐・別worktreeの未合流branchも確認する。
2. 言語、package manager、lockfile、ビルド、起動、テスト、生成データ
3. 絶対パス、symlink、ローカルアプリ、OSサービス、シェル、資格情報ストアへの依存
4. `.env`、APIキー、token、cookie、顧客データ、会話ログ、端末固有設定
5. Gitへ入らない大容量データ、キャッシュ、ビルド成果物と、それらの再生成方法
6. agent-labのルール、スキル、フック、MCP、補助コマンドを実行時に本当に必要とするか

agent-labを「このPCに存在する」という理由だけで依存にしない。利用者がCodexからシステムを操作するためにagent-lab側のスキル・フック・MCPが必要なら依存、開発時の好みだけなら非依存と分類する。

## 3. 配布境界を安全に決める

- remoteがなく、ユーザーがGitHubへのアップロードも依頼している場合だけ、GitHub CLIでユーザー所有のprivateリポジトリを作る。ownerは `gh api user` の認証主体、名前は現在のリポジトリ名を候補にし、複数候補や組織ownerが絡む時だけ確認する。「他PCで使えるように」だけならremote作成・pushを推論せず、ローカルの可搬化とclone後コマンドの準備までに留める。
- 既存remoteがあれば新しい正本を増やさず、原則そのremoteを使う。
- 認証情報や端末固有ファイルはcommitしない。必要な変数名だけ `.env.example` などへ残し、値の取得・ログイン手順をsetup出力へ出す。
- 生成可能なデータや依存パッケージはGitへ入れず、bootstrapで再生成する。再生成不能で利用に必須のデータだけ、容量、権利、機密性を確認してGit LFS、Release asset、private storageのどれかを選ぶ。第三者データの再配布可否を根拠から確定できなければcommit・pushせず、取得元からの再生成経路にするかユーザー判断を待つ。
- 既存のユーザー変更を消さない。移行に必要な既存変更は秘密監査後に含め、無関係な変更は触らない。dirty変更のどれを完成形へ含めるかで機能や配布内容が変わる時は、include / exclude候補を示して編集前に選択を得る。

## 4. 1本のbootstrapを実装する

既存の導入スクリプトがある場合は正本として再利用し、別の実装を複製しない。利用者向け入口は原則として次へ揃える。

```text
python3 bootstrap.py install   # macOS / Linux
python bootstrap.py install    # Windows
python3 bootstrap.py check     # macOS / Linux
python bootstrap.py check      # Windows
```

リポジトリの規約や必要ランタイムにより別の入口が明らかに優れる場合は、その1本へ統一してよい。bootstrapは次を満たす。

- OSを実行時に判定し、OS共通処理とOS固有処理を分離する。
- 再実行しても壊れない。既存設定を書き換える前に回復可能なbackupを作る。
- package managerのlockfileを優先し、依存バージョンを再現する。
- 必須コマンドやアプリがなければ、検出したOSに対応する具体的な導入方法を表示する。ユーザー領域だけで完結し、無料で、ライセンス同意や管理者権限を要求せず、既存の既定runtimeを置き換えない依存だけ自動導入してよい。それ以外は影響を示して確認する。
- パスを固定しない。repo root、home、アプリの実在位置から解決する。
- login、token、Codexのtrust/hook reviewなど、人の安全確認を偽装・コピー・迂回しない。
- `check` はファイルの存在だけでなく、主要コマンド、登録、起動、最小ユースケースを確認し、未確認項目も出力する。

agent-labが実行時依存なら、bootstrap内で次を行う。

1. 既存cloneと配線を検出して再利用する。
2. なければ現在のAGENTS import、設定、既存remoteからagent-labの正本remoteを特定する。特定不能なら決め打ちせず確認する。
3. `gh` の認証を確認し、macOS/Linuxは `~/work/agent-lab`、Windowsは `$HOME\work\agent-lab` を既定候補としてprivate remoteをcloneする。既存パスやユーザー指定があればそちらを優先する。
4. 対象OSのPythonで `engine/bridge/setup.py install` と `check` を実行する。
5. 元システムのsetupへ戻って残りを継続する。

agent-labのknowledgeを使う場合は、同じリポジトリがOSやclone先の違いで別棚にならないことも確認する。
project IDはorigin remoteを正本とし、既存の絶対パス棚は`knowledge/project-aliases.json`で対応付ける。
共有対象はjournalとcurrentに限定し、会話原本、ジョブDB、認証状態は各PCのローカルへ残す。

## 5. リポジトリへ届ける

READMEの先頭付近に、別PCで最初に実行するcloneからcheckまでのコピペ可能なコマンドをOS別に載せる。前提、認証が必要な箇所、導入されない秘密情報、更新方法も短く記載する。READMEとbootstrapには、対象にした主要ユースケースと、任意扱い・非対象にした利用形態を明記する。

変更を小さくcommitする。remoteへの反映が依頼に含まれる場合はprivate remoteへpushし、直後にremote branchとcommitを読み直して確認する。agent-labを依存にした場合は、対象リポジトリだけでなくagent-labもfetchし、今回生成されたjournal/currentがcommit・push済みか確認する。既存公開remoteのvisibility変更、課金が発生する保存先、秘密を含む可能性が残るpushでは停止してユーザーへ確認する。

## 6. クリーン環境で閉じる

1. 静的チェックを実行する。
2. `$test` を使い、install/checkの正常系、再実行、欠損依存、既存設定保持を検証する。
3. 一時ディレクトリで確認する場合は、隔離したhomeとconfig/cacheを使い、PATHと認証情報を明示的に制限したclean cloneからinstall/checkを実行する。同一端末に既にある依存やログインで成功を偽らない。GUIアプリやOSサービスはCIだけで証明せず、対象OSの実機またはVMで確認する。
4. 対応を名乗る各OSをCI matrixまたは実機で確認する。未確認OSは `UNKNOWN` と明記する。
5. GUI、外部API、MCP、拡張、生成物がある場合は `$visual-verify` を使う。
6. `$improve-with-user-tests` を使い、会話履歴のないfreshな担当がREADMEの入口だけから主要ユースケースを完遂できるまで修正と再検証を繰り返す。

最後に、別PCで実行するコマンド、GitHubリポジトリとvisibility、対応OS、移行できるもの、PCごとに再認証が必要なもの、テスト結果を報告する。
