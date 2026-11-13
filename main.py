#!/usr/bin/env python3
"""Ponto de entrada do Extrator de Vídeos (interface gráfica).

Uso:  python3 main.py      (Windows: py main.py)
"""

import sys

if sys.version_info < (3, 8):
    sys.exit("Este programa precisa do Python 3.8 ou mais recente.")

try:
    import tkinter  # noqa: F401
except ImportError:
    sys.exit(
        "O Tkinter (interface gráfica do Python) não está instalado.\n"
        "  Debian/Ubuntu: sudo apt install python3-tk\n"
        "  Fedora:        sudo dnf install python3-tkinter\n"
        "  Arch:          sudo pacman -S tk\n"
        "  macOS (Homebrew): brew install python-tk\n"
        "  Windows: reinstale o Python marcando a opção 'tcl/tk and IDLE'."
    )


def main() -> None:
    try:
        from extractor.ui import run
        run()
    except tkinter.TclError as exc:
        sys.exit(f"Não foi possível abrir a janela (há uma tela gráfica disponível?): {exc}")


if __name__ == "__main__":
    main()
