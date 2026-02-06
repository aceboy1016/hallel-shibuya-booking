# Google Apps Script 詳細登録手順

## 🎯 完全手順ガイド

### 1. Google Apps Script アクセス
1. **ブラウザで以下URLにアクセス**
   ```
   https://script.google.com
   ```

2. **Googleアカウントでログイン**
   - HALLELのGmailアカウントでログイン必須

### 2. 新しいプロジェクト作成
1. **「新しいプロジェクト」ボタンをクリック**
   ![新しいプロジェクト](https://developers.google.com/apps-script/images/new-project.png)

2. **プロジェクト名変更**
   - 左上の「無題のプロジェクト」をクリック
   - 「HALLEL Gmail Sync」に変更
   - 「名前を変更」をクリック

### 3. Gmail API サービス追加
1. **左メニューの「サービス」をクリック**
2. **「＋」ボタンをクリック**
3. **Gmail API を検索**
   - 検索ボックスに「Gmail」と入力
   - 「Gmail API」を選択
4. **バージョン選択**
   - 「v1」を選択
   - 「追加」ボタンをクリック

### 4. スクリプトコード貼り付け
1. **メインエディタに移動**
   - 左メニューの「エディタ」をクリック

2. **既存コードを全削除**
   - `コード.gs` タブの中身を全て選択（Ctrl+A）
   - 削除（Delete）

3. **新しいコードを貼り付け**
   ```javascript
   // 以下のコード全体を貼り付け
   /**
    * Google Apps Script用Gmail自動同期
    * HALLEL渋谷店予約システム - 全メール確認対応
    */

   // 設定
   const CONFIG = {
     WEBHOOK_URL: 'https://hallelshibuyabooking-m1d4xnomi-aceboys-projects.vercel.app/api/gas/webhook',
     SEARCH_QUERY: 'from:noreply@em.hacomono.jp subject:hallel',
     MAX_MESSAGES: 200, // 全メール対象
     LABELS: {
       PROCESSED: 'HALLEL/Processed',
       BOOKING: 'HALLEL/Booking',
       CANCELLATION: 'HALLEL/Cancellation',
       SHIBUYA: 'HALLEL/Shibuya'
     }
   };

   // [続きのコードは gas_gmail_sync.js を全てコピー]
   ```

4. **保存**
   - Ctrl+S または「保存」ボタンをクリック

### 5. 権限認証（重要！）
1. **初回実行準備**
   - 関数選択ドロップダウンで「testSync」を選択

2. **実行ボタンをクリック**
   - 「実行」ボタン（▶️）をクリック

3. **権限承認プロセス**
   - 「承認が必要です」ダイアログが表示
   - 「権限を確認」ボタンをクリック

4. **Googleアカウント選択**
   - HALLELのGmailアカウントを選択

5. **セキュリティ警告への対応**
   - 「このアプリは確認されていません」が表示される場合
   - 「詳細設定」をクリック
   - 「HALLEL Gmail Sync（安全ではないページ）に移動」をクリック

6. **権限許可**
   以下の権限を「許可」：
   - ✅ Gmail メッセージの表示、編集、整理、削除
   - ✅ Gmail ラベルの表示と管理
   - ✅ 外部サービスに接続

7. **「許可」ボタンをクリック**

### 6. 初回テスト実行
1. **実行完了確認**
   - 下部の「実行ログ」を確認
   - エラーがないことを確認

2. **ログ内容例**
   ```
   📧 Gmail予約同期開始...
   ✅ ラベル既存: HALLEL/Processed
   🏷️ ラベル作成: HALLEL/Booking
   📊 検索対象メール: 156件
   ✅ 予約処理: 2025-11-01 10:00-11:00 田中太郎
   ✅ 同期完了: 45件の予約を処理
   ```

### 7. 定期実行トリガー設定
1. **setupTrigger関数実行**
   - 関数選択で「setupTrigger」を選択
   - 「実行」ボタンをクリック

2. **トリガー確認**
   - 左メニューの「トリガー」をクリック
   - 「scheduledSync」が1時間ごとに設定されていることを確認

### 8. Gmail確認
1. **Gmailにアクセス**
   ```
   https://mail.google.com
   ```

2. **ラベル確認**
   左サイドバーに以下ラベルが作成されているか確認：
   - 📁 HALLEL
     - 📁 Processed
     - 📁 Booking
     - 📁 Cancellation
     - 📁 Shibuya

3. **メールラベリング確認**
   - hacomonoからの予約メールを開く
   - 上記ラベルが適用されているか確認

### 9. Vercel連携確認
1. **予約システムアクセス**
   ```
   https://hallelshibuyabooking-m1d4xnomi-aceboys-projects.vercel.app/admin
   ```

2. **ログイン**
   - パスワード: `hallel`

3. **予約データ確認**
   - GASから送信された予約が表示されているか確認

## 🚨 よくあるエラーと対処法

### エラー1: 「Gmail APIが見つかりません」
**対処法:**
1. 左メニュー「サービス」をクリック
2. Gmail APIが追加されているか確認
3. 未追加の場合は手順3を再実行

### エラー2: 「Exception: Request failed for https://...」
**対処法:**
1. WEBHOOK_URLが正しいか確認
2. インターネット接続を確認
3. Vercelサービスが稼働しているか確認

### エラー3: 「権限が不十分です」
**対処法:**
1. 手順5の権限承認を再実行
2. 全ての権限を「許可」したか確認

### エラー4: 「スクリプトを保存してから実行してください」
**対処法:**
1. Ctrl+S でスクリプトを保存
2. 保存完了を確認してから実行

## 📱 日常的な使用方法

### 手動で全メール同期
1. script.google.com にアクセス
2. HALLEL Gmail Sync プロジェクトを開く
3. 関数選択で「syncGmailReservations」を選択
4. 「実行」ボタンをクリック
5. ログで進行状況を確認

### 定期実行状況確認
1. 左メニュー「トリガー」をクリック
2. 最後の実行時間を確認
3. エラーがある場合は「実行数」をクリックして詳細確認

### ログ履歴確認
1. 左メニュー「実行数」をクリック
2. 各実行の詳細ログを確認
3. エラーの原因を特定

## ✅ 最終確認チェックリスト
- [ ] Google Apps Script プロジェクト作成完了
- [ ] Gmail API サービス追加完了
- [ ] スクリプトコード貼り付け完了
- [ ] 権限承認完了（Gmail/外部接続）
- [ ] テスト実行成功
- [ ] 定期トリガー設定完了
- [ ] Gmail ラベル作成確認
- [ ] Vercel システム連携確認
- [ ] 予約データ同期確認

**この手順で完璧なGmail全メール同期システムが完成！**