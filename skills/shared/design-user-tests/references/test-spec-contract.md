# Test specification contract

JSONをUTF-8で保存する。必須形は次の通り。

```json
{
  "schema_version": "user-test-spec/v1",
  "spec_id": "stable-kebab-id",
  "version": 1,
  "goal": "利用者が達成すること",
  "persona": "想定利用者",
  "public_entry": "URL、command、画面などの公開入口",
  "test_data": ["必要なfixtureまたは制約"],
  "minimal_test_count_rationale": "なぜこの件数が最小か",
  "execution_policy": {"runs_per_test": 1, "continue_after_failure": true, "parallelize_independent_tests": true},
  "tests": [{
    "id": "T1",
    "title": "短い名前",
    "user_task": "利用者へ渡す目標。内部手順を答えとして漏らさない",
    "setup": ["事前条件"],
    "actions": ["公開入口からの操作", "成果を実際に使う操作"],
    "functional_expectations": ["観測可能な正しさ"],
    "ux_checks": ["対象、測定値、閾値、直接観測方法が明確なUX条件"],
    "impossible_if": ["製品FAILとは異なる、実行が真に不可能な条件"],
    "isolation_requirements": "このjourney専用の環境・account・session条件",
    "budget": {
      "public_steps_minutes": 2,
      "expected_external_wait_minutes": 1,
      "total_minutes": 3,
      "basis": "公開step数と想定waitからの見積根拠"
    }
  }],
  "reporting": {
    "separate_functional_and_ux": true,
    "include_unexpected_findings": true,
    "evidence_level": "concise"
  },
  "coverage": {"covered_risks": ["主リスク"], "blind_spots": ["既知の未確認範囲"]},
  "revision": null
}
```

各 `tests[]` を独立して実行できる1つのstateful journeyにする。shared UI/account/session、same-entry、状態継続が必要なstepは同じjourneyの `actions` にまとめて直列にする。journeyを分ける時は別executorと別isolated environmentで同時実行できるようにする。

## 客観的なinteraction条件

UIまたはcross-surface journeyの `ux_checks` には、利用者目標に関係する次の項目を可能な範囲で固定する。

- クリック・タップ・キー操作数
- 手動の画面、ウィンドウ、タブ切替数
- 自動画面遷移の遷移元・遷移先・期限
- 前面window、focus、選択状態
- viewport内に最初から見えるべき入口、次操作、重要結果
- journeyの区間ごとのscroll回数または距離

各条件は「何を」「いつからいつまで」「どのviewportまたは環境で」「何回以内／何秒以内／どの状態なら合格か」「何で直接観測するか」が分かる文にする。例：`1920x1080の初期画面で「開始」が見え、開始を1クリックしてから2秒以内にCodexが前面になり、追加クリック・手動window切替・scrollはいずれも0回`。

`setup` には、初見利用者ならclean profileの要否、ログイン状態、既存会話・既読tutorial・保存状態など結果を変える初期状態を固定する。対象surfaceは「Codex」のような製品名だけで済ませず、desktop window、VS Code panel、browser tabなど観測対象を区別する。「入力可能」は必要に応じて、入力欄の可視性、enabled状態、keyboard focus/caret、試験文字の入力、送信成功のどこまでを意味するか定義する。秒数を測る条件では、開始event、終了event、使用する時計またはobserver、許容値を記す。

公開要件または利用者目標が明示したinteraction項目は必須であり、「可能な範囲」や最小test数を理由に省略しない。直接観測できない場合は、合格条件から黙って外さず、必要な公開harnessをfixtureへ加えるかblind spotとして実行不能を明示する。

操作数は常に少ないほど良いとは限らない。確認や安全のため必要な操作を省かず、利用者に期待する最短の通常経路を基準にする。自動focus移動も常に良いとは限らないため、公開要件または利用者目標が要求する時だけ固定する。

スクリーンショットは静的な表示状態の根拠に限定する。単一の最終スクリーンショットから、途中のクリック数、scroll数、遷移の自動性、focus移動、経過時間を推測してはならない。直接観測channelが用意できない必須条件は、実行可能な期待として書かず `coverage.blind_spots` に記録するか、公開harnessをfixtureとして定義する。

UX checkはgoalに即して、発見可能性、読みやすさ、理解可能性、情報密度、clipping、scroll負担、遷移の迷い、回復案内、surface間の一貫性から必要なものだけを選ぶ。UI journeyでは必ず「通常利用者向けとしてこのまま出荷できるか」と「最大のUX問題は何か」を含める。機能結果より内部ID・hash・診断情報が先に目立つ、重要結果まで仕様を超える操作やscrollが要る、成功と失敗を誤解しやすい場合は不合格にする。見た目の好みを無制限に採点しない。

新versionでは `spec_id` を維持し、`version` を1増やす。`revision` を次の形にする。

```json
{"kind":"TEST_SPEC_ISSUE","previous_version":1,"issue":"観測された仕様問題","raw_observation":"実行時の生観測"}
```

旧versionとlockを上書きしない。

budgetは公開操作に必要な時間と、公開contractから想定できる外部waitを足してjourneyごとに事前固定する。典型的な最小journeyは数分を想定する。一律上限を置かず、遅い実装、予期しないhang、実行後の都合を理由に延長しない。
