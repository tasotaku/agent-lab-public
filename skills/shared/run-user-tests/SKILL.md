---
name: run-user-tests
description: 固定済みの利用者テスト仕様を、実装から独立したfreshなcontext-free担当が公開入口から各1回だけ実行する。クリック数、自動遷移、手動切替、スクロール、focusなどを実操作中に直接測り、機能問題とUX問題を分けて報告する。
---

# 固定利用者テストを実行する

## 入力と観測可能性を検査する

`design-user-tests` のlintでspec lockを検証する。

```powershell
python ../design-user-tests/scripts/lint_user_test_artifact.py spec <spec.json> --verify-lock <spec.lock.json>
```

固定spec、公開製品入口、startup手順、対象を限定した正確なcleanup手順を用意する。cleanupが通常のCodex、IDE、無関係なprocessやdataへ触れないことを確認する。

実行前に、各必須actionと期待を許可された公開channelで直接操作・観測できるか確認する。MCP structured result、App/Card、browser、隔離UI、OSのforeground/focus観測などを区別し、host UIの挙動を別surfaceのpayloadや内部関数の成功から推測しない。必要な観測channelがspec/startupにない、または安全規則上使えないならjourney開始前は `NOT_RUN`、開始後は `INCOMPLETE` とし、`TEST_SPEC_ISSUE` またはblind spotへ分ける。未観測の必須条件が1つでもあればPASSにしない。

## fresh実行担当を起動する

各journeyに新しいcontext-freeサブエージェントを1体ずつ起動する。実装担当、spec作成担当、過去のexecutorを再利用しない。独立journeyごとに別isolated environmentを使い、利用可能slotまで同時実行する。slotを超える時だけ最小batch数にする。渡す情報を次に限定する。

- 固定specとlock
- 公開製品入口
- startup手順、許可された観測方法、正確なcleanup手順

source、diff、既知の失敗、修正意図、実装詳細、過去reportを渡さない。分離できなければ `BLOCKED_INDEPENDENCE` と報告し、自分で承認しない。

## 1回だけ最後まで試す

executorへ次を指示する。

- 各testを記載順に1回だけ実行し、失敗をPASSへ変えるretryをしない。
- journey開始時からクリック・タップ・キー操作、手動surface切替、scrollを数える。自動遷移、focus、前面window、表示時刻は発生時に直接観測する。
- 「入力可能」はspecに従い、可視性だけでなくenabled、focus/caret、試験入力・送信まで実操作する。時間条件は固定された開始eventと終了eventで測る。
- 各期待について、期待値、実測値または観測状態、観測方法、合否を短いevidenceへ残す。
- failure後もjourneyの最後まで続け、真に不可能・unsafe・そのjourneyの事前budget到達時だけ止める。
- 製品やspecを編集しない。
- 機能findingsとUX findingsを分け、checklist外のunexpected findingsも残す。
- UIはexecutor自身が初期表示から操作後・最終状態まで実画面を見て、「このまま通常利用者へ出荷できるか」を `GO` / `NO-GO` で判定する。`NO-GO` は必ずUX findingとし、最大の理由を1つ先頭に書く。
- UXは機能と同じgating findingとして扱う。機能PASSでも、固定した操作上限、自動遷移、focus、初期viewport、scroll負担、理解しやすさ等を満たさなければtestをPASSにしない。
- スクリーンショットは表示・clipping・文言などの補助証拠に使う。単一画像から途中の操作数、scroll数、遷移原因、focus移動、所要時間を推測しない。
- `TEST_SPEC_ISSUE` は契約に入口がない、手順が矛盾、入力不足、期待を観測不能、PASS/FAILが曖昧、目標と無関係な場合だけ使う。
- 成否にかかわらず各isolated environmentをcleanupする。specに固定された公開step時間＋想定外部waitのbudgetを守り、遅い実装やhangを理由に後付け延長しない。到達時はcleanupして `INCOMPLETE` と報告する。
- 製品findingは直接観測した製品挙動だけにする。executor/harnessの操作不能、権限不足、host固有UIの未観測を製品不在の証拠にしない。

reportを [report-contract.md](../design-user-tests/references/report-contract.md) に従って保存し、検査する。

```powershell
python ../design-user-tests/scripts/lint_user_test_artifact.py report <report.json> --spec <spec.json> --verify-lock <spec.lock.json>
```

global PASS/FAILだけで終えず、個々のproduct finding、spec issue、blind spot、実測したinteraction、journey budget、並列batch、cleanup結果を返す。
