"""Private HTTP runner for a single SakuraFRP check-in."""
import hmac
import json
import os
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import sys
import threading

RUN_LOCK = threading.Lock()
MAX_REQUEST = 16384


def terminate_process(process):
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, data):
        result = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(result)))
        self.end_headers()
        self.wfile.write(result)

    def do_POST(self):
        token = os.environ.get("SAKURA_RUNNER_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        if not token or not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
            return self.reply(401, {"error": "unauthorized"})
        if self.path != "/run":
            return self.reply(404, {"error": "not found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_REQUEST:
                raise ValueError("invalid request length")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict) or any(not isinstance(body.get(k), str) or not body[k] for k in ("username", "password", "api_key")):
                raise ValueError("missing credentials")
        except (ValueError, UnicodeError):
            return self.reply(400, {"error": "invalid request"})
        if not RUN_LOCK.acquire(blocking=False):
            return self.reply(409, {"error": "already running"})
        try:
            env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TZ", "PLAYWRIGHT_BROWSERS_PATH", "SAKURAFRP_DATA_DIR")}
            env.update(SAKURAFRP_USERNAME=body["username"], SAKURAFRP_PASSWORD=body["password"], ZHIPU_API_KEY=body["api_key"])
            for key in ("ZHIPU_MODEL_VISION", "ZHIPU_MODEL_TEXT"):
                if isinstance(body.get(key), str) and 0 < len(body[key]) <= 100:
                    env[key] = body[key]
            try:
                process = subprocess.Popen([sys.executable, "-u", "/app/main.py"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
                try:
                    output, _ = process.communicate(timeout=600)
                except subprocess.TimeoutExpired:
                    terminate_process(process)
                    try:
                        process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        if process.stdout:
                            process.stdout.close()
                    raise
                output = output[-100000:]
                for secret in (body["password"], body["api_key"], token):
                    output = output.replace(secret, "[redacted]")
                self.reply(200, {"exit_code": process.returncode, "output": output})
            except subprocess.TimeoutExpired:
                self.reply(504, {"error": "check-in timed out"})
        finally:
            RUN_LOCK.release()


def make_server(address=("127.0.0.1", 8765)):
    return ThreadingHTTPServer(address, Handler)


if __name__ == "__main__":
    if not os.environ.get("SAKURA_RUNNER_TOKEN") or not os.environ.get("SAKURAFRP_DATA_DIR"):
        raise SystemExit("SAKURA_RUNNER_TOKEN and SAKURAFRP_DATA_DIR are required")
    make_server().serve_forever()
