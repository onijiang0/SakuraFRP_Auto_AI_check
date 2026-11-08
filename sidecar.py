"""Private HTTP runner for a single SakuraFRP check-in."""
import base64
import hmac
import json
import os
import signal
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import sys
import threading
import tempfile

RUN_LOCK = threading.Lock()
MAX_REQUEST = 16384


def create_tls_context():
    cert = os.environ.get("SAKURA_RUNNER_TLS_CERT_B64", "")
    key = os.environ.get("SAKURA_RUNNER_TLS_KEY_B64", "")
    if not cert or not key:
        raise ValueError("TLS certificate and private key are required")
    cert_bytes = base64.b64decode(cert, validate=True)
    key_bytes = base64.b64decode(key, validate=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with tempfile.TemporaryDirectory(dir=os.environ["SAKURAFRP_DATA_DIR"]) as directory:
        cert_path, key_path = os.path.join(directory, "cert.pem"), os.path.join(directory, "key.pem")
        for path, value in ((cert_path, cert_bytes), (key_path, key_bytes)):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as file:
                file.write(value)
        context.load_cert_chain(cert_path, key_path)
    return context


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


def make_server(address=("0.0.0.0", 8765)):
    return ThreadingHTTPServer(address, Handler)


if __name__ == "__main__":
    if not os.environ.get("SAKURA_RUNNER_TOKEN") or not os.environ.get("SAKURAFRP_DATA_DIR"):
        raise SystemExit("SAKURA_RUNNER_TOKEN and SAKURAFRP_DATA_DIR are required")
    server = make_server()
    server.socket = create_tls_context().wrap_socket(server.socket, server_side=True)
    server.serve_forever()
