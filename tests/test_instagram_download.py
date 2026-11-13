"""Fluxo link do Instagram: downloader CONTROLADO (tests/fake_ytdlp.py) + extração FFmpeg REAL.

A fronteira de rede é simulada pelo yt-dlp falso (VIDEO_EXTRACTOR_YTDLP / kwarg ytdlp=), que
produz vídeos reais com ffmpeg e emite as mensagens reais de erro do yt-dlp. Tudo depois do
download (MP3, MP4 sem áudio, nomes, colisões, limpeza) é o engine real com ffmpeg/ffprobe real.
O teste com o yt-dlp/Instagram REAL fica em tests/test_instagram_live.py (opt-in).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tests import helpers as H

if not H.HAVE_FFMPEG:
    raise unittest.SkipTest("ffmpeg/ffprobe ausentes")

import extractor as E  # noqa: E402
from tests.test_engine_real import EngineTestBase  # noqa: E402

FAKE = Path(__file__).resolve().parent / "fake_ytdlp.py"
URL = "https://www.instagram.com/reel/AbC_d-123/"
CODE = "AbC_d-123"


class FakeDownloaderBase(EngineTestBase):
    def setUp(self):
        super().setUp()
        self.log = self.root / "ytdlp_argv.jsonl"
        self.marker = self.root / "ytdlp_exit_marker"
        self.systmp = self.root / "systmp"
        self.systmp.mkdir()
        self._old_tempdir = tempfile.tempdir
        tempfile.tempdir = str(self.systmp)       # onde o engine cria video-extractor-ig-*
        self.env = H.EnvPatch(VIDEO_EXTRACTOR_YTDLP=str(FAKE), FAKE_YTDLP_MODE="ok",
                              FAKE_YTDLP_LOG=str(self.log), FAKE_YTDLP_MARKER=str(self.marker))
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__()
        tempfile.tempdir = self._old_tempdir
        super().tearDown()

    def mode(self, m):
        os.environ["FAKE_YTDLP_MODE"] = m

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines() if l.strip()]

    def download_calls(self):
        return [c for c in self.calls() if c["argv"] != ["--version"]]

    def assertTempClean(self):
        left = [p.name for p in self.systmp.iterdir()]
        self.assertEqual(left, [], f"temporários não removidos: {left}")

    def assertNoFakeAlive(self):
        import subprocess
        time.sleep(0.3)
        out = subprocess.run(["pgrep", "-f", str(FAKE)], stdout=subprocess.PIPE, text=True).stdout
        self.assertEqual(out.strip(), "", "processo yt-dlp ainda vivo")


class TestDownloaderDependency(FakeDownloaderBase):
    def test_fake_detected(self):
        st = E.check_downloader()
        self.assertTrue(st.ok, st.message)
        self.assertEqual(st.version, "2099.01.01-fake")

    def test_missing_ytdlp_never_raises_and_local_still_works(self):
        os.environ["VIDEO_EXTRACTOR_YTDLP"] = str(self.root / "nao" / "existe" / "yt-dlp")
        st = E.check_downloader()
        self.assertFalse(st.ok)
        self.assertIn("yt-dlp", st.message)
        self.assertTrue(st.message.strip())
        # ffmpeg/local não são afetados
        self.assertTrue(E.check_dependencies().ok)
        vid = H.make_video(self.src / "local.mp4")
        r = E.run_batch([vid], self.out)
        self.assertEqual(r[0].status, "success", r[0].error)
        # link recusa ANTES de criar thread / temporário
        job = E.InstagramProcessor(URL, self.out)
        with self.assertRaises(E.DependencyMissingError):
            job.start()
        self.assertFalse(job.is_running)
        with self.assertRaises(E.DependencyMissingError):
            E.run_instagram(URL, self.out)
        self.assertTempClean()

    def test_missing_ytdlp_on_empty_path(self):
        os.environ.pop("VIDEO_EXTRACTOR_YTDLP", None)
        with H.EnvPatch(PATH=str(H.fake_bin_dir(self.root))):
            st = E.check_downloader()
        # pode existir módulo yt_dlp no Python em uso; só exige não levantar e ser coerente
        self.assertIsInstance(st.ok, bool)
        if not st.ok:
            self.assertIn("pip", st.message)

    def test_broken_ytdlp_reports_not_ok(self):
        bad = self.root / "yt-dlp-quebrado"
        bad.write_text("#!/bin/sh\necho boom >&2\nexit 3\n")
        bad.chmod(0o755)
        st = E.check_downloader(ytdlp=str(bad))
        self.assertFalse(st.ok)


class TestDownloadFlow(FakeDownloaderBase):
    def test_success_real_extraction(self):
        events = []
        results = E.run_instagram(URL, self.out, on_event=events.append)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.status, "success", r.error)
        self.assertEqual(Path(r.folder), self.out / "001")
        self.assertV3Folder(r, r.source)
        self.assertTempClean()
        kinds = [e.kind for e in events]
        self.assertEqual(kinds[0], "download_started")
        self.assertIn("download_progress", kinds)
        self.assertLess(kinds.index("download_finished"), kinds.index("file_started"))
        self.assertEqual(kinds[-1], "batch_finished")
        for e in events:
            self.assertTrue(e.message, f"evento sem mensagem: {e.kind}")
            if e.kind == "download_progress":
                self.assertTrue(e.percent == -1 or 0 <= e.percent <= 100, e.percent)
        # nada guardado além de MP3/MP4 (vídeo baixado não é mantido por padrão)
        self.assertEqual(os.listdir(self.out), ["001"])
        self.assertIn("frames", {e.stage for e in events if e.kind == "progress"})

    def test_argv_is_safe_list_with_double_dash_and_normalized_url(self):
        raw = "  http://instagram.com/reel/AbC_d-123?igsh=xyz#x  "
        E.run_instagram(raw, self.out)
        calls = self.download_calls()
        self.assertEqual(len(calls), 1)
        argv = calls[0]["argv"]
        i = argv.index("--")
        self.assertEqual(argv[i + 1:], [URL], "URL deve ser o único arg após '--' e normalizada")
        for flag in ("--ignore-config", "--no-cookies", "-P"):
            self.assertIn(flag, argv)
        self.assertNotIn("--cookies-from-browser", [a for a in argv if a != "--no-cookies-from-browser"])
        for a in argv:
            self.assertNotIn("--exec", a)
        tmp = Path(argv[argv.index("-P") + 1])
        self.assertTrue(tmp.name.startswith("video-extractor-ig-"))
        self.assertEqual(tmp.parent, self.systmp)

    def test_shell_metacharacters_never_reach_a_shell(self):
        """URLs com metacaracteres são recusadas antes de chamar o yt-dlp; nenhum efeito colateral."""
        pwn = self.root / "pwned"
        for evil in (f"https://www.instagram.com/p/x;touch {pwn}/",
                     f"https://www.instagram.com/p/$(touch {pwn})/",
                     f"https://www.instagram.com/p/`touch {pwn}`/",
                     f"--exec=touch {pwn}"):
            with self.subTest(evil=evil):
                with self.assertRaises(E.InvalidInputError):
                    E.run_instagram(evil, self.out)
        self.assertFalse(pwn.exists())
        self.assertEqual(self.download_calls(), [])

    def test_extraction_only_after_download_process_exits(self):
        self.mode("linger")   # publica VXFILE e só sai 1,5 s depois
        first_file_started = []

        def on_event(ev):
            if ev.kind == "file_started" and not first_file_started:
                first_file_started.append(time.time())

        r = E.run_instagram(URL, self.out, on_event=on_event)
        self.assertEqual(r[0].status, "success", r[0].error)
        exited_at = float(self.marker.read_text())
        self.assertGreaterEqual(first_file_started[0], exited_at,
                                "extração começou antes do yt-dlp terminar")

    def test_collision_no_overwrite(self):
        self.out.mkdir()
        (self.out / "001").mkdir()
        (self.out / "001" / "audio.mp3").write_bytes(b"antigo")
        r1 = E.run_instagram(URL, self.out)[0]
        r2 = E.run_instagram(URL, self.out)[0]
        self.assertEqual([Path(r1.folder).name, Path(r2.folder).name], ["002", "003"])
        self.assertEqual((self.out / "001" / "audio.mp3").read_bytes(), b"antigo")
        self.assertEqual(os.listdir(self.out / "001"), ["audio.mp3"])
        for r in (r1, r2):
            self.assertV3Folder(r, r.source)
        self.assertTempClean()

    def test_output_dirs_with_spaces_and_accents(self):
        out = self.root / "Saída do Insta ção 日本"
        r = E.run_instagram(URL, out)[0]
        self.assertEqual(r.status, "success", r.error)
        self.assertEqual(Path(r.folder), out / "001")
        self.assertV3Folder(r, r.source)

    def test_keep_video_dir(self):
        keep = self.root / "vídeos baixados"
        r = E.run_instagram(URL, self.out, keep_video_dir=keep)[0]
        self.assertEqual(r.status, "success", r.error)
        kept = list(keep.iterdir())
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(H.streams(kept[0], "audio")), 1, "vídeo guardado deve manter o áudio")
        self.assertEqual(Path(r.source).resolve(), kept[0].resolve())
        self.assertTempClean()

    def test_downloaded_video_without_audio(self):
        self.mode("no_audio")
        r = E.run_instagram(URL, self.out)[0]
        self.assertEqual(r.status, "no_audio")
        self.assertV3Folder(r, r.source, audio=False)

    def test_carousel_two_videos(self):
        self.mode("carousel")
        events = []
        results = E.run_instagram(URL, self.out, on_event=events.append)
        self.assertEqual([r.status for r in results], ["success", "success"])
        self.assertEqual([Path(r.folder).name for r in results], ["001", "002"])
        self.assertEqual(sorted(os.listdir(self.out)), ["001", "002"])
        for r in results:
            self.assertV3Folder(r, r.source)
        warn_text = " ".join(e.message for e in events if e.kind == "download_finished")
        self.assertTrue(warn_text)
        self.assertTempClean()

    def test_carousel_continues_existing_numbering_and_local_queue(self):
        local = H.make_video(self.src / "local ação.mp4")
        E.run_batch([local], self.out, seed=1)
        self.mode("carousel")
        rs = E.run_instagram(URL, self.out, seed=2)
        self.assertEqual([Path(r.folder).name for r in rs], ["002", "003"])
        self.assertEqual(sorted(os.listdir(self.out)), ["001", "002", "003"])

    def test_download_instagram_sync_publishes_unique(self):
        dest = self.root / "destino downloads"
        r1 = E.download_instagram(URL, dest)
        r2 = E.download_instagram(URL, dest)
        self.assertEqual([p.name for p in map(Path, r1.files)], [f"instagram_{CODE}.mp4"])
        self.assertEqual([p.name for p in map(Path, r2.files)], [f"instagram_{CODE} (1).mp4"])
        self.assertEqual(len(H.streams(r1.files[0], "audio")), 1)
        self.assertTempClean()


class TestDownloadFailures(FakeDownloaderBase):
    CASES = {
        "private": "login",
        # mensagem real e ambígua do yt-dlp ("rate-limit reached or login required")
        "login": ("login", "rate_limit"), "network": "network", "not_found": "not_found",
        "rate_limit": "rate_limit", "unsupported": "unsupported", "unknown": "unknown",
        "images_only": "no_video",
    }

    def test_error_kinds_and_clean_state(self):
        for mode, kind in self.CASES.items():
            with self.subTest(mode=mode):
                self.mode(mode)
                with self.assertRaises(E.DownloadError) as cm:
                    E.download_instagram(URL, self.root / "dl")
                if isinstance(kind, tuple):
                    self.assertIn(cm.exception.kind, kind)
                else:
                    self.assertEqual(cm.exception.kind, kind)
                self.assertTrue(str(cm.exception).strip())
                self.assertTempClean()

    def test_processor_failure_events_and_no_outputs(self):
        for mode in ("private", "network", "images_only"):
            with self.subTest(mode=mode):
                self.mode(mode)
                events = []
                job = E.InstagramProcessor(URL, self.out, events.append)
                job.start()
                self.assertTrue(job.wait(timeout=60))
                kinds = [e.kind for e in events]
                self.assertIn("download_failed", kinds)
                self.assertEqual(kinds[-1], "batch_finished")
                self.assertNotIn("file_started", kinds)
                self.assertEqual(job.results, [])
                self.assertTrue(job.error)
                failed = [e for e in events if e.kind == "download_failed"][0]
                self.assertTrue(failed.error and failed.message)
                if self.out.exists():
                    self.assertEqual(os.listdir(self.out), [], "erro de download não pode consumir número")
                self.assertTempClean()

    def test_nonzero_exit_with_finished_file_processes_nothing(self):
        self.mode("partial_then_fail")
        events = []
        self.assertEqual(E.run_instagram(URL, self.out, on_event=events.append), [])
        self.assertIn("download_failed", [e.kind for e in events])
        self.assertNotIn("file_started", [e.kind for e in events])
        with self.assertRaises(E.DownloadError):
            E.download_instagram(URL, self.root / "dl")
        if self.out.exists():
            self.assertEqual(os.listdir(self.out), [])
        self.assertTempClean()

    def test_exit_zero_without_files_is_no_video(self):
        self.mode("ok_without_vxfile")
        with self.assertRaises(E.DownloadError) as cm:
            E.download_instagram(URL, self.root / "dl")
        self.assertEqual(cm.exception.kind, "no_video")
        self.assertTempClean()

    def test_vxfile_outside_temp_is_ignored(self):
        self.mode("escape_path")
        events = []
        self.assertEqual(E.run_instagram(URL, self.out, on_event=events.append), [])
        self.assertIn("download_failed", [e.kind for e in events])
        if self.out.exists():
            self.assertEqual(os.listdir(self.out), [])
        # o arquivo "de fora" não foi movido nem apagado pelo engine
        outside = list(self.systmp.glob("fora_do_temp_*"))
        self.assertEqual(len(outside), 1)
        outside[0].unlink()
        self.assertTempClean()

    def test_validation_before_any_process(self):
        f = self.root / "arquivo"
        f.write_text("x")
        cases = [
            (dict(url="https://evil.com/p/x/", out=self.out), E.InvalidInputError),
            (dict(url=URL, out=None), (E.InvalidInputError, TypeError)),
            (dict(url=URL, out=f), E.InvalidInputError),
        ]
        for kw, exc in cases:
            with self.subTest(kw=kw):
                job = E.InstagramProcessor(kw["url"], kw["out"])
                with self.assertRaises(exc):
                    job.start()
                self.assertFalse(job.is_running)
        self.assertEqual(self.download_calls(), [])
        self.assertTempClean()

    def test_missing_ffmpeg_blocks_link(self):
        with H.EnvPatch(VIDEO_EXTRACTOR_FFMPEG=str(self.root / "sem_ffmpeg")):
            with self.assertRaises(E.DependencyMissingError):
                E.InstagramProcessor(URL, self.out).start()
        self.assertEqual(self.download_calls(), [])


class TestDownloadCancel(FakeDownloaderBase):
    def test_cancel_during_download(self):
        self.mode("slow")
        events = []
        got_progress = threading.Event()

        def on_event(ev):
            events.append(ev)
            if ev.kind == "download_progress":
                got_progress.set()

        job = E.InstagramProcessor(URL, self.out, on_event)
        job.start()
        self.assertTrue(got_progress.wait(30), "sem progresso de download")
        t0 = time.time()
        job.cancel()
        self.assertTrue(job.wait(timeout=10))
        self.assertLess(time.time() - t0, 2.0, "cancelamento lento")
        self.assertEqual(events[-1].kind, "batch_finished")
        self.assertNotIn("file_started", [e.kind for e in events])
        self.assertTempClean()
        self.assertNoFakeAlive()
        if self.out.exists():
            self.assertEqual(os.listdir(self.out), [])

    def test_cancel_sync_download_raises_cancelled(self):
        self.mode("slow")
        ev = threading.Event()
        threading.Timer(1.0, ev.set).start()
        with self.assertRaises(E.CancelledError):
            E.download_instagram(URL, self.root / "dl", cancel_event=ev)
        self.assertTempClean()
        self.assertNoFakeAlive()

    def test_cancel_during_extraction_after_download(self):
        os.environ["FAKE_YTDLP_DURATION"] = "30"
        try:
            events = []
            started = threading.Event()

            def on_event(e):
                events.append(e)
                if e.kind == "progress":
                    started.set()

            # VP9 não; o fake gera H.264 (cópia rápida) -> MP3 de 30 s ainda leva um pouco
            job = E.InstagramProcessor(URL, self.out, on_event)
            job.start()
            started.wait(60)
            job.cancel()
            self.assertTrue(job.wait(timeout=15))
            self.assertEqual(events[-1].kind, "batch_finished")
            self.assertTempClean()
            if self.out.exists():
                self.assertEqual(os.listdir(self.out), [], "pasta do item cancelado deve ser removida")
        finally:
            os.environ.pop("FAKE_YTDLP_DURATION", None)

    def test_cancel_during_frames_of_second_carousel_video(self):
        self.mode("carousel")
        holder = {}

        def on_event(e):
            if e.kind == "progress" and e.stage == "frames" and e.index == 1:
                holder["job"].cancel()

        job = E.InstagramProcessor(URL, self.out, on_event)
        holder["job"] = job
        job.start()
        self.assertTrue(job.wait(timeout=60))
        self.assertEqual([r.status for r in job.results], ["success", "cancelled"])
        self.assertEqual(sorted(os.listdir(self.out)), ["001"])
        self.assertV3Folder(job.results[0], job.results[0].source)
        self.assertTempClean()
        self.assertNoTempLeftovers(self.out)


if __name__ == "__main__":
    unittest.main()
