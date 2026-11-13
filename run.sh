#!/bin/sh
# Inicia o Extrator de Vídeos no Linux/macOS (usa .venv, se existir, para ter o yt-dlp).
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python main.py "$@"
fi
exec python3 main.py "$@"
