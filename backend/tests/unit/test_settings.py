from __future__ import annotations

from forestwatch.settings import Settings

FAKE_PASSWORD = "not-a-real-password-7f3a"


def test_cdse_password_is_kept_out_of_repr_and_dumps():
    s = Settings(_env_file=None, cdse_username="someone", cdse_password=FAKE_PASSWORD)
    assert FAKE_PASSWORD not in repr(s)
    assert FAKE_PASSWORD not in str(s)
    assert FAKE_PASSWORD not in s.model_dump_json()
    assert s.cdse_password.get_secret_value() == FAKE_PASSWORD


def test_empty_cdse_password_counts_as_not_configured():
    # .env.example ships SYLVA_CDSE_PASSWORD= (empty); that must not look configured
    s = Settings(_env_file=None, cdse_username="someone", cdse_password="")
    assert not bool(s.cdse_username and s.cdse_password)
    assert not bool(Settings(_env_file=None).cdse_password)


def test_cdse_token_request_sends_the_plain_password(monkeypatch):
    from forestwatch.providers import cdse

    sent = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "tok"}

    def fake_post(url, data, timeout):
        sent.update(data)
        return _Resp()

    monkeypatch.setattr(cdse, "get_settings", lambda: Settings(_env_file=None, cdse_username="u", cdse_password=FAKE_PASSWORD))
    monkeypatch.setattr(cdse.httpx, "post", fake_post)
    assert cdse.CDSEProvider.access_token(object()) == "tok"
    assert sent["password"] == FAKE_PASSWORD
