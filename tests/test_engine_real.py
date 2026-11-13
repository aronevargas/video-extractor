"""Testes REAIS do engine V3 (pasta numerada por vídeo) com ffmpeg/ffprobe.

Contrato: "CONTRATO v3 FINAL (backend)" — ver docs/qa.md. Estrutura por vídeo:
<destino>/NNN/audio.mp3, NNN/video.mp4 (sem áudio), NNN/frames/frame_01.jpg..frame_04.jpg.
Nada de mock: vídeos sintéticos reais (ffmpeg lavfi), saídas inspecionadas com ffprobe,
frames comparados pixel a pixel com o quadro de referência no instante informado.
"""
from __future__ import annotations

import os
import random
import shutil
import stat
import tempfile
import threading
import unittest
from pathlib import Path

from tests import helpers as H

if not H.HAVE_FFMPEG:
    raise unittest.SkipTest("ffmpeg/ffprobe ausentes no sistema: testes reais impossíveis")

import extractor as E  # noqa: E402

ACCENT_NAME = "Vídeo de Férias ção ñ 日本 #1.mp4"
FRAME_NAMES = [f"frame_0{i}.jpg" for i in range(1, 5)]


class EngineTestBase(unittest.TestCase):
    """Árvore temporária isolada por teste (com espaço/acento no próprio caminho)."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="qa ve ção ")
        self.root = Path(self._tmp)
        self.src = self.root / "entrada"
        self.out = self.root / "saída única"
        self.src.mkdir()

    def tearDown(self):
        for p in self.root.rglob("*"):
            try:
                p.chmod(0o755 if p.is_dir() else 0o644)
            except OSError:
                pass
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ---- asserts reutilizáveis -------------------------------------------------
    def assertValidMp3(self, path, expected_duration=H.DURATION):
        path = Path(path)
        self.assertTrue(path.is_file(), f"MP3 não existe: {path}")
        self.assertGreater(path.stat().st_size, 0)
        a = H.streams(path, "audio")
        v = [s for s in H.streams(path, "video") if s.get("disposition", {}).get("attached_pic") != 1]
        self.assertEqual(len(a), 1, f"MP3 deveria ter 1 stream de áudio: {path}")
        self.assertEqual(a[0]["codec_name"], "mp3")
        self.assertEqual(v, [], "MP3 não deveria ter stream de vídeo")
        self.assertAlmostEqual(H.duration(path), expected_duration, delta=H.DURATION_TOL)
        self.assertTrue(H.decodes_cleanly(path), f"MP3 não decodifica limpo: {path}")

    def assertValidSilentMp4(self, path, expected_duration=H.DURATION):
        path = Path(path)
        self.assertTrue(path.is_file(), f"MP4 não existe: {path}")
        self.assertEqual(H.streams(path, "audio"), [], f"MP4 ainda tem áudio: {path}")
        v = H.streams(path, "video")
        self.assertEqual(len(v), 1, "MP4 deveria ter exatamente 1 stream de vídeo")
        self.assertIn(v[0]["codec_name"], ("h264", "mpeg4"))
        self.assertIn("mp4", H.probe(path)["format"]["format_name"])
        self.assertAlmostEqual(H.duration(path), expected_duration, delta=H.DURATION_TOL)
        self.assertTrue(H.decodes_cleanly(path), f"MP4 não decodifica limpo: {path}")

    def assertValidFrames(self, r, src, duration=H.DURATION, size=(160, 120)):
        folder = Path(r.folder)
        self.assertEqual([Path(p).name for p in r.frame_paths], FRAME_NAMES)
        self.assertEqual(sorted(os.listdir(folder / "frames")), FRAME_NAMES)
        for p in r.frame_paths:
            self.assertEqual(Path(p).parent, folder / "frames")
            codec, w, h = H.jpeg_info(p)
            self.assertEqual(codec, "mjpeg", f"não é JPEG: {p}")
            self.assertEqual((w, h), size, f"dimensão errada em {p}")
            self.assertTrue(H.decodes_cleanly(p), f"JPEG não decodifica limpo: {p}")
        t = list(r.frame_times)
        self.assertEqual(len(t), 4)
        self.assertEqual(t, sorted(t), "frame_times devem ser crescentes")
        for x in t:
            self.assertGreaterEqual(x, 0.0)
            self.assertLess(x, duration, f"instante {x} fora da duração {duration}")

    def assertV3Folder(self, r, src, *, audio=True, duration=H.DURATION, size=(160, 120)):
        """Pasta NNN completa e coerente com o VideoResult."""
        self.assertIsNotNone(r.folder)
        folder = Path(r.folder)
        self.assertTrue(folder.is_dir())
        self.assertRegex(folder.name, r"^\d{3,}$")
        expected = {"video.mp4", "frames"} | ({"audio.mp3"} if audio else set())
        self.assertEqual(set(os.listdir(folder)), expected, f"conteúdo inesperado em {folder}")
        self.assertEqual(Path(r.video_path), folder / "video.mp4")
        self.assertValidSilentMp4(r.video_path, duration)
        if audio:
            self.assertEqual(Path(r.audio_path), folder / "audio.mp3")
            self.assertValidMp3(r.audio_path, duration)
        else:
            self.assertIsNone(r.audio_path)
        self.assertValidFrames(r, src, duration, size)

    def assertNoTempLeftovers(self, *folders):
        for f in folders:
            if Path(f).exists():
                left = [str(p) for p in Path(f).rglob("*") if p.name.endswith(".part")]
                self.assertEqual(left, [], f"temporários deixados: {left}")

    def folders(self, d=None):
        d = Path(d or self.out)
        return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


# ============================================================ dependências / listagem
class TestDependencies(EngineTestBase):
    def test_dependencies_present(self):
        st = E.check_dependencies()
        self.assertTrue(st.ok, st.message)

    def test_missing_ffmpeg_via_kwarg_never_raises(self):
        st = E.check_dependencies(ffmpeg=str(self.root / "nao_existe_ffmpeg"))
        self.assertFalse(st.ok)
        self.assertIn("ffmpeg", st.message.lower())

    def test_missing_ffprobe_via_env(self):
        with H.EnvPatch(VIDEO_EXTRACTOR_FFPROBE=str(self.root / "nao_existe_ffprobe")):
            st = E.check_dependencies()
        self.assertFalse(st.ok)

    def test_missing_from_path(self):
        with H.EnvPatch(PATH=str(H.fake_bin_dir(self.root)), VIDEO_EXTRACTOR_FFMPEG=None,
                        VIDEO_EXTRACTOR_FFPROBE=None):
            st = E.check_dependencies()
        self.assertFalse(st.ok)

    def test_batch_start_refuses_without_ffmpeg(self):
        vid = H.make_video(self.src / "a.mp4")
        with H.EnvPatch(VIDEO_EXTRACTOR_FFMPEG=str(self.root / "nao_existe")):
            job = E.BatchProcessor([vid], self.out, lambda ev: None)
            with self.assertRaises(E.DependencyMissingError):
                job.start()
        self.assertFalse(job.is_running)
        self.assertEqual(self.folders(), [])

    def test_api_has_no_dual_destination(self):
        import inspect
        params = inspect.signature(E.process_video).parameters
        self.assertNotIn("mp3_dir", params)
        self.assertNotIn("mp4_dir", params)
        self.assertIn("output_dir", params)


class TestListVideos(EngineTestBase):
    def test_lists_only_videos_sorted_nonrecursive(self):
        for n in ["b.mp4", "A.MKV", "c.webm", "nota.txt", ".oculto.mp4", ".x.mp4.part", ACCENT_NAME]:
            (self.src / n).write_bytes(b"x")
        (self.src / "sub").mkdir()
        (self.src / "sub" / "dentro.mp4").write_bytes(b"x")
        got = [Path(p).name for p in E.list_videos(self.src)]
        self.assertEqual(got, sorted(["b.mp4", "A.MKV", "c.webm", ACCENT_NAME], key=str.casefold))

    def test_invalid_folder(self):
        with self.assertRaises(E.InvalidInputError):
            E.list_videos(self.root / "nao existe")


# ============================================================ estrutura e conteúdo
class TestFolderContent(EngineTestBase):
    def test_h264_aac_full_folder(self):
        vid = H.make_video(self.src / "clip.mp4")
        before = H.sha256(vid)
        r = E.process_video(vid, self.out, seed=1)
        self.assertEqual(r.status, "success", r.error)
        self.assertEqual(Path(r.folder), self.out / "001")
        self.assertV3Folder(r, vid)
        self.assertEqual(H.sha256(vid), before, "original alterado")
        self.assertEqual(os.listdir(self.src), ["clip.mp4"])
        self.assertNoTempLeftovers(self.out)
        # aliases do contrato
        self.assertEqual(r.mp3_path, r.audio_path)
        self.assertEqual(r.mp4_path, r.video_path)
        self.assertEqual(list(r.frames), list(r.frame_paths))

    def test_webm_vp9_opus_odd_size(self):
        vid = H.make_video(self.src / "clip.webm", vcodec="libvpx-vp9", acodec="libopus", size="320x240")
        r = E.process_video(vid, self.out, seed=2)
        self.assertEqual(r.status, "success", r.error)
        self.assertV3Folder(r, vid, size=(320, 240))

    def test_avi_and_mkv_inputs(self):
        for name, kw in (("clip.avi", dict(vcodec="mpeg4", acodec="libmp3lame")), ("clip.mkv", {})):
            with self.subTest(name=name):
                vid = H.make_video(self.src / name, **kw)
                r = E.process_video(vid, self.out, seed=3)
                self.assertEqual(r.status, "success", r.error)
                self.assertV3Folder(r, vid)

    def test_frame_dimensions_follow_video(self):
        vid = H.make_video(self.src / "hd.mp4", size="640x360")
        r = E.process_video(vid, self.out, seed=4)
        self.assertEqual(r.status, "success", r.error)
        self.assertV3Folder(r, vid, size=(640, 360))

    def test_spaces_accents_in_source_and_destination(self):
        vid = H.make_video(self.src / ACCENT_NAME)
        out = self.root / "Destino com espaço ação 日本"
        r = E.process_video(vid, out, seed=5)
        self.assertEqual(r.status, "success", r.error)
        self.assertEqual(Path(r.folder), out / "001")
        self.assertV3Folder(r, vid)

    def test_longer_video_durations(self):
        vid = H.make_video(self.src / "longo.mp4", duration=7.0)
        r = E.process_video(vid, self.out, seed=6)
        self.assertEqual(r.status, "success", r.error)
        self.assertV3Folder(r, vid, duration=7.0)

    def test_video_without_audio(self):
        vid = H.make_video(self.src / "mudo.mp4", audio=False)
        r = E.process_video(vid, self.out, seed=7)
        self.assertEqual(r.status, "no_audio", r.error)
        self.assertTrue(r.warnings, "deveria avisar a falta de áudio")
        self.assertV3Folder(r, vid, audio=False)
        self.assertFalse((Path(r.folder) / "audio.mp3").exists(), "não pode haver MP3 vazio")

    def test_very_short_video_still_four_valid_jpgs(self):
        vid = H.make_video(self.src / "curto.mp4", duration=0.3)
        r = E.process_video(vid, self.out, seed=8)
        self.assertIn(r.status, ("success",), r.error)
        self.assertEqual(len(r.frame_paths), 4)
        for p in r.frame_paths:
            self.assertEqual(H.jpeg_info(p)[0], "mjpeg")
        for t in r.frame_times:
            self.assertGreaterEqual(t, 0)
            self.assertLess(t, 0.3 + 1e-6)

    def test_single_frame_video(self):
        vid = H.make_video(self.src / "um quadro.mp4", duration=0.04)
        r = E.process_video(vid, self.out, seed=9)
        self.assertIn(r.status, ("success", "partial"), r.error)
        self.assertEqual(len(r.frame_paths), 4)
        for p in r.frame_paths:
            self.assertEqual(H.jpeg_info(p)[0], "mjpeg")

    def test_invalid_file_fails_without_folder(self):
        bad = H.make_invalid(self.src / "quebrado.mp4")
        before = H.sha256(bad)
        r = E.process_video(bad, self.out, seed=1)
        self.assertEqual(r.status, "failed")
        self.assertTrue(r.error and r.error.strip())
        self.assertIsNone(r.folder)
        self.assertEqual(self.folders(), [], "arquivo inválido não pode consumir número")
        self.assertEqual(H.sha256(bad), before)

    def test_truncated_file_no_garbage(self):
        good = H.make_video(self.root / "bom.mp4")
        bad = H.make_truncated(good, self.src / "truncado.mp4")
        r = E.process_video(bad, self.out, seed=1)
        self.assertIn(r.status, ("failed", "partial", "no_audio", "success"))
        self.assertNoTempLeftovers(self.out)
        if r.status == "failed":
            self.assertEqual(self.folders(), [])
        elif r.folder:
            for f in Path(r.folder).rglob("*"):
                if f.is_file():
                    self.assertGreater(f.stat().st_size, 0, f"arquivo vazio: {f}")

    @unittest.skipIf(os.geteuid() == 0, "root ignora permissões")
    def test_unreadable_input(self):
        vid = H.make_video(self.src / "secreto.mp4")
        vid.chmod(0)
        r = E.process_video(vid, self.out)
        self.assertEqual(r.status, "failed")
        self.assertEqual(self.folders(), [])

    def test_audio_only_is_partial_with_only_audio(self):
        vid = H.make_video(self.src / "so_audio.mkv", video=False)
        r = E.process_video(vid, self.out, seed=1)
        self.assertEqual(r.status, "partial")
        self.assertTrue(r.error)
        self.assertEqual(os.listdir(r.folder), ["audio.mp3"])
        self.assertValidMp3(r.audio_path)
        self.assertIsNone(r.video_path)
        self.assertEqual(list(r.frame_paths), [])
        self.assertNoTempLeftovers(self.out)


# ============================================================ frames: instantes e aleatoriedade
class TestFrameTimes(EngineTestBase):
    DUR = 8.0

    def setUp(self):
        super().setUp()
        self.vid = H.make_video(self.src / "oito.mp4", duration=self.DUR)

    def test_times_spread_one_per_quarter(self):
        r = E.process_video(self.vid, self.out, seed=123)
        self.assertEqual(r.status, "success", r.error)
        t = r.frame_times
        safe_end = self.DUR - 0.1
        for i, x in enumerate(t):
            lo, hi = i * safe_end / 4, (i + 1) * safe_end / 4
            self.assertTrue(lo - 0.05 <= x <= hi + 0.05, f"frame {i + 1} em {x:.3f}s fora da faixa [{lo:.2f},{hi:.2f}]")
        self.assertEqual(len(set(round(x, 3) for x in t)), 4, "instantes repetidos")

    def test_same_seed_is_deterministic_and_seed_changes_times(self):
        a = E.process_video(self.vid, self.out, seed=42).frame_times
        b = E.process_video(self.vid, self.out, seed=42).frame_times
        c = E.process_video(self.vid, self.out, seed=43).frame_times
        self.assertEqual(a, b, "mesma seed deve dar os mesmos instantes")
        self.assertNotEqual(a, c, "seed diferente deveria mudar os instantes")
        d = E.process_video(self.vid, self.out, rng=random.Random(42)).frame_times
        self.assertEqual(a, d, "rng=random.Random(seed) deve equivaler a seed=")

    def test_default_rng_is_random_between_runs(self):
        # sem seed usa SystemRandom; probabilidade de coincidir em floats contínuos ~0
        a = E.process_video(self.vid, self.out).frame_times
        b = E.process_video(self.vid, self.out).frame_times
        self.assertNotEqual(a, b)

    def test_frame_pixels_match_reported_timestamps(self):
        """Cada JPG corresponde ao quadro de referência no instante informado (testsrc muda com o tempo)."""
        r = E.process_video(self.vid, self.out, seed=7)
        refs = []
        for i, t in enumerate(r.frame_times):
            refs.append(H.reference_frame_png(self.vid, t, self.root / f"ref{i}.png"))
        for i, fp in enumerate(r.frame_paths):
            own = H.image_distance(fp, refs[i])
            for j, ref in enumerate(refs):
                if j != i and abs(r.frame_times[j] - r.frame_times[i]) > 0.5:
                    other = H.image_distance(fp, ref)
                    self.assertLess(own, other, f"frame_0{i + 1} ({r.frame_times[i]:.2f}s) parece mais com "
                                                f"o instante {r.frame_times[j]:.2f}s")
            self.assertLess(own, 12.0, f"frame_0{i + 1} difere demais da referência ({own:.1f})")

    def test_frames_differ_from_each_other(self):
        r = E.process_video(self.vid, self.out, seed=11)
        fp = r.frame_paths
        for i in range(4):
            for j in range(i + 1, 4):
                self.assertGreater(H.image_distance(fp[i], fp[j]), 0.5, f"frames {i + 1} e {j + 1} iguais")


# ============================================================ numeração e não sobrescrita
class TestNumbering(EngineTestBase):
    def test_queue_numbers_sequential(self):
        vids = [H.make_video(self.src / f"v{i}.mp4") for i in range(3)]
        rs = E.run_batch(vids, self.out, seed=1)
        self.assertEqual([Path(r.folder).name for r in rs], ["001", "002", "003"])
        for r, v in zip(rs, vids):
            self.assertEqual(Path(r.source).name, v.name)
            self.assertV3Folder(r, v)

    def test_new_execution_continues_and_keeps_previous(self):
        v = H.make_video(self.src / "v.mp4")
        E.run_batch([v, v], self.out, seed=1)
        snap = {p.relative_to(self.out): H.sha256(p) for p in self.out.rglob("*") if p.is_file()}
        rs = E.run_batch([v], self.out, seed=2)
        self.assertEqual(Path(rs[0].folder).name, "003")
        now = {p.relative_to(self.out): H.sha256(p) for p in self.out.rglob("*") if p.is_file()}
        for k, h in snap.items():
            self.assertEqual(now[k], h, f"{k} foi alterado por nova execução")

    def test_existing_entries_gaps_files_and_non_numeric(self):
        self.out.mkdir()
        (self.out / "001").mkdir()
        (self.out / "005").mkdir()
        (self.out / "007").write_text("sou arquivo")   # arquivo numérico conta
        (self.out / "abc").mkdir()
        (self.out / "01a").mkdir()
        (self.out / "notas.txt").write_text("x")
        v = H.make_video(self.src / "v.mp4")
        self.assertEqual(Path(E.next_output_folder(self.out)).name, "008")
        r = E.process_video(v, self.out, seed=1)
        self.assertEqual(Path(r.folder).name, "008")
        self.assertEqual((self.out / "007").read_text(), "sou arquivo")
        self.assertEqual(os.listdir(self.out / "001"), [])
        self.assertEqual(os.listdir(self.out / "005"), [])

    def test_next_output_folder_does_not_reserve(self):
        self.out.mkdir()
        self.assertEqual(Path(E.next_output_folder(self.out)).name, "001")
        self.assertEqual(Path(E.next_output_folder(self.out)).name, "001")
        self.assertEqual(os.listdir(self.out), [])

    def test_beyond_999(self):
        self.out.mkdir()
        (self.out / "999").mkdir()
        r = E.process_video(H.make_video(self.src / "v.mp4"), self.out, seed=1)
        self.assertEqual(Path(r.folder).name, "1000")
        self.assertV3Folder(r, self.src / "v.mp4")

    def test_invalid_does_not_consume_number(self):
        q = [H.make_video(self.src / "1 ok.mp4"), H.make_invalid(self.src / "2 ruim.mp4"),
             H.make_video(self.src / "3 ok.mp4")]
        rs = E.run_batch(q, self.out, seed=1)
        self.assertEqual([r.status for r in rs], ["success", "failed", "success"])
        self.assertEqual([r.folder and Path(r.folder).name for r in rs], ["001", None, "002"])
        self.assertEqual(self.folders(), ["001", "002"])

    def test_concurrent_batches_never_share_a_folder(self):
        vids = [H.make_video(self.src / f"c{i}.mp4") for i in range(3)]
        out = {}

        def work(k):
            out[k] = E.run_batch(vids, self.out, seed=k)

        ts = [threading.Thread(target=work, args=(k,)) for k in (1, 2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(180)
        names = [Path(r.folder).name for k in (1, 2) for r in out[k]]
        self.assertEqual(sorted(names), ["001", "002", "003", "004", "005", "006"])
        for k in (1, 2):
            for r in out[k]:
                self.assertEqual(r.status, "success", r.error)
                self.assertV3Folder(r, r.source)

    def test_destination_equals_source(self):
        vids = [H.make_video(self.src / "a.mp4"), H.make_video(self.src / "b mudo.mp4", audio=False)]
        before = H.snapshot(self.src)
        rs = E.run_batch(vids, self.src, seed=1)
        self.assertEqual([r.status for r in rs], ["success", "no_audio"])
        self.assertEqual([Path(r.folder).parent for r in rs], [self.src, self.src])
        after = {k: v for k, v in H.snapshot(self.src).items()}
        self.assertEqual(after, before, "originais alterados")
        # nova execução sobre a mesma pasta: só os originais entram na fila
        self.assertEqual([Path(p).name for p in E.list_videos(self.src)], ["a.mp4", "b mudo.mp4"])
        self.assertEqual([Path(p).name for p in E.list_videos(self.src, recursive=True)],
                         ["a.mp4", "b mudo.mp4"])
        rs2 = E.run_batch(E.list_videos(self.src), self.src, seed=2)
        self.assertEqual([Path(r.folder).name for r in rs2], ["003", "004"])

    def test_destination_is_a_file_or_not_writable(self):
        v = H.make_video(self.src / "v.mp4")
        f = self.root / "arquivo"
        f.write_text("x")
        with self.assertRaises(E.InvalidInputError):
            E.process_video(v, f)
        with self.assertRaises(E.InvalidInputError):
            E.BatchProcessor([v], f, lambda e: None).start()
        if os.geteuid() != 0:
            ro = self.root / "somente leitura"
            ro.mkdir()
            ro.chmod(stat.S_IRUSR | stat.S_IXUSR)
            with self.assertRaises(E.InvalidInputError):
                E.process_video(v, ro)

    def test_creates_missing_nested_destination(self):
        out = self.root / "novo" / "nível 2"
        r = E.process_video(H.make_video(self.src / "v.mp4"), out, seed=1)
        self.assertEqual(Path(r.folder), out / "001")


# ============================================================ fila, falhas, cancelamento
class _FfmpegFailing:
    """ffmpeg REAL embrulhado: falha só quando o comando grava um .jpg (frames)."""

    def __init__(self, root: Path, pattern: str = ".jpg"):
        self.path = root / "ffmpeg_falha_frames"
        self.path.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            f"if any(a.endswith({pattern!r}) or {pattern!r} in a for a in sys.argv[1:]):\n"
            "    sys.stderr.write('falha injetada pelo teste\\n'); sys.exit(1)\n"
            f"os.execv({H.FFMPEG!r}, [{H.FFMPEG!r}] + sys.argv[1:])\n")
        self.path.chmod(0o755)


class TestQueueAndFailures(EngineTestBase):
    def test_mixed_queue_continues(self):
        q = [H.make_video(self.src / "01 ok.mp4"), H.make_invalid(self.src / "02 inválido.mp4"),
             H.make_video(self.src / "03 mudo.mp4", audio=False),
             H.make_video(self.src / "04 vp9 ção.webm", vcodec="libvpx-vp9", acodec="libopus"),
             H.make_video(self.src / "05 último.mov")]
        before = H.snapshot(self.src)
        events = []
        rs = E.run_batch(q, self.out, on_event=events.append, seed=1)
        self.assertEqual([r.status for r in rs], ["success", "failed", "no_audio", "success", "success"])
        self.assertEqual([r.folder and Path(r.folder).name for r in rs], ["001", None, "002", "003", "004"])
        for r, src in zip(rs, q):
            if r.folder:
                self.assertV3Folder(r, src, audio=(r.status == "success"))
        self.assertEqual(H.snapshot(self.src), before)
        self.assertNoTempLeftovers(self.out)
        kinds = [e.kind for e in events]
        self.assertEqual(kinds.count("file_started"), 5)
        self.assertEqual(kinds.count("file_finished"), 5)
        self.assertEqual(kinds[-1], "batch_finished")
        stages = {e.stage for e in events if e.kind == "progress"}
        self.assertIn("frames", stages)
        for e in events:
            self.assertTrue(e.message)
            if e.kind in ("progress", "file_finished") and e.index in (0, 2, 3, 4):
                self.assertIsNotNone(e.folder, f"evento {e.kind} sem folder")
            if e.kind == "progress":
                self.assertTrue(0 <= e.percent <= 100)

    def test_frames_failure_is_partial_keeps_audio_and_video(self):
        fake = _FfmpegFailing(self.root)
        v = H.make_video(self.src / "v.mp4")
        r = E.process_video(v, self.out, ffmpeg=str(fake.path), seed=1)
        self.assertEqual(r.status, "partial")
        self.assertTrue(r.error)
        self.assertValidMp3(r.audio_path)
        self.assertValidSilentMp4(r.video_path)
        self.assertEqual(list(r.frame_paths), [])
        self.assertFalse((Path(r.folder) / "frames").exists() and
                         any((Path(r.folder) / "frames").iterdir()), "frames/ com lixo")
        self.assertNoTempLeftovers(self.out)

    def test_frames_failure_in_queue_does_not_stop_next(self):
        fake = _FfmpegFailing(self.root)
        vids = [H.make_video(self.src / f"v{i}.mp4") for i in range(2)]
        with H.EnvPatch(VIDEO_EXTRACTOR_FFMPEG=str(fake.path)):
            rs = E.run_batch(vids, self.out, seed=1)
        self.assertEqual([r.status for r in rs], ["partial", "partial"])
        self.assertEqual(self.folders(), ["001", "002"])

    def _cancel_at(self, stage):
        vids = [H.make_video(self.src / f"v{i}.mp4", duration=4.0) for i in range(3)]
        cancel = threading.Event()
        seen = []

        def on_event(e):
            seen.append(e)
            if e.kind == "progress" and e.stage == stage and e.index == 1:
                cancel.set()

        rs = E.run_batch(vids, self.out, on_event=on_event, cancel_event=cancel, seed=1)
        return rs, seen

    def test_cancel_during_frames_removes_current_folder(self):
        rs, seen = self._cancel_at("frames")
        self.assertEqual([r.status for r in rs], ["success", "cancelled", "cancelled"])
        self.assertEqual(self.folders(), ["001"], "pasta do item cancelado deve sumir")
        self.assertIsNone(rs[1].folder)
        self.assertV3Folder(rs[0], rs[0].source, duration=4.0)
        self.assertEqual(seen[-1].kind, "batch_finished")
        self.assertNoTempLeftovers(self.out)

    def test_cancel_during_audio(self):
        rs, _ = self._cancel_at("audio")
        self.assertEqual([r.status for r in rs], ["success", "cancelled", "cancelled"])
        self.assertEqual(self.folders(), ["001"])
        self.assertNoTempLeftovers(self.out)

    def test_batch_processor_thread_and_cancel(self):
        vids = [H.make_video(self.src / f"longo{i}.webm", duration=20.0, vcodec="libvpx-vp9",
                             acodec="libopus", size="640x480") for i in range(2)]
        events = []
        started = threading.Event()

        def on_event(e):
            events.append(e)
            if e.kind == "progress":
                started.set()

        job = E.BatchProcessor(vids, self.out, on_event, seed=1)
        job.start()
        self.assertTrue(started.wait(60))
        job.cancel()
        self.assertTrue(job.wait(timeout=30))
        self.assertEqual([r.status for r in job.results], ["cancelled", "cancelled"])
        self.assertEqual(self.folders(), [])
        self.assertEqual(events[-1].kind, "batch_finished")
        self.assertNoTempLeftovers(self.out)

    def test_batch_processor_validations(self):
        with self.assertRaises(E.InvalidInputError):
            E.BatchProcessor([], self.out, lambda e: None).start()


class TestEngineIsolation(unittest.TestCase):
    def test_engine_does_not_import_tkinter(self):
        import subprocess
        import sys
        code = "import sys, extractor; print('tkinter' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", code], cwd=H.REPO_ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
