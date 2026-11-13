"""Interface gráfica (Tkinter, tema escuro) do Extrator de Vídeos.

A UI só monta a fila e mostra o andamento; o trabalho pesado é feito pelo motor
(``engine.BatchProcessor`` para arquivos locais e ``engine.InstagramProcessor``
para links), cada um na sua própria thread. Os eventos do motor chegam na thread
de trabalho e são repassados à thread do Tk por uma ``queue.Queue`` lida
periodicamente com ``root.after`` — nenhum widget é tocado fora da thread
principal.

Fila: um trabalho por vez. "Iniciar fila" enfileira todos os itens locais não
concluídos; um link colado entra na fila e começa sozinho (baixa e extrai) assim
que nada mais estiver rodando.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from extractor import engine

APP_TITLE = "Extrator de Vídeos"
POLL_MS = 80

# ----------------------------------------------------------------- tema escuro
# Todas as cores ficam aqui (o QA mede o contraste a partir destas constantes).
# Referência visual: paleta do site sharkbot.com.br (inspecionada em 2026-11-13; ver
# docs/ui-visual.md). Quase-preto, painéis sutis, azul como única cor de destaque.
# Transparências do site (ex.: white/8%) foram convertidas em cores sólidas, pois o Tk não
# tem alfa.
COLORS = {
    "bg": "#050505",            # fundo da janela (--surface-base)
    "surface": "#0b0b0c",       # lista/painéis (--surface-100)
    "surface_2": "#141416",     # cabeçalho da lista, botão secundário em hover (white/4%)
    "hover": "#1a1a1d",         # hover (--surface-300)
    "pressed": "#232327",
    "field": "#0e0e10",         # campos de texto
    "border": "#27272a",        # bordas finas (white/8–10%)
    "border_strong": "#3f3f46", # borda em hover (white/15–20%)
    "divider": "#161618",       # linha entre seções (white/5%)
    "text": "#ffffff",          # --text
    "text_secondary": "#e5e5e5",
    "muted": "#a1a1aa",         # --text-muted
    "disabled": "#71717a",      # --text-disabled
    "accent": "#2563eb",        # botão principal (--brand-600; brand-500 com texto branco
    "accent_hover": "#1d4ed8",  #   não atinge 4,5:1, então o fundo usa o tom 600)
    "accent_pressed": "#1e40af",
    "accent_disabled": "#111a2e",
    "accent_text": "#ffffff",
    "brand": "#3b82f6",         # --brand-500: barra de progresso, detalhes não textuais
    "brand_text": "#60a5fa",    # --brand-400: textos azuis (rótulos de passo, links)
    "badge_bg": "#0a1426",      # pílula de passo (brand-500 a 10% sobre o fundo)
    "badge_border": "#16294a",  # (brand-500 a 20%)
    "focus": "#60a5fa",         # contorno de foco
    "select": "#152a4a",        # linha selecionada (--brand-900 escurecido)
    "success": "#34d399",       # emerald-400 (--success)
    "warning": "#fbbf24",       # amber-400 (--warning)
    "error": "#f87171",         # red-400 (--danger)
    "info": "#60a5fa",          # brand-400
    "danger_bg": "#1a0a0a",     # faixa de aviso (FFmpeg ausente)
    "danger_border": "#7f1d1d",
    "danger_text": "#fecaca",
}
STATUS_COLORS = {
    "ok": COLORS["success"],
    "warn": COLORS["warning"],
    "error": COLORS["error"],
    "running": COLORS["info"],
    "pending": COLORS["text"],
}

# ------------------------------------------------------------- rótulos/estados
ST_PENDING = "Na fila"
ST_QUEUED = "Aguardando"
ST_RUNNING = "Processando"
ST_LABELS = {
    "success": "Concluído",
    "no_audio": "Concluído (sem áudio)",
    "partial": "Parcial",
    "failed": "Falhou",
    "cancelled": "Cancelado",
}
STAGE_LABELS = {"probe": "Analisando", "audio": "Extraindo áudio", "video": "Gerando vídeo",
                "frames": "Extraindo frames",
                "download": "Baixando"}
STATUS_TAG = {"success": "ok", "no_audio": "warn", "partial": "warn",
              "failed": "error", "cancelled": "error"}
DONE_STATUSES = {"success", "no_audio"}          # não são reprocessados
BUSY_STATUSES = {"queued", "running"}            # já estão na fila de execução

VIDEO_PATTERNS = " ".join(
    f"*{ext} *{ext.upper()}" for ext in sorted(getattr(engine, "VIDEO_EXTENSIONS", ()))
) or "*.mp4 *.mkv *.mov *.avi *.webm"


def open_in_file_manager(path: Path) -> None:
    """Abre a pasta no gerenciador de arquivos do sistema."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:  # noqa: BLE001 - só informativo
        messagebox.showwarning(APP_TITLE, f"Não foi possível abrir a pasta:\n{exc}")


def short_url(url: str) -> str:
    text = url.split("://", 1)[-1].split("?", 1)[0].rstrip("/")
    return text[4:] if text.startswith("www.") else text


# Fontes: o site usa Inter (texto) e Space Grotesk (títulos). Usa-se a primeira família
# instalada; sem nenhuma delas, a fonte padrão do sistema (nada é baixado).
TEXT_FONTS = ("Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Noto Sans", "Ubuntu",
              "Cantarell", "DejaVu Sans")
DISPLAY_FONTS = ("Space Grotesk", "Inter", "Segoe UI Semibold", "SF Pro Display",
                 "Helvetica Neue", "Noto Sans", "Ubuntu", "DejaVu Sans")


def _pick_family(root: tk.Tk, wanted, fallback: str) -> str:
    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        return fallback
    return next((f for f in wanted if f in available), fallback)


def apply_dark_theme(root: tk.Tk) -> dict:
    """Tema escuro inspirado em sharkbot.com.br (ttk 'clam' + banco de opções dos diálogos)."""
    c = COLORS
    base = tkfont.nametofont("TkDefaultFont")
    fam = _pick_family(root, TEXT_FONTS, base.cget("family"))
    display = _pick_family(root, DISPLAY_FONTS, fam)
    base.configure(family=fam, size=10)
    for name in ("TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=fam, size=10)
        except tk.TclError:
            pass
    fonts = {
        "title": tkfont.Font(root, family=display, size=18, weight="bold"),
        "section": tkfont.Font(root, family=display, size=12, weight="bold"),
        "step": tkfont.Font(root, family=fam, size=8, weight="bold"),
        "button": tkfont.Font(root, family=fam, size=10, weight="bold"),
        "small": tkfont.Font(root, family=fam, size=9),
        "heading": tkfont.Font(root, family=fam, size=8, weight="bold"),
    }

    root.configure(background=c["bg"])
    # Diálogos clássicos do Tk (seletor de arquivos no Linux, caixas de mensagem).
    for pattern, value in (
        ("*Background", c["surface"]), ("*Foreground", c["text"]),
        ("*activeBackground", c["hover"]), ("*activeForeground", c["text"]),
        ("*selectBackground", c["select"]), ("*selectForeground", c["text"]),
        ("*highlightBackground", c["surface"]), ("*highlightColor", c["focus"]),
        ("*insertBackground", c["text"]), ("*disabledForeground", c["disabled"]),
        ("*Entry.Background", c["field"]), ("*Listbox.Background", c["field"]),
        ("*Canvas.Background", c["field"]), ("*Text.Background", c["field"]),
        ("*troughColor", c["field"]),
    ):
        root.option_add(pattern, value)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=c["bg"], foreground=c["text"], fieldbackground=c["field"],
                    bordercolor=c["border"], lightcolor=c["bg"], darkcolor=c["bg"],
                    troughcolor=c["field"], focuscolor=c["focus"], selectbackground=c["select"],
                    selectforeground=c["text"], insertcolor=c["text"], arrowcolor=c["muted"],
                    font=base)
    style.map(".", foreground=[("disabled", c["disabled"])])

    # Fundos: seções sem cartão (como as seções do site), separadas por uma linha fina.
    style.configure("TFrame", background=c["bg"])
    style.configure("Inner.TFrame", background=c["bg"])
    style.configure("Card.TFrame", background=c["bg"])
    style.configure("Divider.TFrame", background=c["divider"])
    style.configure("TLabel", background=c["bg"], foreground=c["text"])
    style.configure("Title.TLabel", font=fonts["title"])
    style.configure("Subtitle.TLabel", foreground=c["muted"])
    style.configure("Section.TLabel", background=c["bg"], font=fonts["section"])
    # Pílula de passo: azul claro sobre azul a 10%, borda a 20% (como "RECURSOS" no site).
    style.configure("Step.TLabel", background=c["badge_bg"], foreground=c["brand_text"],
                    bordercolor=c["badge_border"], relief="solid", borderwidth=1,
                    font=fonts["step"], anchor="center", padding=(8, 2))
    style.configure("Card.TLabel", background=c["bg"], foreground=c["text_secondary"])
    style.configure("Muted.TLabel", background=c["bg"], foreground=c["muted"], font=fonts["small"])
    style.configure("Placeholder.TLabel", background=c["field"], foreground=c["muted"])
    style.configure("Warn.TLabel", background=c["bg"], foreground=c["warning"], font=fonts["small"])
    style.configure("Status.TLabel", background=c["bg"], foreground=c["muted"])
    style.configure("Banner.TFrame", background=c["danger_bg"], bordercolor=c["danger_border"],
                    relief="solid", borderwidth=1)
    style.configure("Banner.TLabel", background=c["danger_bg"], foreground=c["danger_text"])

    # Botões
    # Secundário (padrão): fundo transparente com contorno fino, como "Ver Demonstração".
    style.configure("TButton", background=c["bg"], foreground=c["text"],
                    bordercolor=c["border"], lightcolor=c["bg"], darkcolor=c["bg"],
                    padding=(14, 6), relief="solid", borderwidth=1, focusthickness=0)
    style.map("TButton",
              background=[("disabled", c["bg"]), ("pressed", c["pressed"]), ("active", c["surface_2"])],
              foreground=[("disabled", c["disabled"])],
              bordercolor=[("focus", c["focus"]), ("disabled", c["divider"]),
                           ("active", c["border_strong"])],
              lightcolor=[("pressed", c["pressed"]), ("active", c["surface_2"])],
              darkcolor=[("pressed", c["pressed"]), ("active", c["surface_2"])])
    # Principal: azul sólido, texto branco em negrito ("Criar Conta").
    style.configure("Accent.TButton", background=c["accent"], foreground=c["accent_text"],
                    bordercolor=c["accent"], lightcolor=c["accent"], darkcolor=c["accent"],
                    font=fonts["button"], padding=(20, 9))
    style.map("Accent.TButton",
              background=[("disabled", c["accent_disabled"]), ("pressed", c["accent_pressed"]),
                          ("active", c["accent_hover"])],
              foreground=[("disabled", c["disabled"])],
              bordercolor=[("focus", c["focus"]), ("disabled", c["accent_disabled"]),
                           ("pressed", c["accent_pressed"]), ("active", c["accent_hover"])],
              lightcolor=[("disabled", c["accent_disabled"]), ("pressed", c["accent_pressed"]),
                          ("active", c["accent_hover"])],
              darkcolor=[("disabled", c["accent_disabled"]), ("pressed", c["accent_pressed"]),
                         ("active", c["accent_hover"])])
    # Discreto: só texto cinza que clareia no hover (links do menu do site). Sem borda até ter foco.
    style.configure("Ghost.TButton", background=c["bg"], foreground=c["muted"],
                    bordercolor=c["bg"], lightcolor=c["bg"], darkcolor=c["bg"], padding=(10, 6))
    style.map("Ghost.TButton",
              background=[("disabled", c["bg"]), ("pressed", c["pressed"]), ("active", c["surface_2"])],
              foreground=[("disabled", c["disabled"]), ("active", c["text"])],
              bordercolor=[("focus", c["focus"]), ("disabled", c["bg"]), ("active", c["surface_2"])],
              lightcolor=[("active", c["surface_2"])], darkcolor=[("active", c["surface_2"])])
    style.configure("Danger.TButton", foreground=c["error"])
    style.map("Danger.TButton", foreground=[("disabled", c["disabled"])],
              bordercolor=[("focus", c["focus"]), ("disabled", c["divider"]), ("active", c["error"])])

    # Campos
    style.configure("TEntry", fieldbackground=c["field"], foreground=c["text"],
                    bordercolor=c["border"], lightcolor=c["field"], darkcolor=c["field"],
                    padding=(10, 7), insertcolor=c["text"])
    style.map("TEntry",
              bordercolor=[("focus", c["focus"]), ("hover", c["border_strong"])],
              lightcolor=[("focus", c["focus"])],
              fieldbackground=[("readonly", c["field"]), ("disabled", c["bg"])],
              foreground=[("disabled", c["disabled"])])
    style.configure("TCheckbutton", background=c["bg"], foreground=c["muted"],
                    indicatorbackground=c["field"], indicatorforeground=c["accent_text"],
                    indicatormargin=(0, 0, 8, 0), padding=(2, 4), upperbordercolor=c["border"],
                    lowerbordercolor=c["border"])
    style.map("TCheckbutton",
              background=[("active", c["bg"])],
              foreground=[("disabled", c["disabled"]), ("active", c["text"]), ("selected", c["text"])],
              indicatorbackground=[("disabled", c["bg"]), ("selected", c["accent"])])

    # Lista
    style.configure("Treeview", background=c["surface"], fieldbackground=c["surface"],
                    foreground=c["text_secondary"], bordercolor=c["border"],
                    lightcolor=c["surface"], darkcolor=c["surface"], rowheight=26)
    style.map("Treeview", background=[("selected", c["select"])],
              foreground=[("selected", c["text"])])
    style.configure("Treeview.Heading", background=c["surface_2"], foreground=c["muted"],
                    bordercolor=c["border"], lightcolor=c["surface_2"], darkcolor=c["surface_2"],
                    relief="flat", padding=(10, 7), font=fonts["heading"])
    style.map("Treeview.Heading", background=[("active", c["hover"])],
              foreground=[("active", c["text"])])
    style.configure("Vertical.TScrollbar", background=c["surface_2"], troughcolor=c["surface"],
                    bordercolor=c["surface"], lightcolor=c["surface_2"], darkcolor=c["surface_2"],
                    arrowcolor=c["muted"])
    style.map("Vertical.TScrollbar", background=[("active", c["hover"])])
    style.configure("Horizontal.TProgressbar", background=c["brand"], troughcolor=c["hover"],
                    bordercolor=c["hover"], lightcolor=c["brand"], darkcolor=c["brand"],
                    thickness=6)
    return fonts


class FolderPicker(ttk.Frame):
    """Linha: rótulo + caminho (somente leitura) + seletor nativo + Abrir."""

    def __init__(self, master, label: str, dialog_title: str, on_change=None):
        super().__init__(master, style="Inner.TFrame")
        self.dialog_title = dialog_title
        self.on_change = on_change
        self.path = tk.StringVar(value="")

        self.label = ttk.Label(self, text=label, style="Card.TLabel")
        self.label.grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.entry = ttk.Entry(self, textvariable=self.path, state="readonly")
        self.entry.grid(row=0, column=1, sticky="ew")
        self.button = ttk.Button(self, text="Escolher pasta…", command=self.choose)
        self.button.grid(row=0, column=2, padx=(8, 0))
        self.open_button = ttk.Button(self, text="Abrir", style="Ghost.TButton", command=self.open)
        self.open_button.grid(row=0, column=3, padx=(6, 0))
        self.columnconfigure(1, weight=1)
        # Após redimensionar, volta a mostrar o fim do caminho (nome da pasta).
        self.entry.bind("<Configure>", lambda _e: self.path.get() and self.entry.xview_moveto(1.0),
                        add="+")
        self.path.trace_add("write", lambda *_: self._sync_placeholder())
        self._sync_placeholder()

    def _sync_placeholder(self) -> None:
        # Mostra uma dica dentro do campo vazio sem alterar o valor real.
        if not self.path.get():
            self.entry.configure(textvariable="")
            self.entry.state(["!readonly"])
            self.entry.delete(0, "end")
            self.entry.insert(0, "Nenhuma pasta escolhida")
            self.entry.configure(foreground=COLORS["muted"])
            self.entry.state(["readonly"])
        else:
            self.entry.configure(textvariable=self.path, foreground=COLORS["text"])
            # Caminhos longos: mostra o final (o nome da pasta), não o começo.
            self.entry.after_idle(lambda: self.entry.xview_moveto(1.0))

    def choose(self) -> None:
        initial = self.path.get() or str(Path.home())
        chosen = filedialog.askdirectory(parent=self.winfo_toplevel(), title=self.dialog_title,
                                         initialdir=initial, mustexist=False)
        if chosen:
            self.path.set(str(Path(chosen)))
            self._changed()

    def open(self) -> None:
        p = self.value()
        if p is None:
            messagebox.showinfo(APP_TITLE, "Escolha a pasta primeiro.")
        elif not p.is_dir():
            messagebox.showinfo(APP_TITLE, "A pasta ainda não existe; ela será criada ao iniciar.")
        else:
            open_in_file_manager(p)

    def value(self) -> Path | None:
        text = self.path.get().strip()
        return Path(text) if text else None

    def set_locked(self, locked: bool) -> None:
        self.button.configure(state="disabled" if locked else "normal")

    def _changed(self) -> None:
        if self.on_change:
            self.on_change()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.job = None                 # processador em execução (Batch ou Instagram)
        self.job_kind: str | None = None
        self.job_token = 0
        self.job_rows: list[str] = []   # lote local: iid por índice
        self.link_iid: str | None = None  # link em execução: linha-pai
        self.link_children: dict[int, str] = {}
        self.link_failed = False
        self.items: dict[str, dict] = {}
        self.deps_ok = False
        self.downloader_ok = False
        self.downloader_message = ""
        self.cancel_requested = False
        self.session_problems = 0
        self.closing = False

        root.title(APP_TITLE)
        # Mínimo cabe na área útil de uma tela 1366x768 (com barra de título e painel do sistema).
        # A altura inicial também respeita telas baixas: 820 px ou a altura da tela menos 100.
        root.minsize(820, 680)
        width = min(1040, max(820, root.winfo_screenwidth() - 80))
        height = min(820, max(680, root.winfo_screenheight() - 100))
        root.geometry(f"{width}x{height}")
        self.fonts = apply_dark_theme(root)
        self._build()
        self._refresh_buttons()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(POLL_MS, self._poll_events)
        root.after(50, self.check_dependencies)
        root.after(80, self.check_downloader)

    # ------------------------------------------------------------------ layout
    @staticmethod
    def _auto_wrap(label: ttk.Label, margin: int = 8) -> None:
        """Quebra o texto conforme a largura disponível (janelas menores não cortam texto)."""
        label.master.bind("<Configure>", lambda e: label.configure(
            wraplength=max(200, e.width - margin)), add="+")

    def _card(self, parent, row: int, step: str, title: str, expand: bool = False) -> ttk.Frame:
        """Seção sem cartão: linha divisória fina, pílula 'PASSO N', título e conteúdo."""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=row, column=0, sticky="nsew", pady=(10, 0))
        if expand:
            parent.rowconfigure(row, weight=1)
        card.columnconfigure(0, weight=1)
        ttk.Frame(card, style="Divider.TFrame", height=1).grid(row=0, column=0, sticky="ew",
                                                               pady=(0, 12))
        head = ttk.Frame(card, style="Inner.TFrame")
        head.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(head, text=f"PASSO {step}", style="Step.TLabel").pack(side="left")
        ttk.Label(head, text=title, style="Section.TLabel").pack(side="left", padx=(12, 0))
        body = ttk.Frame(card, style="Inner.TFrame")
        body.grid(row=2, column=0, sticky="nsew")
        card.rowconfigure(2, weight=1)
        body.columnconfigure(0, weight=1)
        body.header = head  # type: ignore[attr-defined]  # para ações no cabeçalho da seção
        return body

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=(28, 18, 28, 18))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        title = ttk.Frame(header)
        title.pack(anchor="w")
        # Título com a segunda palavra em azul (destaque usado nos títulos do site).
        ttk.Label(title, text="Extrator de", style="Title.TLabel").pack(side="left")
        ttk.Label(title, text="Vídeos", style="Title.TLabel",
                  foreground=COLORS["brand_text"]).pack(side="left", padx=(6, 0))
        subtitle = ttk.Label(header, style="Subtitle.TLabel", justify="left",
                  text="Cada vídeo vira uma pasta numerada: MP3 (se tiver som), vídeo sem áudio e "
                       "4 frames. Originais intactos.")
        subtitle.pack(anchor="w", pady=(2, 0), fill="x")
        self._auto_wrap(subtitle)

        # Aviso de FFmpeg ausente (só aparece quando necessário).
        self.dep_frame = ttk.Frame(outer, style="Banner.TFrame", padding=(12, 8))
        self.dep_frame.columnconfigure(0, weight=1)
        self.dep_label = ttk.Label(self.dep_frame, text="", style="Banner.TLabel",
                                   wraplength=760, justify="left")
        self.dep_label.grid(row=0, column=0, sticky="w")
        self._auto_wrap(self.dep_label, 200)
        self.dep_retry = ttk.Button(self.dep_frame, text="Verificar novamente",
                                    command=self.check_dependencies)

        # 1. Adicionar
        add = self._card(outer, 2, "1", "Adicionar vídeos")
        local = ttk.Frame(add, style="Inner.TFrame")
        local.grid(row=0, column=0, sticky="ew")
        self.btn_add = ttk.Button(local, text="Adicionar arquivos…", command=self.add_files)
        self.btn_add.pack(side="left")
        self.btn_folder = ttk.Button(local, text="Adicionar pasta…", command=self.add_folder)
        self.btn_folder.pack(side="left", padx=8)
        self.recursive = tk.BooleanVar(value=False)
        self.chk_recursive = ttk.Checkbutton(local, text="Incluir subpastas", variable=self.recursive)
        self.chk_recursive.pack(side="left", padx=(4, 0))

        link = ttk.Frame(add, style="Inner.TFrame")
        link.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        link.columnconfigure(0, weight=1)
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(link, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self.url_entry.bind("<Return>", lambda _e: self.submit_url())
        self.url_entry.bind("<KP_Enter>", lambda _e: self.submit_url())
        # Dica dentro do campo vazio (rótulo sobreposto; url_var continua vazio).
        self.url_placeholder = ttk.Label(link, style="Placeholder.TLabel",
                                         text="…ou cole o link de um post/reel público do Instagram")
        self.url_placeholder.bind("<Button-1>", lambda _e: self.url_entry.focus_set())
        for ev in ("<FocusIn>", "<FocusOut>"):
            self.url_entry.bind(ev, lambda _e: self._sync_url_placeholder(), add="+")
        self.btn_link = ttk.Button(link, text="Baixar e extrair", style="Accent.TButton",
                                   command=self.submit_url)
        self.btn_link.grid(row=0, column=1, padx=(8, 0))
        self.url_var.trace_add("write", lambda *_: (self._refresh_buttons(),
                                                    self._sync_url_placeholder()))
        self.link_hint = ttk.Label(add, style="Muted.TLabel", wraplength=860, justify="left",
                                   text="Verificando o yt-dlp…")
        self.link_hint.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self._auto_wrap(self.link_hint)
        self._sync_url_placeholder()

        # 2. Destino
        out = self._card(outer, 3, "2", "Pasta de destino")
        self.out_picker = FolderPicker(out, "Salvar em", "Pasta de destino dos resultados",
                                       on_change=self._refresh_buttons)
        self.out_picker.grid(row=0, column=0, sticky="ew")
        dest_hint = ttk.Label(out, style="Muted.TLabel", wraplength=900, justify="left",
                  text="Pastas 001, 002, … com audio.mp3 (se houver som) · video.mp4 sem áudio · "
                       "frames/ (4 imagens). Nada é sobrescrito."
                  )
        dest_hint.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._auto_wrap(dest_hint)

        # 3. Fila
        q = self._card(outer, 4, "3", "Fila e andamento", expand=True)
        q.rowconfigure(0, weight=1)
        cols = ("status", "progress", "details", "folder")
        self.tree = ttk.Treeview(q, columns=cols, selectmode="extended", height=8,
                                 displaycolumns=("folder", "status", "progress", "details"))
        self.tree.heading("#0", text="ARQUIVO", anchor="w")
        self.tree.heading("folder", text="PASTA", anchor="w")
        self.tree.heading("status", text="STATUS", anchor="w")
        self.tree.heading("progress", text="%", anchor="e")
        self.tree.heading("details", text="DETALHES", anchor="w")
        self.tree.column("#0", width=260, minwidth=160, stretch=True)
        self.tree.column("folder", width=70, minwidth=60, stretch=False)
        self.tree.column("status", width=160, minwidth=120, stretch=False)
        self.tree.column("progress", width=60, minwidth=50, anchor="e", stretch=False)
        self.tree.column("details", width=360, minwidth=160, stretch=True)
        for tag, color in STATUS_COLORS.items():
            self.tree.tag_configure(tag, foreground=color)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(q, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Delete>", lambda _e: self.remove_selected())
        self.tree.bind("<Double-1>", self.show_item_details)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._refresh_buttons())
        self.empty_hint = ttk.Label(q, style="Muted.TLabel",
                                    text="A fila está vazia. Adicione arquivos, uma pasta ou um link acima.")
        self.empty_hint.grid(row=1, column=0, sticky="w", pady=(6, 0))

        # Ações da fila no cabeçalho do cartão (economiza uma linha para a lista).
        self.btn_clear = ttk.Button(q.header, text="Limpar fila", style="Ghost.TButton",
                                    command=self.clear_queue)
        self.btn_clear.pack(side="right")
        self.btn_remove = ttk.Button(q.header, text="Remover selecionados", style="Ghost.TButton",
                                     command=self.remove_selected)
        self.btn_remove.pack(side="right", padx=(0, 2))
        self.btn_open_item = ttk.Button(q.header, text="Abrir pasta do item",
                                        command=self.open_selected_folder)
        self.btn_open_item.pack(side="right", padx=(0, 6))

        run = ttk.Frame(q, style="Inner.TFrame")
        run.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        run.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(run, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 18))
        self.status = tk.StringVar(value="Pronto.")
        ttk.Label(run, textvariable=self.status, style="Status.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        self.btn_cancel = ttk.Button(run, text="Cancelar", style="Danger.TButton", command=self.cancel)
        self.btn_cancel.grid(row=0, column=1, rowspan=2, padx=(0, 8))
        self.btn_start = ttk.Button(run, text="▶  Iniciar fila", style="Accent.TButton",
                                    command=self.start)
        self.btn_start.grid(row=0, column=2, rowspan=2)
        self._indeterminate = False

    def _url_entry_focused(self) -> bool:
        # Consulta o foco direto no Tcl: focus_get() levanta KeyError quando o foco está num
        # widget puramente Tcl (ex.: diálogo nativo de pastas do Tk, "__tk_choosedir").
        try:
            return str(self.root.tk.call("focus")) == str(self.url_entry)
        except tk.TclError:
            return False

    def _sync_url_placeholder(self) -> None:
        focused = self._url_entry_focused()
        if self.url_var.get() or focused:
            self.url_placeholder.place_forget()
        else:
            self.url_placeholder.place(in_=self.url_entry, x=11, rely=0.5, anchor="w")

    # ------------------------------------------------------------ dependências
    def check_dependencies(self) -> None:
        try:
            st = engine.check_dependencies()
            ok, msg = bool(st.ok), st.message or ""
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, f"Falha ao verificar o FFmpeg: {exc}"
        self.deps_ok = ok
        if ok:
            self.dep_label.configure(text="")
            self.dep_retry.grid_remove()
            self.dep_frame.grid_remove()
            if self.job is None:
                self.status.set("Pronto. FFmpeg encontrado.")
        else:
            self.dep_label.configure(text="⚠ " + (msg or "FFmpeg/FFprobe não encontrados.")
                                     + "\nDepois de instalar, clique em “Verificar novamente”.")
            self.dep_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
            self.dep_retry.grid(row=0, column=1, padx=(10, 0), sticky="ne")
            self.status.set("FFmpeg não encontrado — instale-o para processar vídeos.")
        self._refresh_buttons()

    def check_downloader(self) -> None:
        """Verifica o yt-dlp numa thread (pode levar ~1 s) e atualiza a dica do link."""
        fn = getattr(engine, "check_downloader", None)
        if fn is None:
            self.events.put(("downloader", False, "Download por link não disponível nesta versão."))
            return

        def work():
            try:
                st = fn()
                self.events.put(("downloader", bool(st.ok), st.message or ""))
            except Exception as exc:  # noqa: BLE001
                self.events.put(("downloader", False, f"Falha ao verificar o yt-dlp: {exc}"))

        threading.Thread(target=work, daemon=True).start()

    def _set_downloader(self, ok: bool, message: str) -> None:
        self.downloader_ok = ok
        self.downloader_message = message
        if ok:
            self.link_hint.configure(
                style="Muted.TLabel",
                text="Baixa e entra na fila sozinho, com a mesma pasta de destino. "
                     "Só links públicos, sem login.")
        else:
            self.link_hint.configure(
                style="Warn.TLabel",
                text="⚠ Links indisponíveis: yt-dlp ausente ou com erro. Arquivos locais funcionam; "
                     "cole um link para ver detalhes.")
        self._refresh_buttons()

    # ------------------------------------------------------------------- fila
    def add_paths(self, paths) -> int:
        known = {os.path.normcase(str(i["path"].resolve()))
                 for i in self.items.values() if i.get("kind") == "local"}
        added = 0
        for p in paths:
            p = Path(p)
            key = os.path.normcase(str(p.resolve()))
            if key in known:
                continue
            known.add(key)
            iid = self.tree.insert("", "end", text=p.name, values=(ST_PENDING, "", str(p.parent), ""),
                                   tags=("pending",))
            self.items[iid] = {"kind": "local", "path": p, "status": None}
            added += 1
        self._refresh_buttons()
        return added

    def set_output_dir(self, dest=None) -> None:
        """Define a pasta de destino sem diálogo (útil para testes)."""
        self.out_picker.path.set(str(Path(dest)) if dest else "")
        self._refresh_buttons()

    def add_files(self) -> None:
        files = filedialog.askopenfilenames(
            parent=self.root, title="Selecione um ou mais vídeos",
            filetypes=[("Vídeos", VIDEO_PATTERNS), ("Todos os arquivos", "*")])
        if files:
            n = self.add_paths(files)
            self.status.set(f"{n} vídeo(s) adicionado(s). Clique em “Iniciar fila”."
                            if n else "Esses vídeos já estão na fila.")

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(parent=self.root, mustexist=True,
                                         title="Selecione a pasta com os vídeos")
        if not folder:
            return
        try:
            videos = engine.list_videos(folder, recursive=self.recursive.get())
        except engine.EngineError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        if not videos:
            messagebox.showinfo(APP_TITLE, f"Nenhum vídeo encontrado em:\n{folder}")
            return
        n = self.add_paths(videos)
        self.status.set(f"{n} vídeo(s) carregado(s) de {folder}"
                        + (f" ({len(videos) - n} já estavam na fila)." if n < len(videos) else ".")
                        + " Clique em “Iniciar fila”.")

    def _output_dir(self, problems: list) -> Path | None:
        dest = self.out_picker.value()
        if dest is None:
            problems.append("Escolha a pasta de destino (passo 2).")
        return dest

    def _check_output_writable(self, dest) -> str | None:
        prep = getattr(engine, "prepare_output_dir", None)
        if prep is None or dest is None:
            return None
        try:
            prep(dest)
        except engine.EngineError as exc:
            return str(exc)
        return None

    def submit_url(self) -> None:
        if self.add_url(self.url_var.get()):
            self.url_var.set("")

    def add_url(self, url: str) -> bool:
        """Valida link + pastas + dependências e coloca o link na fila (inicia sozinho)."""
        url = (url or "").strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "Cole o link de um post ou reel do Instagram.")
            return False
        validate = getattr(engine, "validate_instagram_url", None)
        try:
            norm = validate(url) if validate else url
        except engine.EngineError as exc:
            messagebox.showwarning(APP_TITLE, f"Link não aceito:\n{exc}")
            return False
        if not self.downloader_ok:
            fn = getattr(engine, "check_downloader", None)
            if fn is not None:  # pode ter sido instalado depois de abrir o programa
                try:
                    st = fn()
                    self._set_downloader(bool(st.ok), st.message or "")
                except Exception:  # noqa: BLE001
                    pass
            if not self.downloader_ok:
                messagebox.showerror(APP_TITLE, "Para baixar do Instagram é preciso instalar o yt-dlp.\n\n"
                                     + (self.downloader_message or "python3 -m pip install -U yt-dlp"))
                return False
        problems: list = []
        dest = self._output_dir(problems)
        if problems:
            messagebox.showwarning(APP_TITLE, "Antes de baixar:\n" + "\n".join(problems))
            return False
        err = self._check_output_writable(dest)
        if err:
            messagebox.showerror(APP_TITLE, err)
            return False
        if not self.deps_ok:
            self.check_dependencies()
            if not self.deps_ok:
                messagebox.showerror(APP_TITLE, self.dep_label.cget("text").lstrip("⚠ "))
                return False
        if any(i.get("kind") == "link" and i.get("url") == norm and i["status"] in BUSY_STATUSES
               for i in self.items.values()):
            messagebox.showinfo(APP_TITLE, "Esse link já está na fila.")
            return False

        iid = self.tree.insert("", "end", text="🔗 " + short_url(norm), open=True,
                               values=(ST_QUEUED, "", "Aguardando para baixar…", ""), tags=("pending",))
        self.items[iid] = {"kind": "link", "url": norm, "path": None, "status": "queued"}
        self.tree.see(iid)
        self.status.set("Link adicionado. O download começa assim que a fila estiver livre."
                        if self.job is not None else "Link adicionado. Iniciando download…")
        self._schedule()
        return True

    def remove_selected(self) -> None:
        if self._busy():
            return
        for iid in self.tree.selection():
            if self.tree.exists(iid):
                parent = self.tree.parent(iid)
                if parent:  # vídeo de um link: remove o link inteiro
                    iid = parent
                for child in self.tree.get_children(iid):
                    self.items.pop(child, None)
                self.tree.delete(iid)
                self.items.pop(iid, None)
        self._refresh_buttons()

    def clear_queue(self) -> None:
        if self._busy() or not self.items:
            return
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        self.progress["value"] = 0
        self.status.set("Fila limpa.")
        self._refresh_buttons()

    def show_item_details(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid or iid not in self.items:
            return
        item = self.items[iid]
        values = self.tree.item(iid, "values")
        origin = item.get("url") or item.get("path")
        lines = [f"{'Link' if item.get('kind') == 'link' else 'Arquivo'}: {origin}",
                 f"Status: {values[0]}"]
        if item.get("folder"):
            lines.append(f"Pasta: {item['folder']}")
        if values[2]:
            lines.append(f"Detalhes: {values[2]}")
        messagebox.showinfo(APP_TITLE, "\n".join(lines))

    # --------------------------------------------------------------- execução
    def _busy(self) -> bool:
        return self.job is not None or any(i["status"] in BUSY_STATUSES for i in self.items.values())

    def _startable(self) -> list[str]:
        """Itens de topo que 'Iniciar fila' colocaria para rodar."""
        return [iid for iid in self.tree.get_children()
                if self.items[iid]["status"] not in DONE_STATUSES | BUSY_STATUSES]

    def start(self) -> None:
        """Coloca na fila todos os itens não concluídos e começa (ou continua) o processamento."""
        if not self.deps_ok:
            self.check_dependencies()
            if not self.deps_ok:
                messagebox.showerror(APP_TITLE, self.dep_label.cget("text").lstrip("⚠ "))
                return
        problems: list = []
        dest = self._output_dir(problems)
        iids = self._startable()
        if not self.items:
            problems.append("Adicione vídeos à fila.")
        elif not iids:
            problems.append("Todos os vídeos da fila já foram concluídos ou estão em andamento. "
                            "Adicione novos vídeos ou limpe a fila.")
        if problems:
            messagebox.showwarning(APP_TITLE, "\n".join(problems))
            return
        err = self._check_output_writable(dest)
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        for iid in iids:
            item = self.items[iid]
            item["status"] = "queued"
            item["folder"] = None
            if item["kind"] == "link":
                for child in self.tree.get_children(iid):
                    self.items.pop(child, None)
                    self.tree.delete(child)
                self._set_row(iid, ST_QUEUED, "", "Aguardando para baixar…", ("pending",))
            else:
                self._set_row(iid, ST_QUEUED, "", "", ("pending",))
        self.session_problems = 0
        if self.job is None:
            self.progress["value"] = 0
        self._schedule()

    def _schedule(self) -> None:
        """Se nada estiver rodando, inicia o próximo trabalho da fila."""
        if self.job is not None or self.closing:
            self._refresh_buttons()
            return
        queued = [iid for iid in self.tree.get_children() if self.items[iid]["status"] == "queued"]
        if not queued:
            self._session_finished()
            return
        first = queued[0]
        dest = self.out_picker.value()
        self.job_token += 1
        token = self.job_token
        on_event = lambda ev, t=token: self.events.put(("engine", t, ev))  # noqa: E731
        try:
            if self.items[first]["kind"] == "link":
                job = engine.InstagramProcessor(self.items[first]["url"], dest,
                                                on_event=on_event)
                rows, kind = [first], "link"
            else:
                rows = [iid for iid in queued if self.items[iid]["kind"] == "local"]
                job = engine.BatchProcessor([self.items[i]["path"] for i in rows], dest,
                                            on_event=on_event)
                kind = "batch"
            job.start()
        except Exception as exc:  # noqa: BLE001 - nunca derrubar a janela
            text = str(exc) if isinstance(exc, engine.EngineError) else f"Não foi possível iniciar:\n{exc}"
            target = [first] if self.items[first]["kind"] == "link" else rows
            for iid in target:
                self.items[iid]["status"] = "failed"
                self._set_row(iid, ST_LABELS["failed"], "", text, ("error",))
            if isinstance(exc, getattr(engine, "DependencyMissingError", ())):
                self.check_dependencies()
                self.check_downloader()
            messagebox.showerror(APP_TITLE, text)
            self.root.after_idle(self._schedule)
            return

        self.job, self.job_kind = job, kind
        self.cancel_requested = False
        if kind == "link":
            self.link_iid, self.link_children, self.link_failed = first, {}, False
            self.items[first]["status"] = "running"
            self._set_row(first, "Baixando", "", "Conectando ao Instagram…", ("running",))
            self.status.set(f"Baixando {short_url(self.items[first]['url'])}…")
        else:
            self.job_rows = rows
            for iid in rows:
                self.items[iid]["status"] = "running"
                self._set_row(iid, ST_PENDING, "", "", ("pending",))
            self.status.set(f"Iniciando {len(rows)} vídeo(s)…")
        self._set_progress(0)
        self._refresh_buttons()

    def cancel(self) -> None:
        if not self._busy():
            return
        if not messagebox.askyesno(APP_TITLE, "Cancelar a fila? O item atual será interrompido "
                                              "e os próximos não serão processados."):
            return
        self.cancel_requested = True
        self.btn_cancel.configure(state="disabled")
        for iid, item in self.items.items():
            if item["status"] == "queued":
                item["status"] = "cancelled"
                if self.tree.exists(iid):
                    self._set_row(iid, ST_LABELS["cancelled"], "", "Cancelado antes de começar.",
                                  ("error",))
        if self.job is None:
            self._refresh_buttons()
            return
        self.status.set("Cancelando…")
        try:
            self.job.cancel()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"Falha ao cancelar: {exc}")

    # ------------------------------------------------------- eventos do motor
    def _poll_events(self) -> None:
        try:
            for _ in range(200):  # limita o trabalho por ciclo para manter a UI fluida
                msg = self.events.get_nowait()
                if msg[0] == "downloader":
                    self._set_downloader(msg[1], msg[2])
                elif msg[0] == "engine" and msg[1] == self.job_token and self.job is not None:
                    self._handle_event(msg[2])
        except queue.Empty:
            pass
        except Exception as exc:  # noqa: BLE001 - um evento ruim não pode parar o polling
            self.status.set(f"Erro interno ao atualizar a tela: {exc}")
        if self.closing and self.job is None:
            return  # janela já foi (ou está sendo) destruída
        self.root.after(POLL_MS, self._poll_events)

    def _set_progress(self, pct) -> None:
        if pct is None or pct < 0:
            if not self._indeterminate:
                self.progress.configure(mode="indeterminate")
                self.progress.start(15)
                self._indeterminate = True
            return
        if self._indeterminate:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self._indeterminate = False
        self.progress["value"] = max(0.0, min(100.0, float(pct)))

    def _row_for(self, ev) -> str | None:
        idx = getattr(ev, "index", None)
        if idx is None:
            return None
        if self.job_kind == "batch":
            if 0 <= idx < len(self.job_rows) and self.tree.exists(self.job_rows[idx]):
                return self.job_rows[idx]
            return None
        if self.link_iid is None or not self.tree.exists(self.link_iid):
            return None
        iid = self.link_children.get(idx)
        if iid is None:
            path = getattr(ev, "path", None)
            name = Path(path).name if path else f"vídeo {idx + 1}"
            iid = self.tree.insert(self.link_iid, "end", text=name, values=(ST_PENDING, "", "", ""),
                                   tags=("pending",))
            self.items[iid] = {"kind": "link_video", "path": Path(path) if path else None,
                               "status": "running", "parent": self.link_iid}
            self.link_children[idx] = iid
            self.tree.item(self.link_iid, open=True)
        return iid

    def _handle_event(self, ev) -> None:
        kind = getattr(ev, "kind", None)
        msg = getattr(ev, "message", "") or ""
        err = getattr(ev, "error", None)
        link = self.link_iid if self.job_kind == "link" else None

        if kind == "download_started" and link:
            self._set_row(link, "Baixando", "", msg or "Baixando do Instagram…", ("running",))
            self._set_progress(-1)
            self.status.set(msg or "Baixando do Instagram…")
            return
        if kind == "download_progress" and link:
            pct = getattr(ev, "percent", None)
            known = pct is not None and pct >= 0
            self._set_row(link, "Baixando", f"{pct:.0f}%" if known else "", msg, ("running",))
            self._set_progress(pct if known else -1)
            if msg:
                self.status.set(msg)
            return
        if kind == "download_finished" and link:
            self._set_row(link, "Extraindo", "", msg or "Download concluído.", ("running",))
            self._set_progress(0)
            self.status.set(msg or "Download concluído. Extraindo…")
            return
        if kind == "download_failed" and link:
            self.link_failed = True
            self.items[link]["status"] = "failed"
            self._set_row(link, ST_LABELS["failed"], "", err or msg or "Falha no download.", ("error",))
            self._set_progress(0)
            self.status.set(err or msg or "Falha no download.")
            return

        batch_pct = getattr(ev, "batch_percent", None)
        if batch_pct is not None and kind != "batch_finished":
            self._set_progress(batch_pct)

        iid = self._row_for(ev) if kind in ("file_started", "progress", "file_finished") else None
        folder = getattr(ev, "folder", None)
        if iid and folder and kind in ("file_started", "progress", "file_finished"):
            self.items[iid]["folder"] = Path(folder)
        if kind == "file_started" and iid:
            self._set_row(iid, ST_RUNNING, "0%", msg, ("running",))
            self.tree.see(iid)
            name = self.tree.item(iid, "text")
            self.status.set(f"Vídeo {ev.index + 1} de {ev.total}: {name}")
        elif kind == "progress" and iid:
            stage = getattr(ev, "stage", None) or ""
            pct = getattr(ev, "percent", None)
            self._set_row(iid, STAGE_LABELS.get(stage, ST_RUNNING),
                          f"{pct:.0f}%" if pct is not None and pct >= 0 else "", msg, ("running",))
        elif kind == "file_finished" and iid:
            self._apply_result(iid, getattr(ev, "result", None), msg)
        elif kind == "batch_finished":
            self._finish_job(getattr(ev, "results", None) or [], msg)
        elif msg:
            self.status.set(msg)

    def _apply_result(self, iid: str, result, msg: str) -> None:
        if result is None:
            return
        status = result.status
        self.items[iid]["status"] = status
        folder = getattr(result, "folder", None)
        self.items[iid]["folder"] = Path(folder) if folder else None
        made = []
        if getattr(result, "mp3_path", None):
            made.append("audio.mp3")
        if getattr(result, "mp4_path", None):
            made.append("video.mp4")
        frames = list(getattr(result, "frames", None) or getattr(result, "frame_paths", None) or [])
        if frames:
            made.append(f"{len(frames)} frames")
        parts = []
        if made and folder:
            parts.append(f"{Path(folder).name}/: " + ", ".join(made))
        if status == "no_audio":
            parts.append("Vídeo sem áudio: audio.mp3 não foi criado.")
        if result.error:
            parts.append(str(result.error))
        parts.extend(str(w) for w in (result.warnings or [])
                     if not (status == "no_audio" and "áudio" in str(w)))
        if status == "no_audio" and self.items[iid].get("kind") == "link_video":
            parts.append("O Instagram costuma enviar alguns vídeos sem áudio para acesso sem login.")
        pct = "100%" if status in DONE_STATUSES or status == "partial" else ""
        self._set_row(iid, ST_LABELS.get(status, status), pct, " | ".join(parts) or msg,
                      (STATUS_TAG.get(status, "error"),))

    def _finish_job(self, results, msg: str) -> None:
        if results and not self.cancel_requested:
            self._set_progress(100)
        elif self._indeterminate:
            self._set_progress(0)
        fallback = "cancelled" if self.cancel_requested else "failed"
        if self.job_kind == "batch":
            for iid in self.job_rows:
                if self.tree.exists(iid) and self.items[iid]["status"] in BUSY_STATUSES | {None}:
                    self.items[iid]["status"] = fallback
                    self._set_row(iid, ST_LABELS[fallback], "", "", ("error",))
            touched = [self.items[i]["status"] for i in self.job_rows if i in self.items]
        else:
            link = self.link_iid
            for iid in self.link_children.values():
                if self.items.get(iid, {}).get("status") in BUSY_STATUSES | {None}:
                    self.items[iid]["status"] = fallback
                    self._set_row(iid, ST_LABELS[fallback], "", "", ("error",))
            child_st = [self.items[i]["status"] for i in self.link_children.values() if i in self.items]
            if link and self.tree.exists(link) and not self.link_failed:
                if self.cancel_requested and not all(s in DONE_STATUSES for s in child_st or ["x"]):
                    final = "cancelled"
                elif not child_st:
                    final = "failed"
                elif all(s in DONE_STATUSES for s in child_st):
                    final = "success" if "no_audio" not in child_st else "no_audio"
                elif any(s in DONE_STATUSES or s == "partial" for s in child_st):
                    final = "partial"
                else:
                    final = "failed"
                self.items[link]["status"] = final
                n = len(child_st)
                detail = {"cancelled": "Cancelado.", "failed": "Nenhum vídeo foi gerado."}.get(
                    final, f"{n} vídeo(s) do link processado(s); detalhes nas linhas abaixo.")
                self._set_row(link, ST_LABELS[final], "100%" if final in DONE_STATUSES else "",
                              detail, (STATUS_TAG.get(final, "error"),))
            touched = [self.items[link]["status"]] if link in self.items else []
        self.session_problems += sum(1 for s in touched if s in ("failed", "partial"))

        self.job, self.job_kind = None, None
        self.job_rows, self.link_iid, self.link_children = [], None, {}
        if msg:
            self.status.set(msg)
        if self.closing:
            self.root.destroy()
            return
        if self.cancel_requested:
            self.cancel_requested = False
            self._session_finished(cancelled=True)
            return
        self._schedule()

    def _session_finished(self, cancelled: bool = False) -> None:
        """Nada mais na fila de execução: resume e avisa sobre falhas."""
        self._refresh_buttons()
        if self._indeterminate:
            self._set_progress(0)
        counts: dict[str, int] = {}
        for iid, item in self.items.items():
            if self.tree.parent(iid) and self.items.get(self.tree.parent(iid), {}).get("kind") == "link":
                continue  # conta o link uma vez (linha-pai)
            st = item["status"]
            if st:
                counts[st] = counts.get(st, 0) + 1
        if not counts:
            return
        summary = "Fila finalizada: " + ", ".join(f"{ST_LABELS.get(k, k).lower()}: {v}"
                                                  for k, v in counts.items()) + "."
        if cancelled:
            summary = "Fila cancelada. " + summary
        self.status.set(summary)
        if self.session_problems and not self.closing:
            self.session_problems = 0
            messagebox.showwarning(APP_TITLE, f"{summary}\n\nDê dois cliques em uma linha para ver "
                                              "os detalhes. Clique em “Iniciar fila” para tentar "
                                              "novamente os que não foram concluídos.")

    def _folder_label(self, iid: str) -> str:
        item = self.items.get(iid, {})
        if item.get("kind") == "link":
            names = sorted(self.items[c]["folder"].name for c in self.tree.get_children(iid)
                           if self.items.get(c, {}).get("folder"))
            if not names:
                return ""
            return names[0] if len(names) == 1 else f"{names[0]}–{names[-1]}"
        folder = item.get("folder")
        return folder.name if folder else ""

    def _set_row(self, iid: str, status: str, pct: str, detail: str, tags) -> None:
        self.tree.item(iid, values=(status, pct, detail, self._folder_label(iid)), tags=tags)
        parent = self.tree.parent(iid)
        if parent and parent in self.items:  # mantém a faixa de pastas do link atualizada
            vals = list(self.tree.item(parent, "values"))
            if len(vals) == 4:
                vals[3] = self._folder_label(parent)
                self.tree.item(parent, values=vals)

    def _selected_folder(self) -> Path | None:
        """Pasta numerada do item selecionado (ou do 1º vídeo de um link), se existir."""
        sel = self.tree.selection()
        if len(sel) != 1 or sel[0] not in self.items:
            return None
        iid = sel[0]
        folder = self.items[iid].get("folder")
        if folder is None and self.items[iid].get("kind") == "link":
            kids = [self.items[c].get("folder") for c in self.tree.get_children(iid)]
            folder = next((f for f in kids if f), None)
            if folder is not None and len([k for k in kids if k]) > 1:
                folder = folder.parent  # carrossel: abre o destino, onde estão todas as pastas
        return folder if folder is not None and folder.is_dir() else None

    def open_selected_folder(self) -> None:
        folder = self._selected_folder()
        if folder is None:
            messagebox.showinfo(APP_TITLE, "Selecione um item já processado para abrir a pasta dele.")
            return
        open_in_file_manager(folder)

    # ------------------------------------------------------------- utilidades
    def _refresh_buttons(self) -> None:
        busy = self._busy()
        self.btn_add.configure(state="normal")
        self.btn_folder.configure(state="normal")
        self.chk_recursive.configure(state="normal")
        for w in (self.btn_remove, self.btn_clear):
            w.configure(state="disabled" if busy or not self.items else "normal")
        self.out_picker.set_locked(busy)
        self.btn_open_item.configure(state="normal" if self._selected_folder() else "disabled")
        self.btn_start.configure(state="normal" if self._startable() else "disabled")
        self.btn_cancel.configure(state="normal" if busy and not self.cancel_requested else "disabled")
        self.btn_link.configure(state="normal" if self.url_var.get().strip() else "disabled")
        if self.items:
            self.empty_hint.grid_remove()
        else:
            self.empty_hint.grid()

    def on_close(self) -> None:
        if not self._busy():
            self.root.destroy()
            return
        if not messagebox.askyesno(APP_TITLE, "Há uma fila em andamento. Cancelar e sair?"):
            return
        self.closing = True
        self.cancel_requested = True
        self.status.set("Cancelando e saindo…")
        if self.job is None:
            self.root.destroy()
            return
        try:
            self.job.cancel()
        except Exception:  # noqa: BLE001
            self.root.destroy()
            return
        # _finish_job fecha a janela ao receber batch_finished; garante saída em 10 s.
        self.root.after(10000, self.root.destroy)


def run() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
