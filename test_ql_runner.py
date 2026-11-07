import io
import json
import os
import unittest
from unittest import mock

import ql_runner


class RunnerTests(unittest.TestCase):
    def test_fails_before_sending_when_credentials_missing(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("ql_runner.urllib.request.build_opener") as opener:
            self.assertEqual(ql_runner.main(), 1)
            opener.assert_not_called()

    def test_reports_remote_failure(self):
        env = {"SAKURA_RUNNER_URL": "http://runner:8765/run", "SAKURA_RUNNER_TOKEN": "token", "SAKURAFRP_USERNAME": "alice", "SAKURAFRP_PASSWORD": "password", "ZHIPU_API_KEY": "key"}
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"exit_code": 1, "output": "not signed"}).encode()
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("ql_runner.urllib.request.build_opener", return_value=opener), mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(ql_runner.main(), 1)
            self.assertIn("not signed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
