"""Validação de URL do Instagram (função pura, sem rede)."""
from __future__ import annotations

import unittest
from urllib.parse import urlsplit

from tests import helpers as H  # noqa: F401  (ajusta sys.path)

import extractor as E

VALID = [
    "https://www.instagram.com/p/C1a2B3c4D5e/",
    "https://www.instagram.com/reel/C1a2B3c4D5e/",
    "https://www.instagram.com/reels/C1a2B3c4D5e/",
    "https://www.instagram.com/tv/C1a2B3c4D5e/",
    "https://instagram.com/p/C1a2B3c4D5e",
    "https://m.instagram.com/reel/C1a2B3c4D5e/",
    "https://www.instagram.com/p/C1a2B3c4D5e/?igsh=abc123&utm_source=ig_web_copy_link",
    "https://www.instagram.com/reel/Cx_-9aB/#frag",
    "  https://www.instagram.com/p/C1a2B3c4D5e/  ",   # espaços nas pontas (colado)
    "https://WWW.INSTAGRAM.COM/p/C1a2B3c4D5e/",
    "http://www.instagram.com/p/C1a2B3c4D5e/",
    "https://www.instagram.com/some.user/p/C1a2B3c4D5e/",
]

INVALID = [
    "",
    "   ",
    "não é url",
    "https://www.instagram.com.evil.com/p/C1a2B3c4D5e/",
    "https://instagram.com.evil.com/p/C1a2B3c4D5e/",
    "https://evilinstagram.com/p/C1a2B3c4D5e/",
    "https://instagram.evil.com/p/C1a2B3c4D5e/",
    "https://www.instagram.com@evil.com/p/C1a2B3c4D5e/",
    "https://user:pass@www.instagram.com/p/C1a2B3c4D5e/",
    "https://evil.com/?u=https://www.instagram.com/p/C1a2B3c4D5e/",
    "https://evil.com/www.instagram.com/p/C1a2B3c4D5e/",
    "https://www.instagrarn.com/p/C1a2B3c4D5e/",
    "https://xn--nstagram-f2a.com/p/C1a2B3c4D5e/",
    "https://www.instagram.com:8443/p/C1a2B3c4D5e/",
    "ftp://www.instagram.com/p/C1a2B3c4D5e/",
    "file:///etc/passwd",
    "javascript:alert(1)//www.instagram.com/p/x",
    "https://www.instagram.com/",
    "https://www.instagram.com/someuser/",
    "https://www.instagram.com/stories/someuser/123456789/",
    "https://www.instagram.com/explore/",
    "https://www.instagram.com/p/",
    "https://www.instagram.com/p/../../etc/passwd",
    "https://www.instagram.com/p/abc def/",
    "https://www.instagram.com/p/C1a2B3c4D5e/\nhttps://evil.com/",
    "https://www.instagram.com/p/C1a2B3c4D5e/ --exec 'rm -rf ~'",
    "--exec=touch /tmp/pwned",
    "-o /tmp/x https://www.instagram.com/p/C1a2B3c4D5e/",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.instagram.com/p/C1a2B3c4D5e/;rm -rf ~",
    "https://www.instagram.com/p/$(touch${IFS}pwned)/",
    "https://www.instagram.com/p/`id`/",
]


class TestValidateInstagramUrl(unittest.TestCase):
    def test_valid_urls_normalized_to_https_instagram(self):
        for url in VALID:
            with self.subTest(url=url):
                out = E.validate_instagram_url(url)
                parts = urlsplit(out)
                self.assertEqual(parts.scheme, "https")
                self.assertIn(parts.hostname, ("instagram.com", "www.instagram.com", "m.instagram.com"))
                self.assertIsNone(parts.port)
                self.assertNotIn("@", parts.netloc)
                self.assertNotIn(" ", out)
                self.assertNotIn("\n", out)
                self.assertFalse(out.startswith("-"))
                self.assertTrue(E.is_instagram_url(url))

    def test_invalid_urls_rejected(self):
        for url in INVALID:
            with self.subTest(url=url):
                with self.assertRaises(E.InvalidInputError) as cm:
                    E.validate_instagram_url(url)
                self.assertTrue(str(cm.exception).strip(), "mensagem de erro vazia")
                self.assertFalse(E.is_instagram_url(url))

    def test_schemeless_either_rejected_or_normalized(self):
        for url in ("instagram.com/p/C1a2B3c4D5e", "www.instagram.com/reel/C1a2B3c4D5e/"):
            with self.subTest(url=url):
                try:
                    out = E.validate_instagram_url(url)
                except E.InvalidInputError:
                    continue
                self.assertTrue(out.startswith("https://"), out)

    def test_is_instagram_url_never_raises(self):
        for v in [None, 123, b"https://www.instagram.com/p/x/", "x" * 10000]:
            with self.subTest(v=repr(v)[:40]):
                try:
                    self.assertFalse(E.is_instagram_url(v))
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"is_instagram_url levantou {exc!r}")

    def test_invalid_input_error_is_engine_error(self):
        self.assertTrue(issubclass(E.InvalidInputError, E.EngineError))


if __name__ == "__main__":
    unittest.main()
