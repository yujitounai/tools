# Python の公式イメージを使用（例: Python 3.9-slim）
FROM python:3.9-slim

# 作業ディレクトリの作成
WORKDIR /app

# 依存ライブラリをコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのコードをコピー
COPY app.py .

# コンテナのポート 5010 を公開
EXPOSE 5010

# アプリケーションの起動
CMD ["python", "app.py"]
