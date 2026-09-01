---
name: loop-engineering
description: 全開発タスクの開始時に読み、通常工程かfull improvement loopかを判定する。full loopでは固定した複数基準、決定的検査、freshな独立担当を使い、指定されたskill・rule・prompt・agent手順自身を根拠のある範囲だけ反復改善する。
---

# Loop Engineering

全開発タスクで最初に読む。次のrouting gateだけで、重いfull loopを毎回は実行しない。

- 通常の機能実装、単発のバグ修正、局所的リファクタリング: 利用者目標・合格条件・変更scopeを確認して通常工程へ進む。
- skill・rule・prompt・agent手順の作成／改善、同じfailure signatureの2回目、一般化可能なworkflow改善: 以下のfull loopを実行する。failure signatureは `正規化した診断文字列・exact exit code・failing test/check ID` の三つ組として記録し、確認したroot causeは別項目にする。
- 説明・調査・レビューだけで成果物を変更しない依頼: このskillによる追加工程は不要。

full loopでは指定された一つの再利用可能な対象（skill・rule・prompt・agent手順・harness）を、評価基準を後から動かさずに改善する。通常コードの反復failureを契機にしても製品source自体をこのloopの自己改訂対象にせず、再試行を生んだ開発手順側を対象にする。該当する再利用可能な対象がなければ、通常の製品修正とworkflow checkpointだけを行い、対象を捏造しない。評価AIの主観だけで変更を採用しない。

## 開始契約を固定する

対象skill、編集を許すsupport file、利用者目標、公開入口、決定的validator、held-out条件、最大反復数を編集前に確定する。最大反復数の既定は2。対象や権限が曖昧なら拡張せず確認する。

`design-user-tests` で実装を知らないfresh担当に最小journeyと5軸の観測条件を書かせ、specとlockを固定する。既存の互換specがあれば再利用する。

5軸は同じ計算法でbaselineとcandidateを比較する。

- `task_success`: 固定validatorまたは公開journeyの達成数
- `evidence_grounding`: findingと採否がraw observation/check IDへ追跡可能か
- `efficiency`: 操作、試行、時間、モデル呼出しが固定上限内か
- `safety_scope`: 許可path外の変更、権限拡大、秘密送信がないか
- `generality`: held-outと既存契約が非劣化か

詳細な採用規則は [evaluation-contract.md](references/evaluation-contract.md) を読む。

## baselineを編集前に封印する

skill付属CLIで対象の完全copy、hash、spec/validator hash、開始時Git状態、allowlistを保存する。

```powershell
python <this-skill>/scripts/loop_artifact.py start `
  --root <repo> --target <skill-path> `
  --allow-edit <support-path> --spec <spec.json> `
  --validator <validator-path> --max-iterations 2
```

返されたrun directoryはversioned artifactとして保持する。baselineや過去iterationを上書きしない。

## 役割を分離して1 iterationを回す

同じ担当をbaseline評価、編集、post評価に再利用しない。

1. fresh baseline担当へ固定spec、fixture manifest、baseline snapshot、公開入口だけを渡し、各journeyを1回実行させる。実際に渡した項目をrole input manifestへ記録する。
2. deterministic validatorを実行し、raw stdout/stderr、exit code、時間、Git diffを保存する。
3. findingがcheck IDまたは直接観測へ結び付く場合だけ、別のeditor担当へfindingと編集allowlistを渡す。held-out内容、期待解、過去の採点結論は渡さず、editor input manifestへ明記する。
4. editorは対象skillと許可support fileだけを狭く変更する。各diff行をfinding/check IDへ対応させたchange mapを作る。styleの好み、点数合わせ、fixture固有値のhard-code、無関係な空白・改行正規化は変更理由にしない。
5. 別のfresh post担当へbaseline結論、candidate diff、編集理由、期待解、以前の評価文を渡さず、同じspec、fixture、公開入口とcandidate snapshotだけで各journeyを1回再実行させる。post input manifestを評価開始前に固定する。
6. 同じvalidatorと5軸で比較し、候補diffと証拠を追記記録する。

```powershell
python <this-skill>/scripts/loop_artifact.py record `
  --run <run-dir> --iteration 1 `
  --baseline-executor <fresh-id> --editor-executor <fresh-id> `
  --post-executor <fresh-id> --baseline-report <report.json> `
  --baseline-input-manifest <json> --editor-input-manifest <json> `
  --post-input-manifest <json> `
  --baseline-raw <json> --editor-report <json> --post-raw <json> `
  --post-report <report.json> --scope-report <json> --candidate-diff <diff.patch> `
  --change-map <change-map.json> --scorecard <scorecard.json> --decision adopt `
  --stop-reason "goal achieved"
```

role input manifestとchange mapの形式は [evaluation-contract.md](references/evaluation-contract.md) に従う。raw validator入出力、editor report、scope検査もiteration内へcopyされる。外部の一時work pathだけを証拠として参照しない。CLIがexecutor重複、context分離不足、根拠に対応しないdiff行、反復超過、iteration上書き、allowlist外diffを拒否したら採用しない。

## 採用と停止

候補を採用できるのは、task successまたは根拠付き品質が改善し、その他の軸・held-out・既存契約が非劣化で、scope検査がPASSした時だけ。単独LLMの総合点や「より良いと思う」は証拠にしない。

次のどれかで止める。

- 全固定条件を満たし、未解決の根拠付きfindingがない
- baselineが既に合格し、変更根拠がない（無変更成功）
- 候補が改善しない、回帰する、scopeを破る
- 開始前に固定した反復上限へ到達した
- 新しい権限、製品要件、外部状態、ユーザー判断が必要

`TEST_SPEC_ISSUE` の時だけ `design-user-tests` のfresh設計担当に次versionを作らせる。製品やskillが通らないことを理由に同versionの基準を緩めない。

## 最終応答

最初に採用／無変更／未達、baseline→finalの5軸差、変更path、停止理由、artifact pathを示す。hashやexecutor IDは監査artifactへ置き、利用者向け結論より先に並べない。
