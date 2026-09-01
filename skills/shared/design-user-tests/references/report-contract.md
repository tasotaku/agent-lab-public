# Execution report contract

reportは固定specごとに1ファイル作る。

```json
{
  "schema_version": "user-test-report/v1",
  "spec_id": "stable-kebab-id",
  "spec_version": 1,
  "spec_sha256": "lockのsha256",
  "executor_id": "fresh担当を識別する値",
  "started_at": "2026-08-14T01:00:00Z",
  "finished_at": "2026-08-14T01:12:00Z",
  "scheduling": {"available_executor_slots": 2, "batch_count": 1},
  "execution_artifacts": {"preserved_workspace": "隔離workspaceのpath", "completed_record": "trial recordのpath"},
  "tests": [{
    "id": "T1",
    "batch": 1,
    "execution_count": 1,
    "status": "PASS",
    "journey_started_at": "2026-08-14T01:01:00Z",
    "journey_stopped_at": "2026-08-14T01:03:00Z",
    "stop_reason": "completed",
    "functional_findings": [],
    "ux_findings": [],
    "unexpected_findings": [],
    "test_spec_issues": [],
    "evidence": ["条件名: 実測値、観測方法、合否が分かる短い事実"],
    "cleanup": {"status": "completed", "finished_at": "2026-08-14T01:04:00Z", "evidence": "専用環境だけを停止した"}
  }],
  "product_findings_count": 0,
  "blind_spots": []
}
```

各journeyの開始から停止までをspecのbudget以内にする。budget到達時は後付け延長せず `stop_reason: budget`、`status: INCOMPLETE` としてcleanupする。cleanup時刻はjourney停止後に記録する。`status` は `PASS`、`FINDINGS`、`INCOMPLETE`、`NOT_RUN`。実行済みは `execution_count: 1` と時刻、開始前に不可能と判明した未実行は `execution_count: 0` と両journey時刻 `null` にする。未実行でも環境cleanupは必須。product findingはfunctional、UX、unexpectedを数え、`TEST_SPEC_ISSUE`を含めない。全体経過時間は `started_at` と `finished_at` の差で求め、隔離環境が返した保存workspace/recordは `execution_artifacts` へ入れる（存在しなければnull）。

各 `functional_expectations` と `ux_checks` について、実測値または直接観測した状態と観測方法を `evidence` に残す。クリック数、手動surface切替数、scroll数、自動遷移、focus、所要時間はjourneyの実操作中に数える。最終スクリーンショットや内部関数の成功記録だけから推測しない。指定された観測channelが使えない場合、開始前なら `NOT_RUN`、開始後なら `INCOMPLETE` とし、blind spotまたは `TEST_SPEC_ISSUE` を記録する。未観測の必須条件があるreportをPASSにしない。

スクリーンショットは、viewport、表示要素、clipping、文字、静的な前後状態の補助証拠として使える。画像だけで操作回数や遷移原因を証明しない。必要なら操作log、画面録画、foreground windowのread-only取得、browser accessibility treeなど、対象を直接測れる安全なchannelを併用する。

複数journeyが別isolated environmentを使う場合、`execution_artifacts` の各文字列は `T1=<path> | T2=<path>` のようにtest id付きで全件を保持し、各testの `cleanup.evidence` にも対応するworkspace・completed record・停止確認を記録する。代表1件だけへ潰さない。

独立journeyは別executor・別isolated environmentで同じbatchに割り当て、時間区間を重ねる。利用可能slotを超える時だけ最小batch数にする。report全体に一律の時間上限を設けない。

製品findingには直接観測した製品挙動だけを書く。必要な公開channelを操作・観測できない場合、journey開始前なら `NOT_RUN`、開始後なら `INCOMPLETE` とし、spec不足は `test_spec_issues`、環境・権限制約はevidenceとblind spotへ記録する。host UIに操作があるか確認できない時、別channelのpayloadに操作がないことだけで製品全体に操作がないと断定しない。
