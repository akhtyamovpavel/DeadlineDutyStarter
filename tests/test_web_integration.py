"""Проверка взаимодействия клиентского кода с работающим сервисом."""

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler
from urllib.request import build_opener

import pytest


PROJECT = Path(__file__).resolve().parents[1]

SERVER_CODE = """
import socket
import sys
import uvicorn

listener = socket.fromfd(int(sys.argv[1]), socket.AF_INET, socket.SOCK_STREAM)
config = uvicorn.Config("app.main:app", log_level="warning")
server = uvicorn.Server(config)
server.run(sockets=[listener])
"""


def test_client_scenario_with_real_service(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for the client integration check")

    environment = os.environ.copy()
    environment["DEADLINES_DB_PATH"] = str(tmp_path / "integration.sqlite3")
    environment["AUTH_USERNAME"] = "test-user"
    environment["AUTH_PASSWORD"] = "test-password"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        command = [sys.executable, "-c", SERVER_CODE, str(listener.fileno())]
        with subprocess.Popen(
            command,
            cwd=PROJECT,
            env=environment,
            pass_fds=(listener.fileno(),),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) as server:
            try:
                origin = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 15
                opener = build_opener(ProxyHandler({}))
                while True:
                    try:
                        with opener.open(f"{origin}/health", timeout=1) as response:
                            assert response.status == 200
                        break
                    except (URLError, TimeoutError):
                        if server.poll() is not None or time.monotonic() >= deadline:
                            pytest.fail("The integration test server did not start")
                        time.sleep(0.05)

                environment["WEB_INTEGRATION_ORIGIN"] = origin
                result = subprocess.run(
                    [node, "tests/web_integration.js"],
                    cwd=PROJECT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                assert result.returncode == 0, result.stdout + result.stderr
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
