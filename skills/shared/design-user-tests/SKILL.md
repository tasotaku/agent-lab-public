---
name: design-user-tests
description: 実装から独立したcontext-freeな担当に、公開入口から実利用までの最小件数の利用者テスト仕様を実装前に設計させる。機能の正しさに加え、クリック数、自動画面遷移、手動切替、スクロール負担、発見可能性などを観測可能なUX条件として固定したい時、またはTEST_SPEC_ISSUEにより固定仕様の新versionが必要な時に使う。
---

# 利用者テストを設計する

## 実装より先に代表journeyを固定する

UI、MCP App/Card、Codex-hosted tool、cross-surface flowを作る・直す時は、原則として実装開始前にこのskillを使う。既に実装済みなら、次の修正内容を見せる前に仕様を作る。実装を見てから通りやすい手順へ寄せない。

新しいcontext-freeサブエージェントを1体起動し、その担当だけに仕様を書かせる。実装担当を兼任させない。渡してよい情報を次に限定する。

- 利用者の目標、公開要件、公開入口
- 想定利用者と対象画面サイズ・OSなどの公開利用条件
- 必要なテストデータとfixture制約

製品source、diff、既知の欠陥、修正案、過去の判定、実装担当の説明を渡さない。情報を分けられない環境では、自分で代筆せず `BLOCKED_INDEPENDENCE` と報告する。

## 最小仕様を作る

サブエージェントに [test-spec-contract.md](references/test-spec-contract.md) を完全に読ませ、現実の公開入口から成果を実際に使うところまでのjourneyを設計させる。主要リスクを覆う最小件数にし、1件で足りるなら1件にする。各journeyで客観的な機能期待と、目標に結び付くUX確認を一緒に定義する。

UIまたはsurface間を移動するjourneyでは、該当するものを事前に数値または明確な状態で固定する。

- 目的達成までのクリック・タップ・キー操作の上限
- 手動のウィンドウ／タブ／画面切替の上限
- 自動遷移する対象、開始条件、許容時間
- 指定viewportでスクロールせず見えるべき入口・次操作・結果
- 許容するスクロール回数または距離
- 操作後に前面・focus・選択状態になるべきsurface

公開要件がクリック数、自動切替、focus、scroll、待ち時間のいずれかを明示している時は、「該当しない」として省略しない。`setup` には初見・再訪・ログイン済み等の開始状態を、製品名だけでなくwindow/panel/tabまで識別できる公開surface名で書く。「入力可能」は単に入力欄が見えることではなく、必要ならfocus/caretと実際の試験入力・送信成功まで定義する。時間条件には計測開始event、終了event、時計または観測channelを含める。

すべてを機械的にゼロや最小にしない。安全確認など必要な操作は残し、利用者目標から期待値を決める。「簡単」「迷わない」「すぐ」だけで終わらせず、対象・測定値・閾値・直接観測方法が分かる文にする。スクロール条件にはviewportと、どこまでの操作を対象にするかを書く。

スクリーンショットは表示、clipping、情報密度、文言の根拠には使えるが、クリック回数、自動遷移、focus移動、待ち時間、途中のスクロール回数の証明にはしない。これらを直接観測できる公開channelまたは安全なharnessがない場合は、仕様の `coverage.blind_spots` に隠さず書く。

ユーザーが具体的な失敗手順・対象・期待状態を提示した場合、それを最優先の回帰journeyとして同じ対象名と観測可能な結果まで仕様へ固定する。最小化を理由に別機能へ置き換えたり、単なる起動確認へ弱めたりしない。

## 固定する

候補specを次で検査し、lockを作る。

```powershell
python scripts/lint_user_test_artifact.py spec <spec.json> --create-lock <spec.lock.json>
```

lint失敗は同じdesign担当に返して形式だけ直させる。製品都合で期待やUX基準を緩めない。version内のspecとlockを実行開始後に編集しない。

`TEST_SPEC_ISSUE` が報告された時だけ、別のfreshなcontext-free design担当に、元の利用者目標、現version、raw execution observations、指摘されたspec issueだけを渡す。`revision.kind` を `TEST_SPEC_ISSUE` にした次versionを新規ファイルへ作り、旧versionを残して検査する。

```powershell
python scripts/lint_user_test_artifact.py spec <v2.json> --previous <v1.json> --create-lock <v2.lock.json>
```

製品が失敗した、UIが分かりにくい、期待と出力が違う、厳しいという理由はspec issueにしない。
