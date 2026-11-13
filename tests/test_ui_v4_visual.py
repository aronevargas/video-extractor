"""UI v4 (reestilização inspirada na referência visual) na tela real.

Verifica o que a reestilização NÃO pode piorar, sem amarrar nomes de estilos ou valores
exatos de cor (o design pode mudar):

- nenhum controle cortado/fora da janela no tamanho padrão e no tamanho mínimo, com a fila
  vazia e com caminhos longos na fila;
- contraste WCAG por **estado** dos botões (normal/hover/pressionado ≥ 4.5:1 no texto),
  contorno de foco visível (≥ 3:1, WCAG 1.4.11) e desabilitado distinguível do habilitado;
- hierarquia: ação principal (Iniciar / Baixar e extrair) destacada em relação às
  secundárias; fundo quase preto e destaque azul, coerentes com a referência;
- caminhos longos: janela não cresce, destino mostra o final do caminho;
- sem dependências pesadas: o pacote importa só biblioteca padrão.
"""
from __future__ import annotations

import ast
import colorsys
import sys
from pathlib import Path

from tests import helpers as H
from tests.test_ui_integration import UITestBase, ui  # noqa: F401 (pula sem DISPLAY/ffmpeg)
from tests.test_ui_v2 import _lum, contrast

PKG = Path(__file__).resolve().parent.parent / "extractor"
LONG = "um nome de arquivo de vídeo realmente muito longo com acentuação ção e espaços " * 2


class V4Base(UITestBase):
    def hexc(self, color) -> str:
        r, g, b = self.tk.winfo_rgb(str(color))
        return "#%02x%02x%02x" % (r >> 8, g >> 8, b >> 8)

    def style(self):
        return ui.ttk.Style(self.tk)

    def lookup(self, stylename, option, state=None):
        st = self.style()
        val = st.lookup(stylename, option, state) if state else st.lookup(stylename, option)
        if not val:
            val = st.lookup("TButton", option, state) if state else st.lookup("TButton", option)
        if not val:
            val = st.lookup(".", option, state) if state else st.lookup(".", option)
        return val

    def buttons(self):
        return {n: getattr(self.app, n) for n in dir(self.app)
                if n.startswith("btn_") and isinstance(getattr(self.app, n), ui.ttk.Button)}

    def stylename(self, w):
        return w.cget("style") or w.winfo_class()

    # ------------------------------------------------------------ layout
    def clipped_widgets(self):
        """Controles mapeados que saem da janela ou do ancestral (Tk recorta filhos)."""
        top = self.tk
        tx, ty = top.winfo_rootx(), top.winfo_rooty()
        tw, th = top.winfo_width(), top.winfo_height()
        problems = []
        interesting = (ui.ttk.Button, ui.ttk.Checkbutton, ui.ttk.Entry, ui.ttk.Progressbar,
                       ui.ttk.Treeview, ui.ttk.Label, ui.ttk.Scrollbar, ui.ttk.Radiobutton)

        def walk(w):
            for c in w.winfo_children():
                yield c
                yield from walk(c)

        for w in walk(top):
            if not isinstance(w, interesting) or not w.winfo_ismapped():
                continue
            x, y = w.winfo_rootx(), w.winfo_rooty()
            ww, wh = w.winfo_width(), w.winfo_height()
            name = f"{w.winfo_class()} {str(w)} '{(w.cget('text') if 'text' in w.keys() else '')}'"
            if x < tx or y < ty or x + ww > tx + tw + 1 or y + wh > ty + th + 1:
                problems.append(f"{name} fora da janela ({x - tx},{y - ty},{ww}x{wh}) janela {tw}x{th}")
                continue
            p = w.master
            while p is not None and p is not top:
                px, py = p.winfo_rootx(), p.winfo_rooty()
                if x < px - 1 or y < py - 1 or x + ww > px + p.winfo_width() + 1 \
                        or y + wh > py + p.winfo_height() + 1:
                    problems.append(f"{name} recortado pelo contêiner {p}")
                    break
                p = p.master
            # Botões/checkbuttons precisam do tamanho pedido inteiro (texto não truncado).
            if isinstance(w, (ui.ttk.Button, ui.ttk.Checkbutton, ui.ttk.Radiobutton)):
                if ww + 1 < w.winfo_reqwidth() or wh + 1 < w.winfo_reqheight():
                    problems.append(f"{name} encolhido {ww}x{wh} < pedido "
                                    f"{w.winfo_reqwidth()}x{w.winfo_reqheight()}")
            # Texto de rótulo maior que o espaço recebido = texto cortado na borda.
            if isinstance(w, ui.ttk.Label) and str(w.cget("text")).strip():
                if ww + 2 < w.winfo_reqwidth() or wh + 2 < w.winfo_reqheight():
                    problems.append(f"{name} texto cortado: {ww}x{wh} < pedido "
                                    f"{w.winfo_reqwidth()}x{w.winfo_reqheight()}")
            if isinstance(w, (ui.ttk.Treeview, ui.ttk.Entry)) and (ww < 40 or wh < 10):
                problems.append(f"{name} praticamente sem espaço ({ww}x{wh})")
        return problems

    def resize(self, w, h):
        self.tk.geometry(f"{w}x{h}")
        self.pump(0.6)

    def fill_long_queue(self):
        deep = self.src / ("subpasta com nome comprido ção " * 3).strip()
        vids = [H.make_video(deep / f"{i:02d} {LONG.strip()}.mp4") for i in range(1, 4)]
        vids.append(H.make_video(self.src / "curto.mp4"))
        self.app.add_paths([str(v) for v in vids])
        longdest = self.out / ("destino com caminho muito longo ção " * 4).strip()
        self.app.set_output_dir(longdest)
        self.pump(0.4)
        return longdest


class TestV4Layout(V4Base):
    def default_and_min(self):
        self.pump(0.3)
        geo = self.tk.winfo_geometry()
        minw, minh = self.tk.minsize()
        return geo, (minw, minh)

    def test_default_size_has_no_clipped_controls_empty_and_full(self):
        self.pump(0.5)
        self.assertEqual(self.clipped_widgets(), [], "fila vazia, tamanho padrão")
        self.fill_long_queue()
        self.assertEqual(self.clipped_widgets(), [], "fila com caminhos longos, tamanho padrão")

    def test_min_size_has_no_clipped_controls(self):
        minw, minh = self.tk.minsize()
        self.assertGreater(minw, 1, "sem tamanho mínimo definido")
        self.resize(minw, minh)
        self.assertEqual(self.clipped_widgets(), [], f"fila vazia em {minw}x{minh}")
        self.fill_long_queue()
        self.pump(0.3)
        self.assertEqual(self.clipped_widgets(), [], f"caminhos longos em {minw}x{minh}")
        # A fila continua útil no tamanho mínimo: pelo menos 3 linhas (+ cabeçalho).
        rowh = int(self.style().lookup("Treeview", "rowheight") or 20)
        self.assertGreaterEqual(self.app.tree.winfo_height() // max(rowh, 1), 4,
                                f"fila muito baixa no mínimo: {self.app.tree.winfo_height()}px")

    def test_default_size_queue_shows_rows(self):
        self.pump(0.5)
        rowh = int(self.style().lookup("Treeview", "rowheight") or 20)
        # Base v3 neste ambiente (aviso do yt-dlp ocupando 3 linhas): 5 (4 linhas + cabeçalho).
        self.assertGreaterEqual(self.app.tree.winfo_height() // max(rowh, 1), 5,
                                "fila mais baixa que na v3 no tamanho padrão")

    def test_long_paths_do_not_grow_window_and_dest_shows_end(self):
        self.pump(0.4)
        w0, h0 = self.tk.winfo_width(), self.tk.winfo_height()
        longdest = self.fill_long_queue()
        self.pump(0.5)
        self.assertEqual((self.tk.winfo_width(), self.tk.winfo_height()), (w0, h0),
                         "janela mudou de tamanho com caminhos longos")
        rows = self.app.tree.get_children()
        self.assertEqual(len(rows), 4)
        texts = [self.app.tree.item(i, "text") for i in rows]
        self.assertTrue(any("realmente muito longo" in t for t in texts), texts)
        self.assertEqual(Path(self.app.out_picker.path.get()), longdest)
        self.assertAlmostEqual(self.app.out_picker.entry.xview()[1], 1.0, places=2,
                               msg="campo de destino não mostra o final do caminho")


    def test_dest_keeps_showing_path_end_after_resize_to_min(self):
        self.pump(0.3)
        longdest = self.fill_long_queue()
        minw, minh = self.tk.minsize()
        self.resize(minw, minh)
        self.assertEqual(Path(self.app.out_picker.path.get()), longdest)
        self.assertAlmostEqual(self.app.out_picker.entry.xview()[1], 1.0, places=2,
                               msg="após redimensionar, o destino não mostra mais o fim do caminho")


    def test_min_size_fits_1366x768_work_area(self):
        # 768 - barra superior do GNOME (32) - barra de título (~40) = 696 px úteis;
        # no Windows: 768 - barra de tarefas (48) - título (~31) = 689.
        minw, minh = self.tk.minsize()
        self.assertLessEqual(minw, 1366 - 80)
        self.assertLessEqual(minh, 689, f"minsize {minw}x{minh} não cabe numa tela 1366x768")

    def test_initial_window_fits_screen(self):
        self.pump(0.3)
        sh = self.tk.winfo_screenheight()
        self.assertLessEqual(self.tk.winfo_height(), sh - 72,
                             f"janela inicial {self.tk.winfo_height()}px numa tela de {sh}px")


class TestV4LinkPlaceholder(V4Base):
    def test_native_tk_dialog_while_link_focused_no_callback_error(self):
        """Foco num widget só-Tcl (diálogo de pasta do Tk no Linux) não pode quebrar o
        placeholder do link (Misc.focus_get() levanta KeyError nesse caso)."""
        errors = []
        self.tk.report_callback_exception = lambda *a: errors.append(repr(a[1]))
        self.tk.focus_force()
        self.app.url_entry.focus_force()
        self.pump(0.3)
        import tkinter.filedialog as real_fd
        real = real_fd.Directory  # diálogo real do Tk, não o substituto dos testes

        def close_dialog():
            for w in self.tk.tk.call("winfo", "children", "."):
                if str(w).startswith(".__tk"):
                    self.tk.tk.call("destroy", w)
        self.tk.after(1200, close_dialog)
        real(self.tk, title="qa").show()
        self.pump(0.5)
        self.assertEqual(errors, [], "exceção em callback ao abrir diálogo nativo do Tk")
        if not self.app.url_var.get() and self.tk.focus_get() is not self.app.url_entry:
            self.assertTrue(self.app.url_placeholder.winfo_ismapped(),
                            "campo de link vazio ficou sem a dica depois do diálogo")


class TestV4ThemeStates(V4Base):
    def test_button_text_contrast_in_every_interactive_state(self):
        low = []
        for name, btn in self.buttons().items():
            sn = self.stylename(btn)
            for state in (None, "active", "pressed", "focus"):
                fg = self.lookup(sn, "foreground", [state] if state else None)
                bg = self.lookup(sn, "background", [state] if state else None)
                if not fg or not bg:
                    continue
                r = contrast(self.hexc(fg), self.hexc(bg))
                if r < 4.5:
                    low.append(f"{name} ({sn}) estado={state or 'normal'} {fg} sobre {bg}: {r:.2f}")
        self.assertEqual(low, [], "texto de botão abaixo de 4.5:1")

    def test_disabled_buttons_are_distinguishable(self):
        same = []
        for name, btn in self.buttons().items():
            sn = self.stylename(btn)
            n = (self.hexc(self.lookup(sn, "foreground")), self.hexc(self.lookup(sn, "background")))
            d = (self.hexc(self.lookup(sn, "foreground", ["disabled"])),
                 self.hexc(self.lookup(sn, "background", ["disabled"])))
            if n == d:
                same.append(f"{name} ({sn}) desabilitado idêntico ao normal {n}")
        self.assertEqual(same, [])

    def test_focus_indicator_visible(self):
        c = ui.COLORS
        surfaces = [c[k] for k in ("bg", "surface") if k in c]
        problems = []
        for name, btn in self.buttons().items():
            sn = self.stylename(btn)
            ring = self.lookup(sn, "focuscolor", ["focus"]) or self.lookup(sn, "bordercolor", ["focus"])
            self.assertTrue(ring, f"{name}: sem cor de foco")
            for s in surfaces:
                r = contrast(self.hexc(ring), s)
                if r < 3.0:
                    problems.append(f"{name} ({sn}) foco {ring} sobre {s}: {r:.2f}")
        ering = self.lookup("TEntry", "bordercolor", ["focus"]) or self.lookup("TEntry", "lightcolor", ["focus"])
        self.assertTrue(ering, "campo de texto sem indicação de foco")
        for s in surfaces:
            if contrast(self.hexc(ering), s) < 3.0:
                problems.append(f"TEntry foco {ering} sobre {s}")
        self.assertEqual(problems, [], "indicador de foco abaixo de 3:1 (WCAG 1.4.11)")

    def test_status_colors_distinct_and_readable_on_selection(self):
        sc = {k: self.hexc(v) for k, v in ui.STATUS_COLORS.items()}
        self.assertEqual(len(set(sc[k] for k in ("ok", "warn", "error", "running"))), 4,
                         f"cores de status repetidas: {sc}")
        sel = ui.COLORS.get("select")
        if sel:
            for k, v in sc.items():
                self.assertGreaterEqual(contrast(v, sel), 4.5, f"status {k} sobre seleção")

    def test_hierarchy_and_reference_coherence(self):
        c = ui.COLORS
        bg = self.hexc(self.tk.cget("bg"))
        self.assertLess(_lum(bg), 0.02, f"fundo não é quase preto como a referência: {bg}")
        primary = [self.app.btn_start, self.app.btn_link]
        secondary = [self.app.btn_add, self.app.btn_folder, self.app.btn_clear]
        pbg = {self.hexc(self.lookup(self.stylename(b), "background")) for b in primary}
        sbg = {self.hexc(self.lookup(self.stylename(b), "background")) for b in secondary}
        self.assertEqual(len(pbg), 1, f"ações principais com fundos diferentes: {pbg}")
        self.assertFalse(pbg & sbg, "ação principal igual às secundárias")
        accent = pbg.pop()
        r, g, b = (int(accent[i:i + 2], 16) / 255 for i in (1, 3, 5))
        h, _l, s = colorsys.rgb_to_hls(r, g, b)
        self.assertTrue(200 <= h * 360 <= 245 and s >= 0.6,
                        f"destaque {accent} não é o azul saturado da referência (h={h*360:.0f}, s={s:.2f})")
        # O botão principal se destaca do cartão/fundo (componente não textual ≥ 3:1).
        for k in ("bg", "surface"):
            if k in c:
                self.assertGreaterEqual(contrast(accent, c[k]), 3.0, f"principal vs {k}")
        # Superfícies distinguíveis do fundo (hierarquia de cartões).
        if "surface" in c:
            self.assertNotEqual(self.hexc(c["surface"]), bg)


class TestV4NoHeavyDependencies(V4Base):
    def test_package_imports_only_stdlib(self):
        allowed = set(sys.stdlib_module_names) | {"extractor", "__future__"}
        bad = []
        for f in sorted(PKG.glob("*.py")):
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    mods = [node.module]
                bad += [f"{f.name}: {m}" for m in mods if m.split(".")[0] not in allowed]
        self.assertEqual(bad, [], "dependência fora da biblioteca padrão")

    def test_no_network_or_external_assets_in_ui(self):
        src = (PKG / "ui.py").read_text(encoding="utf-8")
        for needle in ("urlopen", "urllib.request", "PhotoImage(file=\"http", "requests."):
            self.assertNotIn(needle, src)
        # Imagens/fontes, se houver, precisam estar no repositório.
        for p in PKG.rglob("*"):
            if p.suffix.lower() in {".png", ".gif", ".ttf", ".otf"}:
                self.assertLess(p.stat().st_size, 512 * 1024, f"asset pesado: {p}")
