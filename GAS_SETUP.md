# Google Apps Script セットアップ手順

## 🎯 概要
HALLEL渋谷店予約システムのGmail全メール確認・自動同期機能をGoogle Apps Scriptで実装

## 📋 セットアップ手順

### 1. Google Apps Script プロジェクト作成
1. [script.google.com](https://script.google.com) にアクセス
2. 「新しいプロジェクト」をクリック
3. プロジェクト名を「HALLEL Gmail Sync」に変更

### 2. Gmail API有効化
1. 左メニューの「サービス」をクリック
2. 「Gmail API」を検索して追加
3. バージョンは「v1」を選択

### 3. スクリプトコード設定
1. `gas_gmail_sync.js` の内容を全てコピー
2. Google Apps Scriptの `コード.gs` に貼り付け
3. `CONFIG.WEBHOOK_URL` を以下に更新：
   ```javascript
   WEBHOOK_URL: 'https://hallelshibuyabooking-m1d4xnomi-aceboys-projects.vercel.app/api/gas/webhook'
   ```

### 4. 権限設定
1. 「実行」ボタンをクリック
2. 「承認が必要です」が表示されたら「権限を確認」をクリック
3. Googleアカウントでログイン
4. 「安全ではないページ」が表示されたら「詳細設定」→「〜に移動（安全ではないページ）」
5. 以下の権限を許可：
   - Gmail メッセージの表示
   - Gmail ラベルの管理
   - 外部サービスへの接続

### 5. 初回実行テスト
1. 関数選択で `testSync` を選択
2. 「実行」ボタンをクリック
3. ログで処理状況を確認

### 6. 定期実行設定
1. 関数選択で `setupTrigger` を選択
2. 「実行」ボタンをクリック
3. これで1時間ごとの自動実行が設定されます

## 🔧 主な機能

### 全メール処理
- **対象**: `from:noreply@em.hacomono.jp subject:hallel`
- **件数**: 最大200件（全履歴対応）
- **フィルタ**: 渋谷店のみ自動判定

### ラベル自動適用
- `HALLEL/Processed` - 処理済み
- `HALLEL/Booking` - 新規予約
- `HALLEL/Cancellation` - キャンセル
- `HALLEL/Shibuya` - 渋谷店

### 自動同期
- **手動実行**: `syncGmailReservations()`
- **定期実行**: 1時間ごと（`scheduledSync()`）
- **データ送信**: Vercel Webhookで予約システムに反映

## 📊 実行ログ例
```
📧 Gmail予約同期開始...
✅ ラベル既存: HALLEL/Processed
🏷️ ラベル作成: HALLEL/Booking
📊 検索対象メール: 156件
⏳ 処理中... (1/156)
✅ 予約処理: 2025-11-01 10:00-11:00 田中太郎
🏷️ ラベル適用: HALLEL/Processed, HALLEL/Shibuya, HALLEL/Booking
📈 進行状況: 50/156 (32%)
✅ Vercel送信成功: 45件
✅ 同期完了: 45件の予約を処理
```

## 🚨 トラブルシューティング

### 「スクリプトを保存してから実行してください」
→ Ctrl+S でスクリプトを保存

### 「Gmail API が見つかりません」
→ 「サービス」からGmail APIを追加

### 「権限が不十分です」
→ 権限設定を再実行

### 「Webhook送信失敗」
→ WEBHOOK_URLが正しいか確認

## 📱 使用方法

### 手動実行（全メール処理）
1. 関数選択: `syncGmailReservations`
2. 実行ボタンをクリック
3. ログで進行状況を確認

### 定期実行状況確認
1. 左メニュー「トリガー」をクリック
2. 設定されたトリガーを確認

### ログ確認
1. 「実行数」をクリック
2. 各実行の詳細ログを確認

## ✅ 完了後の確認事項
- [ ] Gmail に HALLEL ラベルが作成されている
- [ ] 予約メールにラベルが適用されている
- [ ] Vercel システムに予約が反映されている
- [ ] 定期実行トリガーが設定されている

**これで全メール確認・自動同期システムが完成！**