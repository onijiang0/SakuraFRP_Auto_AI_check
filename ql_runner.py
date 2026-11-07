"""Trigger the isolated SakuraFRP runner from Qinglong."""
import json
import os
import sys
import urllib.error
import urllib.request


def main():
    keys = ("SAKURA_RUNNER_URL", "SAKURA_RUNNER_TOKEN", "SAKURAFRP_USERNAME", "SAKURAFRP_PASSWORD", "ZHIPU_API_KEY")
    missing = [key for key in keys if not os.environ.get(key)]
    if missing:
        print("缺少环境变量：" + ", ".join(missing))
        return 1
    payload = {"username": os.environ["SAKURAFRP_USERNAME"], "password": os.environ["SAKURAFRP_PASSWORD"], "api_key": os.environ["ZHIPU_API_KEY"]}
    for key in ("ZHIPU_MODEL_VISION", "ZHIPU_MODEL_TEXT"):
        if os.environ.get(key):
            payload[key] = os.environ[key]
    request = urllib.request.Request(os.environ["SAKURA_RUNNER_URL"], data=json.dumps(payload).encode(), method="POST", headers={"Authorization": "Bearer " + os.environ["SAKURA_RUNNER_TOKEN"], "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=630) as response:
            result = json.loads(response.read())
        print(result.get("output", ""))
        return 0 if result.get("exit_code") == 0 else 1
    except (OSError, ValueError, KeyError) as error:
        print("独立容器运行失败：" + type(error).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
