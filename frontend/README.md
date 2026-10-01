# frontend

タスク管理アプリのフロントエンド（React 19 + TypeScript + Vite + MUI v9）。

## 画面構成

| パス | 画面 | 概要 |
|---|---|---|
| `/` | ダッシュボード | 「いま取り組んでいるタスク」ヒーローカード・今日の予定・遅延アラート・近日締切・全体進捗ドーナツ |
| `/today` | 今日のタスク | 期限超過/今日/進行中/明日/開始済みのバケット別リスト。チェックで完了トグル |
| `/tasks` | タスク一覧 | 検索・ステータス/カテゴリ/マイルストーン絞り込み・並び替え（クライアント側） |
| `/tasks/new`, `/tasks/:id` | タスク作成/編集 | 中央寄せカードフォーム。優先度・緊急度は 高/中/低 のpill選択（5/3/1 に対応）。編集時は作業ログ・依存関係タブあり |
| `/gantt` | ガントチャート | 自作コンポーネント（`components/GanttChart.tsx`）。今日ライン・土日シェード・ステータス色バー（進捗フィル） |
| `/calendar` | カレンダー | 予定（`/api/calendar/*`）の月・週・平日表示。週表示のドラッグで作る・動かす・伸ばす（元に戻す・やり直しも API 越し）。タスク・マイルストーンの期限を終日の帯に枠だけのチップで出す。予定の編集はダイアログ（`components/calendar/EventEditDialog.tsx`） |
| `/settings` | 個人設定 | 言語・タイムゾーン、営業日カレンダーと祝日（日本の祝日を年で入れる） |
| `/inbox` | インボックス | クイックメモの追加・タスク変換・削除 |

## デザイン

デジタル庁デザインシステム準拠のデザイン handoff を再現している。

- デザイントークン（色・フォント・角丸）は `src/theme.ts` の `ds` オブジェクトと MUI テーマに集約。
  スタイル指定は必ず `ds` を参照する（HEX 直書きしない）。
- フォントは Noto Sans JP（`index.html` で Google Fonts から読み込み）。
- アイコンはすべてインラインSVG（`src/components/icons.tsx`、viewBox 24 / stroke 1.8〜2.6 / round）。
- 共通部品: `StatusChip`（遅延判定込み）・`PriorityChip`（高/中/低）・`ProgressBar`・`CategoryDot`・`Layout`（サイドバー224px＋トップバー58px）。
- ガント・カレンダーは外部ライブラリ不使用（自作）。
- 予定のカレンダー（`components/calendar/`）は NolumiaScheduler（WinUI 版）の見た目に寄せていて、色は
  `ds` ではなく MUI テーマの `palette.calendar`（`src/calendar/calendarColors.ts`、明暗の 2 組）から読む。
  日付は `YYYY-MM-DD`、時刻はその日の 0:00 からの分で持ち、閲覧者のタイムゾーン（利用者設定）で
  日を割る。配置などの純関数は `src/calendar/` にあり、`*.test.ts` が vitest の試験。
- 予定 API への書き込みは、`src/calendar/calendarRequests.ts`（ドラッグ・元に戻す・削除）と
  `src/calendar/eventForm.ts`（編集画面の保存）が呼び出しをデータ（`CalendarRequest`）として組み立て、
  `src/api/calendar.ts` の `sendCalendarRequest` だけが送る。版の食い違い（409）は最新を取り直して知らせる。

## API 契約上の注意

- `GET /api/tasks` は**配列**を返す。ページング・並び替えパラメータは無く、絞り込みは
  `status_filter`（単一値）・`category_id`・`milestone_id`・`parent_task_id` のみ。
  複数ステータス絞り込み・検索・ソートはクライアント側で行う。
- 作業ログは `/api/work-logs`。
- 依存関係のレスポンスは `{ task_id, predecessors[], successors[] }` 形式。追加時は `predecessor_task_id` を送る。
- `progress_percent` は読み取り専用（作業ログの実績時間と残り時間から自動算出。DONE は 100%）。
  進捗を進めたいときは作業ログを記録するか残り時間を更新する。

## コマンド

```bash
npm run dev      # 開発サーバー（/api は localhost:8000 へプロキシ）
npm run build    # 型チェック + 本番ビルド
npm run lint     # oxlint
npm run test     # vitest（src/**/*.test.ts）
```
