このツールは、Web ページ上のフォームから AWS の認証情報（AWS_ACCESS_KEY_ID、AWS_SECRET_ACCESS_KEY、およびオプションの AWS_SESSION_TOKEN）を受け取り、AWS STS の get_caller_identity API を呼び出すことで、どのアカウント・ユーザーであるかを確認して結果を返します。また、Docker を使ってコンテナ内で実行できるようにしています。

- Usage

```bash
docker build -t aws-credential-checker .
docker run -p 5010:5010 aws-credential-checker
```

Open http://localhost:5010

