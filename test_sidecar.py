import http.client
import json
import os
import threading
import unittest
from unittest import mock

import sidecar


class SidecarTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"SAKURA_RUNNER_TOKEN": "shared-secret", "SAKURAFRP_DATA_DIR": "/private"}, clear=True)
        self.env.start()
        self.server = sidecar.make_server(("127.0.0.1", 0))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.env.stop()

    def request(self, token="shared-secret", body=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.request("POST", "/run", body=json.dumps(body or {"username": "alice", "password": "pw", "api_key": "key"}), headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        response = connection.getresponse()
        result = (response.status, json.loads(response.read()))
        connection.close()
        return result

    def test_unauthorized_does_not_run_script(self):
        with mock.patch("sidecar.subprocess.Popen") as run:
            status, _ = self.request(token="wrong")
            self.assertEqual(status, 401)
            run.assert_not_called()

    def test_default_server_listens_on_container_network(self):
        with mock.patch("sidecar.ThreadingHTTPServer") as server:
            sidecar.make_server()
            self.assertEqual(server.call_args.args[0], ("0.0.0.0", 8765))

    def test_server_rejects_missing_tls_material(self):
        with self.assertRaises(ValueError):
            sidecar.create_tls_context()

    def test_run_passes_private_values_only_as_environment(self):
        process = mock.Mock(returncode=0)
        process.communicate.return_value = ("checked", None)
        with mock.patch("sidecar.subprocess.Popen", return_value=process) as run:
            status, result = self.request()
            self.assertEqual((status, result["exit_code"], result["output"]), (200, 0, "checked"))
            args, kwargs = run.call_args
            self.assertNotIn("pw", str(args))
            self.assertEqual(kwargs["env"]["SAKURAFRP_PASSWORD"], "pw")
            self.assertEqual(kwargs["env"]["SAKURAFRP_DATA_DIR"], "/private")
            self.assertNotIn("SAKURA_RUNNER_TOKEN", kwargs["env"])

    def test_concurrent_request_is_rejected(self):
        with sidecar.RUN_LOCK:
            status, _ = self.request()
            self.assertEqual(status, 409)

    def test_failure_exit_code_is_returned(self):
        process = mock.Mock(returncode=1)
        process.communicate.return_value = ("failed", None)
        with mock.patch("sidecar.subprocess.Popen", return_value=process):
            status, result = self.request()
            self.assertEqual((status, result["exit_code"]), (200, 1))

    def test_timeout_terminates_process_group(self):
        process = mock.Mock(pid=42)
        process.communicate.side_effect = [sidecar.subprocess.TimeoutExpired("main", 600), ("", None)]
        with mock.patch("sidecar.subprocess.Popen", return_value=process), mock.patch("sidecar.terminate_process") as terminate:
            status, _ = self.request()
            self.assertEqual(status, 504)
            terminate.assert_called_once_with(process)


if __name__ == "__main__":
    unittest.main()
