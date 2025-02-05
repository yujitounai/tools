from flask import Flask, request, render_template_string
import boto3
import botocore.exceptions

app = Flask(__name__)

# Bootstrap 5 を利用した HTML テンプレート
FORM_TEMPLATE = '''
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>AWS Credential Checker</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body>
    <div class="container my-4">
      <h1 class="mb-4">AWS Credential Checker</h1>
      <form method="POST" action="/">
        <div class="mb-3">
          <label for="access_key" class="form-label">AWS_ACCESS_KEY_ID</label>
          <input type="text" class="form-control" id="access_key" name="access_key" required>
        </div>
        <div class="mb-3">
          <label for="secret_key" class="form-label">AWS_SECRET_ACCESS_KEY</label>
          <input type="text" class="form-control" id="secret_key" name="secret_key" required>
        </div>
        <div class="mb-3">
          <label for="session_token" class="form-label">AWS_SESSION_TOKEN (任意)</label>
          <input type="text" class="form-control" id="session_token" name="session_token">
        </div>
        <!-- 固定リージョン（必要ならフォームに追加可） -->
        <button type="submit" class="btn btn-primary">確認する</button>
      </form>

      {% if error %}
        <div class="alert alert-danger mt-4" role="alert">
          {{ error }}
        </div>
      {% endif %}

      {% if result %}
        <div class="mt-4">
          <h2>基本情報</h2>
          <ul class="list-group">
            <li class="list-group-item"><strong>Account:</strong> {{ result.identity.Account }}</li>
            <li class="list-group-item"><strong>UserId:</strong> {{ result.identity.UserId }}</li>
            <li class="list-group-item"><strong>ARN:</strong> {{ result.identity.Arn }}</li>
          </ul>
        </div>

        {% if result.strong_privileges %}
          <div class="alert alert-warning mt-4" role="alert">
            <h4 class="alert-heading">強力な権限があります！</h4>
            <p>
              このアカウントは<strong>{{ result.strong_privileges | join(', ') }}</strong>などの強力なポリシーが付与されています。
              例えば <strong>AdministratorAccess</strong> があれば、アカウント内のほぼ全てのリソースに対して変更・削除・作成など、完全な操作が可能です。
              <br>
              <strong>PowerUserAccess</strong> や <strong>AmazonEC2FullAccess</strong> がある場合も、管理者並みの権限があり、EC2 の操作や他の主要サービスに対して広範なアクセスが可能です。
              セキュリティ上のリスクを十分に考慮して取り扱ってください。
            </p>
          </div>
        {% endif %}

        {% if result.permissions %}
          <div class="mt-4">
            <h2>権限情報</h2>
            {% if result.permissions.error %}
              <div class="alert alert-danger" role="alert">
                権限情報の取得中にエラーが発生しました: {{ result.permissions.error }}
              </div>
            {% else %}
              {% if result.permissions.UserDetails %}
                <h3>IAM ユーザー詳細</h3>
                <pre>{{ result.permissions.UserDetails | tojson(indent=2) }}</pre>
              {% endif %}
              {% if result.permissions.AttachedUserPolicies %}
                <h3>アタッチされたユーザーポリシー</h3>
                <pre>{{ result.permissions.AttachedUserPolicies | tojson(indent=2) }}</pre>
              {% endif %}
              {% if result.permissions.InlineUserPolicies %}
                <h3>インラインユーザーポリシー</h3>
                <pre>{{ result.permissions.InlineUserPolicies | tojson(indent=2) }}</pre>
              {% endif %}
              {% if result.permissions.RoleDetails %}
                <h3>IAM ロール詳細</h3>
                <pre>{{ result.permissions.RoleDetails | tojson(indent=2) }}</pre>
              {% endif %}
              {% if result.permissions.AttachedRolePolicies %}
                <h3>アタッチされたロールポリシー</h3>
                <pre>{{ result.permissions.AttachedRolePolicies | tojson(indent=2) }}</pre>
              {% endif %}
              {% if result.permissions.InlineRolePolicies %}
                <h3>インラインロールポリシー</h3>
                <pre>{{ result.permissions.InlineRolePolicies | tojson(indent=2) }}</pre>
              {% endif %}
              {% if result.permissions.message %}
                <p>{{ result.permissions.message }}</p>
              {% endif %}
            {% endif %}
          </div>
        {% endif %}

        {% if result.simulation %}
          <div class="mt-4">
            <h2>シミュレーション結果</h2>
            {% if result.simulation.policy_simulator %}
              <h3>IAM Policy Simulator 結果</h3>
              <pre>{{ result.simulation.policy_simulator | tojson(indent=2) }}</pre>
            {% endif %}
            {% if result.simulation.read_operations %}
              <h3>読み取り操作試行結果</h3>
              <pre>{{ result.simulation.read_operations | tojson(indent=2) }}</pre>
            {% endif %}
          </div>
        {% endif %}
      {% endif %}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
  </body>
</html>
'''

def get_permissions_info(session, caller_identity):
    """
    IAM の API を用いて、ユーザーまたはロールのポリシー情報を取得する。
    権限が不足している場合は例外をキャッチし、エラーメッセージを返します。
    """
    permissions = {}
    iam_client = session.client('iam')
    arn = caller_identity.get("Arn", "")
    try:
        if "assumed-role" in arn:
            # arn:aws:sts::<account>:assumed-role/<roleName>/<sessionName>
            parts = arn.split('/')
            if len(parts) >= 3:
                role_name = parts[1]
                # ロールの詳細取得
                role_response = iam_client.get_role(RoleName=role_name)
                permissions["RoleDetails"] = role_response.get("Role", {})
                # アタッチされたロールポリシーの取得
                attached_response = iam_client.list_attached_role_policies(RoleName=role_name)
                permissions["AttachedRolePolicies"] = attached_response.get("AttachedPolicies", [])
                # インラインポリシーの取得
                inline_response = iam_client.list_role_policies(RoleName=role_name)
                permissions["InlineRolePolicies"] = inline_response.get("PolicyNames", [])
            else:
                permissions["message"] = "ARN の解析に失敗しました。"
        elif "user" in arn:
            # arn:aws:iam::<account>:user/<username>
            user_response = iam_client.get_user()
            user = user_response.get("User", {})
            permissions["UserDetails"] = user
            user_name = user.get("UserName")
            # アタッチされたユーザーポリシーの取得
            attached_response = iam_client.list_attached_user_policies(UserName=user_name)
            permissions["AttachedUserPolicies"] = attached_response.get("AttachedPolicies", [])
            # インラインポリシーの取得
            inline_response = iam_client.list_user_policies(UserName=user_name)
            permissions["InlineUserPolicies"] = inline_response.get("PolicyNames", [])
        else:
            permissions["message"] = "不明な ARN 形式です。"
    except Exception as e:
        permissions["error"] = str(e)
    return permissions

def simulate_policy(session, policy_source_arn):
    """
    IAM Policy Simulator API を用いて、代表的なアクションに対する評価結果を取得する。
    ※呼び出しには iam:SimulatePrincipalPolicy の権限が必要です。
    """
    iam_client = session.client('iam')
    actions = ["s3:ListBuckets", "ec2:DescribeInstances", "iam:ListUsers", "cloudwatch:ListMetrics"]
    try:
        response = iam_client.simulate_principal_policy(
            PolicySourceArn=policy_source_arn,
            ActionNames=actions
        )
        simulation_results = {}
        for res in response.get("EvaluationResults", []):
            action = res.get("EvalActionName", "unknown")
            decision = res.get("EvalDecision", "unknown")
            simulation_results[action] = decision
        return simulation_results
    except Exception as e:
        return {"error": str(e)}

def simulate_read_operations(session):
    """
    S3, EC2, IAM の代表的な読み取り系 API を実際に呼び出し、実行可能かどうか試行する。
    """
    simulation_results = {}
    
    # S3: ListBuckets
    s3_client = session.client('s3')
    try:
        s3_client.list_buckets()
        simulation_results["s3:ListBuckets"] = "Success"
    except Exception as e:
        simulation_results["s3:ListBuckets"] = f"Error: {str(e)}"
    
    # EC2: DescribeInstances
    ec2_client = session.client('ec2')
    try:
        ec2_client.describe_instances(MaxResults=5)
        simulation_results["ec2:DescribeInstances"] = "Success"
    except Exception as e:
        simulation_results["ec2:DescribeInstances"] = f"Error: {str(e)}"
    
    # IAM: ListUsers
    iam_client = session.client('iam')
    try:
        iam_client.list_users(MaxItems=5)
        simulation_results["iam:ListUsers"] = "Success"
    except Exception as e:
        simulation_results["iam:ListUsers"] = f"Error: {str(e)}"
    
    return simulation_results

@app.route('/', methods=['GET', 'POST'])
def index():
    result = {}
    error = None

    if request.method == 'POST':
        access_key = request.form.get('access_key')
        secret_key = request.form.get('secret_key')
        session_token = request.form.get('session_token')
        # 固定のリージョン（必要に応じてフォームから入力させることも可）
        region = 'us-east-1'

        try:
            # 認証情報とリージョンを指定して boto3 セッションを作成
            session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                aws_session_token=session_token if session_token else None,
                region_name=region
            )
            sts = session.client('sts')
            identity = sts.get_caller_identity()
            result["identity"] = identity

            # IAM の権限情報取得を試行
            permissions = get_permissions_info(session, identity)
            result["permissions"] = permissions

            # attached policies を解析して、強力な権限があるかチェック
            strong_policies = []
            strong_names = ["AdministratorAccess", "PowerUserAccess", "AmazonEC2FullAccess"]

            if "AttachedUserPolicies" in permissions:
                for policy in permissions["AttachedUserPolicies"]:
                    if policy.get("PolicyName") in strong_names:
                        strong_policies.append(policy.get("PolicyName"))
            if "AttachedRolePolicies" in permissions:
                for policy in permissions["AttachedRolePolicies"]:
                    if policy.get("PolicyName") in strong_names:
                        strong_policies.append(policy.get("PolicyName"))
            if strong_policies:
                # 重複を除く
                result["strong_privileges"] = list(set(strong_policies))

            # もし権限情報取得に失敗（例外・エラー）した場合はシミュレーション処理を実行
            if permissions.get("error"):
                sim_policy = simulate_policy(session, identity.get("Arn"))
                sim_read = simulate_read_operations(session)
                result["simulation"] = {
                    "policy_simulator": sim_policy,
                    "read_operations": sim_read
                }
        except botocore.exceptions.ClientError as e:
            error = f"AWS API エラー: {e}"
        except Exception as e:
            error = f"エラー: {e}"

    return render_template_string(FORM_TEMPLATE, result=result if result else None, error=error)

if __name__ == '__main__':
    # Docker コンテナ内で外部アクセス可能にするためホストを 0.0.0.0 に指定
    app.run(host='0.0.0.0', port=5010)
