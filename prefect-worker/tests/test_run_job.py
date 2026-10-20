import run_job


def _run(monkeypatch, module, sent):
    monkeypatch.setattr(run_job, "send_alert", lambda job, code, tail: sent.append((job, code, tail)))
    monkeypatch.setattr("sys.argv", ["run_job.py", module])
    try:
        run_job.main()
    except SystemExit as e:
        return e.code


def test_success_sends_no_alert(monkeypatch, tmp_path):
    (tmp_path / "ok_job.py").write_text("print('fine')")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    sent = []
    assert _run(monkeypatch, "ok_job", sent) == 0
    assert sent == []


def test_failure_alerts_with_output_tail(monkeypatch, tmp_path):
    (tmp_path / "bad_job.py").write_text("print('about to die')\nraise RuntimeError('boom')")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    sent = []
    assert _run(monkeypatch, "bad_job", sent) == 1
    assert sent[0][0] == "bad_job" and "boom" in sent[0][2]


def test_send_alert_posts_to_ntfy_topic(monkeypatch):
    calls = []
    monkeypatch.setenv("NTFY_TOPIC", "t-123")
    monkeypatch.delenv("NTFY_URL", raising=False)

    class Resp:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(run_job.httpx, "post", lambda url, **kw: calls.append((url, kw)) or Resp())
    run_job.send_alert("flows.x", 2, "trace")
    url, kw = calls[0]
    assert url == "https://ntfy.sh/t-123"
    assert kw["content"] == b"trace" and "flows.x" in kw["headers"]["Title"]


def test_send_alert_without_topic_is_a_noop(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.setattr(run_job.httpx, "post", lambda *a, **k: 1 / 0)
    run_job.send_alert("flows.x", 1, "trace")
