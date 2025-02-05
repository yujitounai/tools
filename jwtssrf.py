# 認証に利用していると推測されるBearerトークンが送信されているSSRFの検証用
# 使い方
# pip install requests flask-jwt-extended
# python ./jwtssrf.py
# curl -X POST http://127.0.0.1:5001/login -H "Content-Type: application/json" -d '{"username": "admin", "password": "password"}'
# curl -X GET "http://127.0.0.1:5001/fetch?url=https://httpbin.org/get" -H "Authorization: Bearer [取得した Bearer token]"


from flask import Flask, request, jsonify
import requests
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity

app = Flask(__name__)

# シークレットキーの設定（本番環境ではより強固なものを使用）
app.config["JWT_SECRET_KEY"] = "super-secret-key"
jwt = JWTManager(app)

# ログインエンドポイント（デモ用）
@app.route('/login', methods=['POST'])
def login():
    username = request.json.get("username", None)
    password = request.json.get("password", None)

    # 簡易認証（本番ではDBと連携させる）
    if username != "admin" or password != "password":
        return jsonify({"msg": "Bad username or password"}), 401

    access_token = create_access_token(identity=username)
    return jsonify(access_token=access_token)

# JWT認証が必要なエンドポイント
@app.route('/fetch')
@jwt_required()
def fetch():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400

    # クライアントのAuthorizationヘッダをそのまま転送
    headers = {
        "Authorization": request.headers.get("Authorization")
    }

    # 外部URLへリクエストを転送
    response = requests.get(url, headers=headers)
    return response.content

if __name__ == '__main__':
    app.run(port=5001,debug=True)
