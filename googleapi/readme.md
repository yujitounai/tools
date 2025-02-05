# usage

## どのAPIが使えるかをざっくり調査

```bash
$ python check_google_api_key.py AIxx --output check_result.json --limit_methods 1 --sleep 0.5
```

## 1APIの全メソッドを試す

```bash
python check_google_api_key.py AIxx --output check_result.json --limit_methods 0 --sleep 0.5 --api_name customsearch --api_version v1 --test_all_methods
```
