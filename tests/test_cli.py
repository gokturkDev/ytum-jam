import os
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import AsyncMock

import httpx
import pytest
import uvicorn

from ambassador.adapters.fake import FakeEvaluator
from ambassador.api.app import create_app
from ambassador.cli.__main__ import command
from ambassador.config import Settings
from ambassador.scenarios.loader import load_scenarios


@pytest.fixture
def live_server(service):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(service, Settings(_env_file=None, llm_backend="fake")),
            log_level="error",
            lifespan="on",
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive()


@pytest.mark.parametrize("win", [True, False])
def test_shipped_cli_readable_faceoff(live_server, service, win):
    service.scenarios = {s.id: s for s in load_scenarios()}
    if win:

        class Good(FakeEvaluator):
            async def evaluate(self, context):
                decision = await super().evaluate(context)
                for a in decision.assessments:
                    a.score = 20
                return decision

        service.evaluator = Good()
    result = subprocess.run(
        [sys.executable, "-m", "ambassador.cli", "--base-url", live_server],
        input=(
            "1\nHerkese fırça dağıtalım!\nKullanmayı gösterelim!\n/gonder\n"
            "Birkaç dakika yeter!\n/gonder\nBirlikte öğrenelim!\n/gonder\n"
        ),
        text=True,
        capture_output=True,
        timeout=15,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "BETİKLİ DEMO" in output and "Halk düşünüyor..." in output
    assert ("Zafer!" if win else "Reform henüz yeterli destek bulamadı.") in output
    assert "Reformcu kralın gündemi" in output
    assert "Tur 1/3" in output and "Tur 3/3" in output
    assert "Sempati" not in output and "10 destekçi" not in output
    # Each round displays only its current 1-3 one-sentence objections.
    for number in range(1, 4):
        section = output.split(f"Tur {number}/3")[1].split("İtirazlara cevabınızı")[0]
        lines = [line for line in section.splitlines() if line.startswith("  ")]
        assert 1 <= len(lines) <= 3
        assert all(len(line) < 220 for line in lines)
    assert "yüzde puan" in output and "Traceback" not in output


async def test_network_retry_preserves_id_and_answer(monkeypatch):
    import ambassador.cli.__main__ as cli

    monkeypatch.setattr(cli, "ask", AsyncMock(return_value=""))
    seen = []

    def handle(request):
        seen.append(request.content)
        if len(seen) == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, json={"success": True})

    body = {"request_id": "same-id", "expected_version": 0, "text": "Pasta benden!"}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://test"
    ) as client:
        assert await command(client, "/answers", body) == {"success": True}
    assert len(seen) == 2 and seen[0] == seen[1]
