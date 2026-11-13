"""Smoke/integração da UI Tkinter com o engine REAL (sem mock de extração).

Usa a tela disponível ($DISPLAY). Os seletores nativos (filedialog) e as caixas de
mensagem são substituídos por funções que devolvem caminhos/respostas, e os botões
reais da janela são acionados com .invoke(). A extração roda de verdade via ffmpeg.
"""
from __future__ import annotations

import gc
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from tests import helpers as H

if not H.HAVE_FFMPEG:
    raise unittest.SkipTest("ffmpeg/ffprobe ausentes")
if os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    raise unittest.SkipTest("sem DISPLAY: rode com xvfb-run ou numa sessão gráfica")

import tkinter as tk  # noqa: E402

import extractor.ui as ui  # noqa: E402


class _Dialogs:
    """Substitui filedialog/messagebox do módulo ui e registra chamadas."""

    def __init__(self):
        self.calls = []
        self.next_dir = []
        self.next_files = ()
        self.yesno = True

    def install(self, test):
        fd, mb = ui.filedialog, ui.messagebox
        saved = {
            (fd, "askdirectory"): fd.askdirectory, (fd, "askopenfilenames"): fd.askopenfilenames,
            (mb, "showinfo"): mb.showinfo, (mb, "showwarning"): mb.showwarning,
            (mb, "showerror"): mb.showerror, (mb, "askyesno"): mb.askyesno,
        }
        fd.askdirectory = lambda **kw: (self.calls.append(("askdirectory", kw.get("title"))),
                                        self.next_dir.pop(0) if self.next_dir else "")[1]
        fd.askopenfilenames = lambda **kw: (self.calls.append(("askopenfilenames", kw.get("title"))),
                                            self.next_files)[1]
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(mb, name, (lambda n: lambda *a, **kw: self.calls.append((n, a[1] if len(a) > 1 else kw)))(name))
        mb.askyesno = lambda *a, **kw: (self.calls.append(("askyesno", a)), self.yesno)[1]

        def restore():
            for (mod, name), fn in saved.items():
                setattr(mod, name, fn)
        test.addCleanup(restore)

    def of(self, kind):
        return [c for c in self.calls if c[0] == kind]


class UITestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="qa ui ção ")
        self.root_dir = Path(self._tmp)
        self.src = self.root_dir / "fila entrada"
        self.out = self.root_dir / "saída única ção"
        self.src.mkdir()
        self.dlg = _Dialogs()
        self.dlg.install(self)
        self.opened = []
        saved_open = ui.open_in_file_manager
        ui.open_in_file_manager = lambda p: self.opened.append(Path(p))
        self.addCleanup(setattr, ui, "open_in_file_manager", saved_open)
        self.tk = tk.Tk()
        self.app = ui.App(self.tk)
        self.pump(0.3)  # deixa check_dependencies (after 50ms) rodar

    def tearDown(self):
        try:
            if self.app.job is not None:
                self.app.job.cancel()
                self.app.job.wait(timeout=30)
            for after_id in self.tk.tk.call("after", "info"):
                self.tk.after_cancel(after_id)
            self.tk.destroy()
        except tk.TclError:
            pass
        # Artefato de teste: várias Tk() no mesmo processo. Coletar as Variables da
        # janela destruída AQUI (thread principal); senão o GC pode rodar dentro da
        # thread do engine no próximo teste -> "Tcl_AsyncDelete ... wrong thread".
        del self.app, self.tk
        gc.collect()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.tk.update()
            time.sleep(0.02)

    def run_until_idle(self, timeout=120):
        end = time.time() + timeout
        self.pump(0.2)
        while self.app.job is not None and time.time() < end:
            self.tk.update()
            time.sleep(0.02)
        self.pump(0.3)
        self.assertIsNone(self.app.job, "fila não terminou no tempo limite")

    def statuses(self):
        return [self.app.items[i]["status"] for i in self.app.tree.get_children()]

    def folder_col(self, iid):
        return str(self.app.tree.item(iid, "values")[3])

    def assertNNN(self, folder, *, audio=True):
        folder = Path(folder)
        expected = {"video.mp4", "frames"} | ({"audio.mp3"} if audio else set())
        self.assertEqual(set(os.listdir(folder)), expected, f"conteúdo de {folder}")
        self.assertEqual(H.streams(folder / "video.mp4", "audio"), [])
        self.assertEqual(len(H.streams(folder / "video.mp4", "video")), 1)
        self.assertAlmostEqual(H.duration(folder / "video.mp4"), H.DURATION, delta=H.DURATION_TOL)
        if audio:
            self.assertEqual(len(H.streams(folder / "audio.mp3", "audio")), 1)
            self.assertAlmostEqual(H.duration(folder / "audio.mp3"), H.DURATION, delta=H.DURATION_TOL)
        frames = sorted(os.listdir(folder / "frames"))
        self.assertEqual(frames, [f"frame_0{i}.jpg" for i in range(1, 5)])
        for f in frames:
            self.assertEqual(H.jpeg_info(folder / "frames" / f)[0], "mjpeg")


class TestUIIntegration(UITestBase):
    def test_window_builds_single_destination(self):
        self.assertTrue(self.app.deps_ok)
        self.assertEqual(self.app.tree.get_children(), ())
        self.assertFalse(hasattr(self.app, "mp3_picker"), "seletor MP3 separado não deve existir")
        self.assertFalse(hasattr(self.app, "mp4_picker"), "seletor MP4 separado não deve existir")
        pickers = [w for w in self._all_widgets(self.tk) if isinstance(w, ui.FolderPicker)]
        self.assertEqual(len(pickers), 1, "deve haver exatamente UM seletor de destino")

    def _all_widgets(self, w):
        out = [w]
        for c in w.winfo_children():
            out += self._all_widgets(c)
        return out

    def test_window_is_mapped_on_display(self):
        self.pump(0.5)
        self.assertTrue(self.tk.winfo_viewable())
        self.assertGreater(self.tk.winfo_width(), 300)
        self.assertEqual(self.tk.title(), ui.APP_TITLE)

    def test_full_flow_via_buttons_folder_queue(self):
        """Pasta de entrada -> fila; destino por seletor; Iniciar; pastas NNN reais."""
        vids = [
            H.make_video(self.src / "01 ação.mp4"),
            H.make_invalid(self.src / "02 quebrado.mkv"),
            H.make_video(self.src / "03 mudo.mp4", audio=False),
            H.make_video(self.src / "04 último vídeo.webm", vcodec="libvpx-vp9", acodec="libopus"),
        ]
        (self.src / "leia-me.txt").write_text("não é vídeo")
        before = H.snapshot(self.src)
        self.dlg.next_dir = [str(self.src)]
        self.app.btn_folder.invoke()
        self.assertEqual(len(self.app.tree.get_children()), 4)
        self.dlg.next_dir = [str(self.src)]
        self.app.btn_folder.invoke()
        self.assertEqual(len(self.app.tree.get_children()), 4, "recarregar não deve duplicar")
        self.dlg.next_dir = [str(self.out)]
        self.app.out_picker.button.invoke()
        self.assertEqual(self.app.out_picker.value(), self.out)
        self.assertEqual(str(self.app.btn_start["state"]), "normal")
        self.app.btn_start.invoke()
        self.assertIsNotNone(self.app.job)
        self.run_until_idle()
        self.assertEqual(self.statuses(), ["success", "failed", "no_audio", "success"])
        rows = self.app.tree.get_children()
        self.assertEqual([self.folder_col(i) for i in rows], ["001", "", "002", "003"])
        self.assertEqual(sorted(os.listdir(self.out)), ["001", "002", "003"])
        self.assertNNN(self.out / "001")
        self.assertNNN(self.out / "002", audio=False)
        self.assertNNN(self.out / "003")
        self.assertEqual(self.app.items[rows[0]]["folder"], self.out / "001")
        self.assertIsNone(self.app.items[rows[1]]["folder"])
        self.assertIn("001", str(self.app.tree.item(rows[0], "values")[2]))
        self.assertIn("áudio", str(self.app.tree.item(rows[2], "values")[2]).lower())
        self.assertTrue(str(self.app.tree.item(rows[1], "values")[2]).strip())
        self.assertEqual(H.snapshot(self.src), before, "originais alterados")
        self.assertEqual(float(self.app.progress["value"]), 100.0)
        self.assertTrue(self.dlg.of("showwarning") or self.dlg.of("showinfo"))
        # abrir pasta do item selecionado
        self.app.tree.selection_set(rows[2])
        self.pump(0.1)
        self.assertEqual(str(self.app.btn_open_item["state"]), "normal")
        self.app.btn_open_item.invoke()
        self.assertEqual(self.opened[-1], self.out / "002")
        self.app.tree.selection_set(rows[1])
        self.pump(0.1)
        self.assertEqual(str(self.app.btn_open_item["state"]), "disabled", "item falho não tem pasta")
        del vids

    def test_individual_files_and_second_run_continues_numbering(self):
        a = H.make_video(self.src / "clip com espaço.mp4")
        b = H.make_video(self.src / "outro.mov")
        self.dlg.next_files = (str(a), str(b))
        self.app.btn_add.invoke()
        self.app.set_output_dir(self.out)
        self.app.btn_start.invoke()
        self.run_until_idle()
        self.assertEqual(self.statuses(), ["success", "success"])
        snap = {p.relative_to(self.out): H.sha256(p) for p in self.out.rglob("*") if p.is_file()}
        self.app.clear_queue()
        self.app.add_paths([a, b])
        self.app.btn_start.invoke()
        self.run_until_idle()
        self.assertEqual(self.statuses(), ["success", "success"])
        self.assertEqual([self.folder_col(i) for i in self.app.tree.get_children()], ["003", "004"])
        now = {p.relative_to(self.out): H.sha256(p) for p in self.out.rglob("*") if p.is_file()}
        for k, h in snap.items():
            self.assertEqual(now[k], h, f"{k} sobrescrito")

    def test_destination_equals_source_folder(self):
        a = H.make_video(self.src / "a.mp4")
        before = H.snapshot(self.src)
        self.dlg.next_dir = [str(self.src)]
        self.app.btn_folder.invoke()
        self.app.set_output_dir(self.src)
        self.app.btn_start.invoke()
        self.run_until_idle()
        self.assertEqual(self.statuses(), ["success"])
        self.assertEqual(H.snapshot(self.src), before)
        self.assertNNN(self.src / "001")
        # recarregar a pasta não traz video.mp4 das saídas
        self.app.clear_queue()
        self.app.recursive.set(True)
        self.dlg.next_dir = [str(self.src)]
        self.app.btn_folder.invoke()
        self.assertEqual(len(self.app.tree.get_children()), 1)
        del a

    def test_start_without_destination_warns(self):
        self.app.add_paths([H.make_video(self.src / "a.mp4")])
        self.app.start()
        self.assertIsNone(self.app.job)
        self.assertTrue(self.dlg.of("showwarning") or self.dlg.of("showerror"))

    def test_destination_that_is_file_shows_error(self):
        f = self.root_dir / "sou arquivo"
        f.write_text("x")
        self.app.add_paths([H.make_video(self.src / "a.mp4")])
        self.app.set_output_dir(f)
        self.app.start()
        self.pump(0.2)
        self.assertIsNone(self.app.job)
        self.assertTrue(self.dlg.of("showerror") or self.dlg.of("showwarning"))

    def test_empty_folder_informs_user(self):
        self.dlg.next_dir = [str(self.src)]
        self.app.btn_folder.invoke()
        self.assertEqual(self.app.tree.get_children(), ())
        self.assertTrue(self.dlg.of("showinfo"))

    def test_ui_responsive_and_cancel_removes_current_folder(self):
        vids = [H.make_video(self.src / f"longo {i}.webm", duration=20.0, vcodec="libvpx-vp9",
                             acodec="libopus", size="640x480") for i in range(2)]
        self.app.add_paths(vids)
        self.app.set_output_dir(self.out)
        self.app.btn_start.invoke()
        worst, end = 0.0, time.time() + 2.0
        while time.time() < end:
            t0 = time.time(); self.tk.update(); worst = max(worst, time.time() - t0); time.sleep(0.02)
        self.assertLess(worst, 0.5, f"UI travou {worst:.2f}s")
        first = self.app.tree.get_children()[0]
        self.assertEqual(self.folder_col(first), "001", "pasta deve aparecer durante o processamento")
        self.dlg.yesno = True
        self.app.btn_cancel.invoke()
        self.run_until_idle(timeout=60)
        self.assertEqual(self.statuses(), ["cancelled", "cancelled"])
        self.assertEqual(os.listdir(self.out) if self.out.exists() else [], [])

    def test_recursive_folder_and_remove_with_delete_key(self):
        H.make_video(self.src / "raiz.mp4")
        (self.src / "sub pasta").mkdir()
        H.make_video(self.src / "sub pasta" / "dentro.mp4")
        self.dlg.next_dir = [str(self.src)]
        self.app.btn_folder.invoke()
        self.assertEqual(len(self.app.tree.get_children()), 1)
        self.app.recursive.set(True)
        self.dlg.next_dir = [str(self.src)]
        self.app.btn_folder.invoke()
        self.assertEqual(len(self.app.tree.get_children()), 2)
        first = self.app.tree.get_children()[0]
        self.app.tree.selection_set(first)
        self.assertTrue(self.app.tree.bind("<Delete>"))
        self.tk.focus_force()
        self.app.tree.focus_force()
        self.pump(0.2)
        if self.tk.focus_get() is self.app.tree:
            self.app.tree.event_generate("<Delete>")
        else:  # Wayland pode negar foco à janela de teste
            self.app.remove_selected()
        self.pump(0.1)
        self.assertEqual(len(self.app.tree.get_children()), 1)

    def test_rerun_processes_only_unfinished(self):
        self.app.add_paths([H.make_video(self.src / "bom.mp4"), H.make_invalid(self.src / "ruim.mp4")])
        self.app.set_output_dir(self.out)
        self.app.btn_start.invoke()
        self.run_until_idle()
        self.assertEqual(self.statuses(), ["success", "failed"])
        self.app.btn_start.invoke()
        self.run_until_idle()
        self.assertEqual(self.statuses(), ["success", "failed"])
        self.assertEqual(os.listdir(self.out), ["001"], "item concluído reprocessado")


class TestUIMissingFFmpeg(UITestBase):
    def setUp(self):
        self._env = H.EnvPatch(VIDEO_EXTRACTOR_FFMPEG="/caminho/inexistente/ffmpeg")
        self._env.__enter__()
        try:
            super().setUp()
        except Exception:
            self._env.__exit__()
            raise

    def tearDown(self):
        super().tearDown()
        self._env.__exit__()

    def test_banner_blocks_start_then_retry_recovers(self):
        self.assertFalse(self.app.deps_ok)
        self.assertIn("ffmpeg", self.app.dep_label.cget("text").lower())
        self.app.add_paths([H.make_video(self.src / "a.mp4")])
        self.app.set_output_dir(self.out)
        self.app.start()
        self.assertIsNone(self.app.job)
        self.assertTrue(self.dlg.of("showerror"))
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))
        self._env.__exit__()
        self.app.dep_retry.invoke()
        self.assertTrue(self.app.deps_ok)
        self.app.btn_start.invoke()
        self.run_until_idle()
        self.assertEqual(self.statuses(), ["success"])
        self._env = H.EnvPatch()


if __name__ == "__main__":
    unittest.main()
