import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clip_recht_check import generate_source_notice, is_valid_http_url


class SourceNoticeTests(unittest.TestCase):
    def test_accepts_http_and_https(self):
        self.assertTrue(is_valid_http_url("https://example.com/video"))
        self.assertTrue(is_valid_http_url("http://example.com/video"))

    def test_rejects_non_http_or_credentials(self):
        self.assertFalse(is_valid_http_url("javascript:alert(1)"))
        self.assertFalse(is_valid_http_url("https://user:pass@example.com/"))
        self.assertFalse(is_valid_http_url("not a url"))
        self.assertFalse(is_valid_http_url("https://example.com:bad/path"))

    def test_notice_does_not_claim_legal_clearance(self):
        notice = generate_source_notice("Kanal", "Streamtitel", "https://example.com/vod", "Lizenz")
        self.assertIn("Quellenangabe allein erteilt keine Nutzungsrechte.", notice)
        self.assertIn("https://example.com/vod", notice)

    def test_empty_fields_raise(self):
        with self.assertRaises(ValueError):
            generate_source_notice("", "Titel", "https://example.com")


if __name__ == "__main__":
    unittest.main()
