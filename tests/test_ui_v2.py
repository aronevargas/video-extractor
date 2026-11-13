"""UI v2 na tela real: tema escuro/contraste e fluxo link -> download -> extração automática.

Downloader controlado (tests/fake_ytdlp.py) na fronteira de rede; extração FFmpeg REAL.
Botões reais acionados com .invoke(); Enter no campo de link via event_generate quando o
compositor dá foco à janela de teste.
"""
from __future__ import annotations

import os
import time
import unittest
from pathlib import Path

from tests import helpers as H
from tests.test_ui_integration import UITestBase, ui  # noqa: F401 (pula sem DISPLAY/ffmpeg)

FAKE = Path(__file__).resolve().parent / "fake_ytdlp.py"
URL = "https://www.instagram.com/reel/QaLink_01/"
CODE = "QaLink_01"


def _lum(hexcolor: str) -> float:
    hexcolor = hexcolor.lstrip("#")
    rgb = [int(hexcolor[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class TestDarkTheme(UITestBase):
    def _hex(self, color):
        r, g, b = self.tk.winfo_rgb(color)
        return "#%02x%02x%02x" % (r >> 8, g >> 8, b >> 8)

    def test_window_background_is_dark(self):
        bg = self._hex(self.tk.cget("bg"))
        self.assertLess(_lum(bg), 0.05, f"fundo não é escuro: {bg}")
        style = ui.ttk.Style(self.tk)
        tree_bg = style.lookup("Treeview", "background") or style.lookup("Treeview", "fieldbackground")
        self.assertLess(_lum(self._hex(tree_bg)), 0.05, f"Treeview clara: {tree_bg}")

    def test_wcag_contrast_of_text_pairs(self):
        c = ui.COLORS
        backgrounds = {k: c[k] for k in ("bg", "surface", "surface_2", "field", "select") if k in c}
        texts = {"text": c["text"], "muted": c["muted"], **{f"status:{k}": v for k, v in ui.STATUS_COLORS.items()}}
        low = []
        for tn, t in texts.items():
            for bn, b in backgrounds.items():
                r = contrast(t, b)
                if r < 4.5:
                    low.append(f"{tn} {t} sobre {bn} {b}: {r:.2f}")
        self.assertEqual(low, [], "pares abaixo de WCAG AA 4.5:1")
        self.assertGreaterEqual(contrast(c["accent_text"], c["accent"]), 4.5)

    def test_actual_widget_colors_follow_theme(self):
        style = ui.ttk.Style(self.tk)
        fg = style.lookup("TLabel", "foreground")
        bg = style.lookup("TLabel", "background") or self.tk.cget("bg")
        self.assertGreaterEqual(contrast(self._hex(fg), self._hex(bg)), 4.5)
        tfg = style.lookup("Treeview", "foreground")
        tbg = style.lookup("Treeview", "fieldbackground") or style.lookup("Treeview", "background")
        self.assertGreaterEqual(contrast(self._hex(tfg), self._hex(tbg)), 4.5)


class LinkUIBase(UITestBase):
    MODE = "ok"

    def setUp(self):
        self._env = H.EnvPatch(VIDEO_EXTRACTOR_YTDLP=str(FAKE), FAKE_YTDLP_MODE=self.MODE)
        self._env.__enter__()
        try:
            super().setUp()
            end = time.time() + 15        # check_downloader roda em thread
            while not self.app.downloader_ok and time.time() < end:
                self.pump(0.1)
        except Exception:
            self._env.__exit__()
            raise

    def tearDown(self):
        super().tearDown()
        self._env.__exit__()

    def mode(self, m):
        os.environ["FAKE_YTDLP_MODE"] = m

    def run_all(self, timeout=120):
        end = time.time() + timeout
        self.pump(0.2)
        while time.time() < end and (self.app.job is not None or any(
                i["status"] in ("queued", "running") for i in self.app.items.values())):
            self.tk.update()
            time.sleep(0.02)
        self.pump(0.3)
        self.assertIsNone(self.app.job, "não terminou")

    def link_rows(self):
        return [i for i in self.app.tree.get_children() if self.app.items[i].get("kind") == "link"]

    def children(self, iid):
        return list(self.app.tree.get_children(iid))


class TestLinkFlowUI(LinkUIBase):
    def test_link_button_downloads_and_extracts_automatically(self):
        self.assertTrue(self.app.downloader_ok)
        self.assertEqual(str(self.app.btn_link["state"]), "disabled", "botão deve exigir texto")
        self.app.set_output_dir(self.out)
        self.app.url_var.set("  https://instagram.com/reel/QaLink_01?igsh=abc  ")
        self.pump(0.1)
        self.assertEqual(str(self.app.btn_link["state"]), "normal")
        self.app.btn_link.invoke()
        self.assertEqual(self.app.url_var.get(), "", "campo deve limpar após aceitar")
        # janela continua respondendo durante o download/extração
        worst, end = 0.0, time.time() + 1.0
        while time.time() < end:
            t0 = time.time(); self.tk.update(); worst = max(worst, time.time() - t0); time.sleep(0.02)
        self.assertLess(worst, 0.5)
        self.run_all()
        links = self.link_rows()
        self.assertEqual(len(links), 1)
        self.assertEqual(self.app.items[links[0]]["status"], "success")
        self.assertEqual(self.app.items[links[0]]["url"], URL)
        kids = self.children(links[0])
        self.assertEqual(len(kids), 1)
        self.assertEqual(self.app.items[kids[0]]["status"], "success")
        self.assertEqual(os.listdir(self.out), ["001"])
        self.assertNNN(self.out / "001")
        self.assertEqual(self.folder_col(kids[0]), "001")
        self.assertEqual(self.folder_col(links[0]), "001")

    def test_enter_key_submits(self):
        self.app.set_output_dir(self.out)
        self.app.url_var.set(URL)
        self.tk.focus_force(); self.app.url_entry.focus_force(); self.pump(0.2)
        if self.tk.focus_get() is self.app.url_entry:
            self.app.url_entry.event_generate("<Return>")
        else:  # Wayland pode negar foco: aciona o mesmo handler ligado ao <Return>
            self.assertTrue(self.app.url_entry.bind("<Return>"))
            self.app.submit_url()
        self.run_all()
        self.assertEqual(len(self.link_rows()), 1)
        self.assertNNN(self.out / "001")

    def test_invalid_and_malicious_links_rejected_without_rows(self):
        self.app.set_output_dir(self.out)
        for bad in ("https://www.instagram.com.evil.com/p/x/", "https://evil.com/p/QaLink_01/",
                    "https://www.instagram.com/stories/user/1/", "não é link",
                    "https://www.instagram.com@evil.com/p/QaLink_01/"):
            with self.subTest(bad=bad):
                n = len(self.dlg.of("showwarning")) + len(self.dlg.of("showerror"))
                self.assertFalse(self.app.add_url(bad))
                self.assertGreater(len(self.dlg.of("showwarning")) + len(self.dlg.of("showerror")), n)
        self.assertEqual(self.app.tree.get_children(), ())
        self.assertIsNone(self.app.job)

    def test_link_without_output_dirs_refused(self):
        self.app.set_output_dir(None)
        self.assertFalse(self.app.add_url(URL))
        self.assertEqual(self.app.tree.get_children(), ())
        self.assertTrue(self.dlg.of("showwarning") or self.dlg.of("showerror"))

    def test_link_added_during_local_batch_runs_after_and_local_regression(self):
        vids = [H.make_video(self.src / "local 1 ção.mp4"), H.make_invalid(self.src / "local 2 ruim.mp4"),
                H.make_video(self.src / "local 3 mudo.mp4", audio=False)]
        self.dlg.next_dir = [str(self.src)]
        self.app.btn_folder.invoke()
        self.app.set_output_dir(self.out)
        self.app.btn_start.invoke()
        self.assertIsNotNone(self.app.job)
        self.assertTrue(self.app.add_url(URL))
        self.run_all()
        local = [i for i in self.app.tree.get_children() if self.app.items[i].get("kind") != "link"]
        self.assertEqual([self.app.items[i]["status"] for i in local], ["success", "failed", "no_audio"])
        self.assertEqual(self.app.items[self.link_rows()[0]]["status"], "success")
        self.assertEqual(sorted(os.listdir(self.out)), ["001", "002", "003"])
        self.assertNNN(self.out / "001")
        self.assertNNN(self.out / "002", audio=False)
        self.assertNNN(self.out / "003")
        self.assertEqual(self.folder_col(self.link_rows()[0]), "003")
        del vids

    def test_same_link_twice_creates_suffix_not_overwrite(self):
        self.app.set_output_dir(self.out)
        self.assertTrue(self.app.add_url(URL))
        self.run_all()
        first = H.sha256(self.out / "001" / "audio.mp3")
        self.assertTrue(self.app.add_url(URL))
        self.run_all()
        self.assertEqual(H.sha256(self.out / "001" / "audio.mp3"), first)
        self.assertEqual(sorted(os.listdir(self.out)), ["001", "002"])
        self.assertNNN(self.out / "002")


class TestCarouselUI(LinkUIBase):
    MODE = "carousel"

    def test_carousel_one_folder_per_video(self):
        self.app.set_output_dir(self.out)
        self.assertTrue(self.app.add_url(URL))
        self.run_all()
        link = self.link_rows()[0]
        kids = self.children(link)
        self.assertEqual([self.app.items[k]["status"] for k in kids], ["success", "success"])
        self.assertEqual([self.folder_col(k) for k in kids], ["001", "002"])
        self.assertIn(self.folder_col(link), ("001–002", "001-002"))
        self.assertEqual(sorted(os.listdir(self.out)), ["001", "002"])
        for k in ("001", "002"):
            self.assertNNN(self.out / k)


class TestLinkNoAudioUI(LinkUIBase):
    MODE = "no_audio"

    def test_no_audio_link_is_flagged_not_plain_success(self):
        self.app.set_output_dir(self.out)
        self.assertTrue(self.app.add_url(URL))
        self.run_all()
        link = self.link_rows()[0]
        self.assertEqual(self.app.items[link]["status"], "no_audio")
        kid = self.children(link)[0]
        self.assertEqual(self.app.items[kid]["status"], "no_audio")
        label = str(self.app.tree.item(kid, "values")[0])
        self.assertIn("sem áudio", label.lower())
        self.assertIn("áudio", str(self.app.tree.item(kid, "values")[2]).lower())
        self.assertNNN(self.out / "001", audio=False)


class TestLinkFailuresUI(LinkUIBase):
    def test_private_network_images_only(self):
        self.app.set_output_dir(self.out)
        for m in ("private", "network", "images_only"):
            with self.subTest(mode=m):
                self.mode(m)
                self.app.clear_queue()
                self.assertTrue(self.app.add_url(URL))
                self.run_all()
                link = self.link_rows()[0]
                self.assertEqual(self.app.items[link]["status"], "failed")
                detail = str(self.app.tree.item(link, "values")[2])
                self.assertTrue(detail.strip())
        self.assertFalse(self.out.exists() and any(self.out.iterdir()), "falha de download não cria pasta")

    def test_cancel_during_download(self):
        self.mode("slow")
        self.app.set_output_dir(self.out)
        self.assertTrue(self.app.add_url(URL))
        self.pump(1.5)
        self.assertIsNotNone(self.app.job)
        self.dlg.yesno = True
        t0 = time.time()
        self.app.btn_cancel.invoke()
        self.run_all(timeout=15)
        self.assertLess(time.time() - t0, 3.0)
        self.assertEqual(self.app.items[self.link_rows()[0]]["status"], "cancelled")
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))


class TestLinkWithoutYtdlpUI(UITestBase):
    def setUp(self):
        self._env = H.EnvPatch(VIDEO_EXTRACTOR_YTDLP="/nao/existe/yt-dlp")
        self._env.__enter__()
        try:
            super().setUp()
            self.pump(1.5)
        except Exception:
            self._env.__exit__()
            raise

    def tearDown(self):
        super().tearDown()
        self._env.__exit__()

    def test_hint_shown_link_refused_local_still_works(self):
        self.assertFalse(self.app.downloader_ok)
        self.assertIn("yt-dlp", self.app.link_hint.cget("text"))
        self.app.set_output_dir(self.out)
        self.assertFalse(self.app.add_url(URL))
        self.assertTrue(self.dlg.of("showerror"))
        self.assertEqual(self.app.tree.get_children(), ())
        vid = H.make_video(self.src / "local.mp4")
        self.app.add_paths([vid])
        self.app.btn_start.invoke()
        self.run_until_idle()
        self.assertEqual(self.statuses(), ["success"])


if __name__ == "__main__":
    unittest.main()
