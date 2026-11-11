import asyncio
import subprocess

import pytest

from app import library
from app.errors import AppError
from test_business import setup


def test_pdf_parsing_on_selector_event_loop(setup):
    config, _, papers = setup
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        result = runner.run(library.parse_pdf(papers / "study.pdf", config))
    assert len(result["pages"]) == 1
    assert "retrieval" in result["pages"][0]


@pytest.mark.parametrize("cancel", [False, True])
def test_pdf_timeout_and_cancel_reap_worker(setup, tmp_path, monkeypatch, cancel):
    config, _, papers = setup
    config.pdf_timeout_seconds = 0.15 if not cancel else 30
    (tmp_path / "pdf_worker.py").write_text("import time; time.sleep(30)", encoding="utf-8")
    monkeypatch.setattr(library, "__file__", str(tmp_path / "library.py"))
    spawned = []
    original = subprocess.Popen
    def track(*args, **kwargs):
        process = original(*args, **kwargs)
        spawned.append(process)
        return process
    monkeypatch.setattr(library.subprocess, "Popen", track)
    async def run():
        task = asyncio.create_task(library.parse_pdf(papers / "study.pdf", config))
        if cancel:
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(AppError) as error:
                await task
            assert error.value.code == "PDF_TIMEOUT"
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(run())
    assert spawned and all(p.poll() is not None for p in spawned)
