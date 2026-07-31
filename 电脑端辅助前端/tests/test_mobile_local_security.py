from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MobileLocalSecurityTests(unittest.TestCase):
    def test_login_form_never_embeds_demo_credentials_or_plaintext_password_input(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('value="123459"', html)
        self.assertNotIn('id="loginUsername" value="1608601"', html)
        self.assertIn('id="loginPassword" type="password" value=""', html)

    def test_mobile_login_has_no_extra_credential_consent_gate(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('id="loginCredentialConsent"', html)
        self.assertNotIn("credentialConsent", app)

    def test_password_field_is_cleared_after_each_submission(self) -> None:
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        submit = app[app.index('document.getElementById("loginSubmit").onclick'):]
        self.assertIn("finally {", submit)
        self.assertIn('document.getElementById("loginPassword").value = ""', submit)


if __name__ == "__main__":
    unittest.main()
