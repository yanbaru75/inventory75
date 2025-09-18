\
# 喫茶店 在庫アプリ（Flask + SQLite）

## 1) セットアップ
```bash
# 1. 仮想環境（任意）を作成・有効化
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 2. 依存をインストール
pip install -r requirements.txt

# 3. アプリ起動（初回はDBと初期ユーザーが自動作成）
python app.py
# ブラウザで http://localhost:8000 にアクセス
```

- 初期ユーザー： `admin` / `admin123`（ログイン後に変更してください）

## 2) 使い方（MVP）
- まず「仕入先」を登録 → 次に「品目」を登録（発注点・PARも入力）
- 日々は「入出庫登録」で 仕入（入庫）/ 使用（出庫）/ 廃棄 / 調整 を記録
- 「在庫一覧」で現在庫・発注点割れ（赤）・推奨発注数が見えます

## 3) よくある質問
- DB は `instance/inventory.db`（1ファイル）。コピーでバックアップ可能
- 同じWi‑Fi内のスマホから使うには `python app.py` 実行後、表示URLの `127.0.0.1` をPCのIPに置き換えてアクセス
- 本番公開は Render / Fly.io などのPaaSを利用すると簡単です
