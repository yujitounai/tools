# 認証に利用していると推測されるBearerトークンが送信されているSSRFの検証用
# usage

```bash
# pip install requests flask-jwt-extended
# python ./jwtssrf.py
```

```bash
# curl -X POST http://127.0.0.1:5001/login -H "Content-Type: application/json" -d '{"username": "admin", "password": "password"}'
# curl -X GET "http://127.0.0.1:5001/fetch?url=https://httpbin.org/get" -H "Authorization: Bearer [取得した Bearer token]"
```
