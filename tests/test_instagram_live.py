"""Teste com yt-dlp REAL e rede REAL (opt-in; pulado por padrão).

Ativar:
    VIDEO_EXTRACTOR_LIVE=1 python3 -m unittest -v tests.test_instagram_live
    # opcional: VIDEO_EXTRACTOR_YTDLP=/caminho/do/yt-dlp
    # opcional: VIDEO_EXTRACTOR_LIVE_URLS="https://www.instagram.com/p/XXX/ ..."

URLs padrão: posts públicos usados pela PRÓPRIA suíte de testes do yt-dlp
(yt_dlp/extractor/instagram.py, _TESTS). O Instagram muda com frequência e pode bloquear
acesso anônimo (rate-limit/login); nesse caso o teste registra o erro classificado em vez de
fingir sucesso. Nenhum login/cookie é usado.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests import helpers as H

if os.environ.get("VIDEO_EXTRACTOR_LIVE") != "1":
    raise unittest.SkipTest("rede real desativada (defina VIDEO_EXTRACTOR_LIVE=1)")

import extractor as E  # noqa: E402

DEFAULT_URLS = [
    "https://www.instagram.com/tv/aye83DjauH/",   # yt-dlp _TESTS
    "https://www.instagram.com/p/BQ0eAlwhDrw/",   # yt-dlp _TESTS (carrossel)
]


class TestInstagramLive(unittest.TestCase):
    def test_real_download_and_extraction(self):
        st = E.check_downloader()
        if not st.ok:
            self.skipTest(f"yt-dlp indisponível: {st.message}")
        print(f"\n[live] yt-dlp {st.version} via {st.command}")
        urls = os.environ.get("VIDEO_EXTRACTOR_LIVE_URLS", "").split() or DEFAULT_URLS
        ok_any = False
        for url in urls:
            with self.subTest(url=url), tempfile.TemporaryDirectory(prefix="qa live ") as tmp:
                out = Path(tmp) / "destino"
                events = []
                results = E.run_instagram(url, out, on_event=events.append)
                failed = [e for e in events if e.kind == "download_failed"]
                if failed:
                    print(f"[live] {url}: download_failed -> {failed[0].error}")
                    continue
                for r in results:
                    desc = []
                    if r.mp3_path:
                        self.assertEqual(len(H.streams(r.mp3_path, "audio")), 1)
                        desc.append(f"MP3 {H.duration(r.mp3_path):.2f}s")
                    if r.mp4_path:
                        self.assertEqual(H.streams(r.mp4_path, "audio"), [])
                        self.assertEqual(len(H.streams(r.mp4_path, "video")), 1)
                        desc.append(f"MP4 {H.duration(r.mp4_path):.2f}s sem áudio")
                    self.assertEqual(len(r.frame_paths), 4)
                    for fp in r.frame_paths:
                        self.assertTrue(H.decodes_cleanly(fp))
                    desc.append("frames " + ", ".join(f"{t:.2f}s" for t in r.frame_times)
                                + f" {H.jpeg_info(r.frame_paths[0])[1]}x{H.jpeg_info(r.frame_paths[0])[2]}")
                    print(f"[live] {url}: pasta={Path(r.folder).name} {Path(r.source).name} status={r.status} "
                          f"{', '.join(desc)} warnings={r.warnings}")
                    self.assertIn(r.status, ("success", "no_audio"))
                    ok_any = True
        if not ok_any:
            self.skipTest("nenhum link público pôde ser baixado agora (ver saída [live])")


if __name__ == "__main__":
    unittest.main()
