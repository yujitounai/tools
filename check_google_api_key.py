#!/usr/bin/env python3
import argparse
import json
import time
import requests
import sys
from urllib.parse import urljoin, urlparse, parse_qs
import re

def fetch_discovery_apis():
    """
    Google Discovery Service から公開されているすべての API 一覧を取得する
    """
    url = "https://www.googleapis.com/discovery/v1/apis"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("items", [])

def fetch_discovery_document(discovery_rest_url):
    """
    ある API の Discovery ドキュメント(JSON)を取得する
    """
    resp = requests.get(discovery_rest_url, timeout=30)
    resp.raise_for_status()
    return resp.json()

def extract_all_methods(discovery_doc):
    """
    Discovery ドキュメントから全てのメソッドを抽出する

    戻り値: [ { "httpMethod": "GET"/"POST"/..., "path": "...", ... }, ...]
    """
    methods = []

    # 直下の methods
    if "methods" in discovery_doc:
        for _, mdata in discovery_doc["methods"].items():
            methods.append(mdata)

    # resources の下にある methods を再帰的に取得
    def recurse_resources(resources):
        for _, resource_data in resources.items():
            # resource 直下の methods
            if "methods" in resource_data:
                for _, mdata in resource_data["methods"].items():
                    methods.append(mdata)
            # 下位リソースがあれば再帰的に探す
            if "resources" in resource_data:
                recurse_resources(resource_data["resources"])

    if "resources" in discovery_doc:
        recurse_resources(discovery_doc["resources"])

    return methods

def build_test_request_url(discovery_doc, method_info, api_key):
    """
    メソッド情報(httpMethod, path など)を使ってテスト用のURLを構築する
    - path に必須パラメータがある場合はダミー値を入れる
    - query パラメータに key=API_KEY を付与
    """

    base_url = discovery_doc.get("rootUrl")
    service_path = discovery_doc.get("servicePath")

    if not base_url or not service_path:
        # あるいは "baseUrl" が提供される場合を利用
        base_url = discovery_doc.get("baseUrl")
        if not base_url:
            return None  # 取得不可の場合

    # 例: path = "files/{fileId}"
    path = method_info["path"]
    # {xxx} 形式のパスパラメータをダミー値に置換
    path_replaced = re.sub(r"\{[^}]+\}", "test", path)

    # URL を結合
    combined_path = urljoin(urljoin(base_url, service_path), path_replaced)

    # key=API_KEY をクエリに付与
    if "?" in combined_path:
        test_url = f"{combined_path}&key={api_key}"
    else:
        test_url = f"{combined_path}?key={api_key}"
    return test_url

def test_method(api_key, discovery_doc, method_info):
    """
    実際に API キーを使ってリクエストを投げ、ステータスコードやレスポンスを返す

    戻り値 (dict):
      {
        "ok": bool,  # 200 or 400 なら True, それ以外は False
        "status_code": int,  # 実際のステータスコード
        "request_url": str,  # 送信したリクエストURL (クエリ文字列含む)
        "response_text": str,  # レスポンスボディ (text)
        "http_method": str,    # 実行したHTTPメソッド (GET/POST/...)
        "request_params": dict or None, # 実際に送信したパラメータ
      }
    """

    method = method_info["httpMethod"]
    url = build_test_request_url(discovery_doc, method_info, api_key)

    if not url:
        return {
            "ok": False,
            "status_code": None,
            "request_url": None,
            "response_text": None,
            "http_method": method,
            "request_params": None
        }

    # 送信パラメータを格納する変数
    request_params = None

    # 実際のHTTPリクエスト
    try:
        if method == "GET":
            parsed_url = urlparse(url)
            query_dict = parse_qs(parsed_url.query)  # {"key": ["YOUR_API_KEY"], ...}
            request_params = {"query": query_dict}

            resp = requests.get(url, timeout=10)

        elif method == "POST":
            payload = {}
            request_params = {"json": payload}
            resp = requests.post(url, json=payload, timeout=10)

        else:
            # 他のメソッド (PUT, DELETE, PATCH...) は必要に応じて追加
            return {
                "ok": False,
                "status_code": None,
                "request_url": url,
                "response_text": f"Not tested (unsupported method: {method})",
                "http_method": method,
                "request_params": None
            }
    except requests.RequestException as e:
        return {
            "ok": False,
            "status_code": None,
            "request_url": url,
            "response_text": f"Request error: {e}",
            "http_method": method,
            "request_params": request_params
        }

    status_code = resp.status_code
    ok = (status_code == 200 or status_code == 400)

    return {
        "ok": ok,
        "status_code": status_code,
        "request_url": url,
        "response_text": resp.text,
        "http_method": method,
        "request_params": request_params
    }

def main():
    parser = argparse.ArgumentParser(description="Google API キー検証ツール")
    parser.add_argument("api_key", help="テスト対象の Google API キー")
    parser.add_argument("--api_name", help="単一APIを指定するときの API 名 (例: 'calendar')")
    parser.add_argument("--api_version", help="単一APIを指定するときのバージョン (例: 'v3')")
    parser.add_argument("--output", default="api_check_result.json",
                        help="結果を保存する JSON ファイルのパス (デフォルト: api_check_result.json)")
    parser.add_argument("--limit_methods", type=int, default=0,
                        help="各 API についてテストするメソッド数の上限 (0 の場合は上限なし)")
    parser.add_argument("--sleep", type=float, default=0.5,
                        help="各メソッドの呼び出し間で待機する秒数 (短いとリクエスト過多になる場合があります)")
    parser.add_argument("--test_all_methods", action="store_true",
                        help="すべてのメソッドをテストし、結果をすべて記録する。指定しない場合は最初に200/400が返った時点で打ち切り。")
    args = parser.parse_args()

    api_key = args.api_key
    output_file = args.output
    method_limit = args.limit_methods
    sleep_time = args.sleep
    test_all_methods = args.test_all_methods

    print("==== Google Discovery API から API リストを取得中 ====")
    all_apis = fetch_discovery_apis()
    print(f"取得した API 数: {len(all_apis)}")

    # 単一 API を指定している場合は、name & version でフィルター
    if args.api_name and args.api_version:
        filtered_apis = [
            api for api in all_apis
            if api.get("name") == args.api_name and api.get("version") == args.api_version
        ]
        if len(filtered_apis) == 0:
            print(f"ERROR: name='{args.api_name}' version='{args.api_version}' に一致するAPIが見つかりませんでした。")
            sys.exit(1)
        elif len(filtered_apis) > 1:
            print(f"ERROR: name='{args.api_name}' version='{args.api_version}' に複数の候補が見つかりました。想定外です。")
            sys.exit(1)
        else:
            # 単一の API に絞り込む
            all_apis = filtered_apis
            print(f"指定されたAPI (name='{args.api_name}', version='{args.api_version}') のみを検証します。")

    elif args.api_name or args.api_version:
        # ユーザが片方だけ指定しているケースは想定外とし、エラー扱い
        print("ERROR: --api_name と --api_version はセットで指定してください。")
        sys.exit(1)

    result = []
    for i, api_item in enumerate(all_apis, start=1):
        name = api_item.get("name")
        version = api_item.get("version")
        discovery_url = api_item.get("discoveryRestUrl")

        print(f"[{i}/{len(all_apis)}] {name} ({version}) のチェックを開始...")

        try:
            discovery_doc = fetch_discovery_document(discovery_url)
        except requests.RequestException as e:
            print(f"  ! Discovery ドキュメント取得失敗: {e}")
            continue

        # メソッド一覧の取得
        methods = extract_all_methods(discovery_doc)
        if not methods:
            print("  ! メソッド情報が見つからないためスキップ")
            continue

        # =================================================================
        # test_all_methods が true なら、全メソッドをチェックして
        # すべての結果を記録する。
        # test_all_methods が false なら、最初に 200/400 が返ったら打ち切り。
        # =================================================================
        if test_all_methods:
            method_results = []
            tested_count = 0

            for method_info in methods:
                tested_count += 1
                tr = test_method(api_key, discovery_doc, method_info)
                method_results.append(tr)

                if method_limit > 0 and tested_count >= method_limit:
                    break

                time.sleep(sleep_time)

            # このAPIで 1つでも ok==True のメソッドがあれば "usable": True
            usable = any(m["ok"] for m in method_results)

            api_result = {
                "name": name,
                "version": version,
                "discovery_url": discovery_url,
                "usable": usable,
                "methods": []  # 各メソッドの結果をすべて入れる
            }

            # method_results を整形して格納
            for mres in method_results:
                api_result["methods"].append({
                    "http_method": mres["http_method"],
                    "request_url": mres["request_url"],
                    "status_code": mres["status_code"],
                    "response_text": mres["response_text"],
                    "request_params": mres["request_params"],
                    "ok": mres["ok"]
                })

            # ログ出力用メッセージ
            if usable:
                print("  => 利用可能性あり (少なくとも 1 メソッドで 200 or 400 を確認)")
            else:
                print("  => 利用可能性なし (該当メソッドなし)")
            
            result.append(api_result)

        else:
            # 従来の動作: 最初に 200/400 が返ったメソッドのみを保存
            valid_endpoint_found = False
            tested_count = 0
            detail_for_this_api = None

            for method_info in methods:
                tested_count += 1
                test_result = test_method(api_key, discovery_doc, method_info)
                if test_result["ok"]:
                    valid_endpoint_found = True
                    detail_for_this_api = {
                        "name": name,
                        "version": version,
                        "discovery_url": discovery_url,
                        "http_method": test_result["http_method"],
                        "request_url": test_result["request_url"],
                        "status_code": test_result["status_code"],
                        "response_text": test_result["response_text"],
                        "request_params": test_result["request_params"],
                    }
                    break

                if method_limit > 0 and tested_count >= method_limit:
                    break

                time.sleep(sleep_time)

            if valid_endpoint_found and detail_for_this_api is not None:
                print("  => 利用可能性あり (少なくとも 1 メソッドで 200 or 400 を確認)")
                result.append(detail_for_this_api)
            else:
                print("  => 利用可能性なし (該当メソッドなし)")

    # 結果を JSON 保存
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # test_all_methods の場合は result が配列の中に APIごとの情報を入れている。
    # 従来の場合も従来通りの形で1 API 1エントリ (成功時のみ) を入れている。

    # 最終ログ表示
    if test_all_methods:
        print(f"\n==== 結果 ====\n検証した API 数: {len(result)} 件 (全メソッドの結果を記録)")
    else:
        print(f"\n==== 結果 ====\n利用可能性ありと判定された API: {len(result)} 件 (最初の成功のみ記録)")
    print(f"結果は {output_file} に保存しました。")

if __name__ == "__main__":
    main()
