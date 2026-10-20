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
