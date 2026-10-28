"""bridge.yemot_setup against a local mock of the Yemot management API."""

import os
import stat

from aiohttp import web

from bridge import yemot_setup


class MockYemot:
    def __init__(self, existing=None, fail=None, extensions=()):
        self.extensions = set(extensions)
        self.calls = []
        self.accounts = list(existing or [])
        self.fail = fail

    async def handler(self, req: web.Request):
        cmd = req.match_info["cmd"]
        body = await req.json()
        self.calls.append((cmd, body, req.headers.get("authorization"), dict(req.query)))
        if req.headers.get("authorization") != "good-token" or cmd == self.fail:
            return web.json_response({"responseStatus": "ERROR", "message": "denied", "messageCode": 7})
        if cmd == "CheckIfFileExists":
            return web.json_response({"responseStatus": "OK", "path": body["path"],
                                      "fileExists": body["path"] in {f"ivr2:{e}/ext.ini" for e in self.extensions}})
        if cmd == "GetSipAccountsInCustomer":
            return web.json_response({"responseStatus": "OK", "accounts": self.accounts, "accountLimit": 6})
        if cmd == "CreateSipAccount":
            acc = {"id": "0772222770=2", "accountNumber": 2, "extensionNote": body.get("extensionNote"),
                   "password": "S3cretPass"}
            self.accounts.append(acc)
            return web.json_response({"responseStatus": "OK", "accountID": acc["id"], "accountNumber": 2,
                                      "PASS": acc["password"]})
        return web.json_response({"responseStatus": "OK"})


async def start(mock: MockYemot):
    app = web.Application()
    app.add_routes([web.post("/ym/api/{cmd}", mock.handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}/ym/api"


async def test_creates_account_configures_extension_and_writes_env(tmp_path, monkeypatch, capsys):
    mock = MockYemot()
    runner, base = await start(mock)
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=k\nYEMOT_SIP_USER=old\nSIP_PORT=5060\n")
    env.chmod(0o640)
    monkeypatch.setenv("YEMOT_API_TOKEN", "good-token")
    try:
        rc = await yemot_setup.run(["--extension", "/5", "--host", "sip.example.test", "--env", str(env),
                                    "--api-base", base])
    finally:
        await runner.cleanup()
    assert rc == 0
    cmds = [c[0] for c in mock.calls]
    assert cmds == ["CheckIfFileExists", "GetSipAccountsInCustomer", "CreateSipAccount", "SipToUdp", "UpdateExtension"]
    assert mock.calls[0][1]["path"] == "ivr2:5/ext.ini"
    ext = mock.calls[4][1]
    assert ext["path"] == "ivr2:5" and ext["type"] == "sip" and ext["account_dial_number"] == 2
    assert all(c[2] == "good-token" and not c[3] for c in mock.calls)  # token only in the header, never in the URL
    text = env.read_text()
    assert "YEMOT_SIP_USER=0772222770=2" in text and "YEMOT_SIP_PASSWORD=S3cretPass" in text
    assert "YEMOT_REGISTER_HOST=sip.example.test" in text and "GEMINI_API_KEY=k" in text
    assert text.count("YEMOT_SIP_USER=") == 1  # replaced in place, not duplicated
    assert stat.S_IMODE(os.stat(env).st_mode) == 0o640
    out = capsys.readouterr().out
    assert "S3cretPass" not in out and "good-token" not in out


async def test_reuses_existing_gemini_bridge_account(tmp_path, monkeypatch):
    mock = MockYemot(existing=[{"id": "0772222770=4", "accountNumber": 4, "extensionNote": "gemini-bridge",
                                "password": "OldPass"}])
    runner, base = await start(mock)
    env = tmp_path / ".env"
    monkeypatch.setenv("YEMOT_API_TOKEN", "good-token")
    try:
        rc = await yemot_setup.run(["--extension", "5", "--env", str(env), "--api-base", base])
    finally:
        await runner.cleanup()
    assert rc == 0 and "CreateSipAccount" not in [c[0] for c in mock.calls]
    assert mock.calls[-1][1]["account_dial_number"] == 4
    assert "YEMOT_SIP_PASSWORD=OldPass" in env.read_text()
    assert stat.S_IMODE(os.stat(env).st_mode) == 0o600  # a newly created env file is private


async def test_api_error_aborts_without_touching_env(tmp_path, monkeypatch, capsys):
    mock = MockYemot()
    runner, base = await start(mock)
    env = tmp_path / ".env"
    monkeypatch.setenv("YEMOT_API_TOKEN", "wrong")
    try:
        rc = await yemot_setup.run(["--extension", "5", "--env", str(env), "--api-base", base])
    finally:
        await runner.cleanup()
    assert rc == 1 and not env.exists()
    assert "FAILED: CheckIfFileExists: ERROR denied" in capsys.readouterr().out
    assert len(mock.calls) == 1  # stops at the first failure


async def test_use_account_picks_a_specific_existing_account(tmp_path, monkeypatch, capsys):
    mock = MockYemot(existing=[
        {"id": "086693864", "accountNumber": 1, "extensionNote": None, "password": "Pw1"},
        {"id": "086693864=2", "accountNumber": 2, "extensionNote": None, "password": "Pw2"}])
    runner, base = await start(mock)
    env = tmp_path / ".env"
    monkeypatch.setenv("YEMOT_API_TOKEN", "good-token")
    try:
        rc = await yemot_setup.run(["--extension", "7", "--use-account", "086693864", "--host", "sip.yemot.co.il",
                                    "--env", str(env), "--api-base", base])
        rc_missing = await yemot_setup.run(["--extension", "7", "--use-account", "nope", "--env", str(env) + "2",
                                            "--api-base", base])
    finally:
        await runner.cleanup()
    assert rc == 0 and "CreateSipAccount" not in [c[0] for c in mock.calls]
    text = env.read_text()
    assert "YEMOT_SIP_USER=086693864" in text and "YEMOT_SIP_PASSWORD=Pw1" in text
    assert "YEMOT_REGISTER_HOST=sip.yemot.co.il" in text
    assert [c[1] for c in mock.calls if c[0] == "UpdateExtension"][0]["account_dial_number"] == 1
    assert rc_missing == 1 and "no SIP account 'nope'" in capsys.readouterr().out


async def test_extension_1522_is_created_when_missing(tmp_path, monkeypatch, capsys):
    mock = MockYemot()
    runner, base = await start(mock)
    monkeypatch.setenv("YEMOT_API_TOKEN", "good-token")
    try:
        rc = await yemot_setup.run(["--extension", "1522", "--use-account", "x", "--env", str(tmp_path / ".env"),
                                    "--api-base", base])
        assert rc == 1  # account 'x' does not exist -> clean failure, nothing created
        assert "UpdateExtension" not in [c[0] for c in mock.calls]
        rc = await yemot_setup.run(["--extension", "1522", "--env", str(tmp_path / ".env"), "--api-base", base])
    finally:
        await runner.cleanup()
    assert rc == 0
    assert "does not exist yet; it will be created" in capsys.readouterr().out
    upd = [c[1] for c in mock.calls if c[0] == "UpdateExtension"][0]
    assert upd["path"] == "ivr2:1522" and upd["type"] == "sip"


async def test_existing_extension_is_not_overwritten_without_flag(tmp_path, monkeypatch, capsys):
    mock = MockYemot(extensions={"1522"})
    runner, base = await start(mock)
    env = tmp_path / ".env"
    monkeypatch.setenv("YEMOT_API_TOKEN", "good-token")
    try:
        rc = await yemot_setup.run(["--extension", "1522", "--env", str(env), "--api-base", base])
        assert rc == 3 and "already exists" in capsys.readouterr().out
        assert [c[0] for c in mock.calls] == ["CheckIfFileExists"] and not env.exists()  # nothing changed
        rc = await yemot_setup.run(["--extension", "1522", "--use-existing", "--env", str(env), "--api-base", base])
    finally:
        await runner.cleanup()
    assert rc == 0 and "UpdateExtension" in [c[0] for c in mock.calls]


async def test_token_can_be_read_from_a_file(tmp_path, monkeypatch):
    mock = MockYemot()
    runner, base = await start(mock)
    token_file = tmp_path / "token"
    token_file.write_text("good-token\n")
    monkeypatch.delenv("YEMOT_API_TOKEN", raising=False)
    try:
        rc = await yemot_setup.run(["--extension", "5", "--token-file", str(token_file),
                                    "--env", str(tmp_path / ".env"), "--api-base", base])
    finally:
        await runner.cleanup()
    assert rc == 0 and all(c[2] == "good-token" for c in mock.calls)
