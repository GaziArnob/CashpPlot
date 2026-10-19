"""Secrets pasted into a hosting dashboard often carry stray characters; they are cleaned when settings load."""

import pytest

from app.config import Settings


@pytest.mark.parametrize("pasted", ["EAAB123", " EAAB123 ", "EAAB123\n", "\"EAAB123\"", "'EAAB123'", "Bearer EAAB123",
                                    "  bearer   EAAB123\r\n", "\" Bearer EAAB123 \""])
def test_a_pasted_token_is_cleaned(pasted):
    assert Settings(whatsapp_token=pasted).whatsapp_token == "EAAB123"


def test_other_secrets_and_empty_values(monkeypatch):
    s = Settings(twilio_auth_token=" abc ", smtp_password="\"app password\"", whatsapp_phone_number_id=" 123456789012345\n",
                 brevo_api_key="", plaid_secret=" s ")
    assert (s.twilio_auth_token, s.smtp_password, s.whatsapp_phone_number_id, s.brevo_api_key, s.plaid_secret) == \
        ("abc", "app password", "123456789012345", "", "s")


def test_settings_that_are_not_secrets_are_left_alone():
    assert Settings(cors_origins=" http://a.com , http://b.com ").cors_origin_list == ["http://a.com", "http://b.com"]
