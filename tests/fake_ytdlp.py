#!/usr/bin/env python3
"""yt-dlp CONTROLADO para testes (fronteira de rede simulada).

Imita o CLI do yt-dlp no contrato descrito em docs/backend.md: lê -P <dir>, -o, a URL após
'--', imprime progresso 'VXPROG ...' e 'VXFILE <caminho>' no stdout e mensagens 'ERROR:' reais
do yt-dlp no stderr. Os "downloads" são vídeos REAIS gerados por ffmpeg (lavfi), então a
extração que vem depois é 100 % real.

Controle por variáveis de ambiente:
  FAKE_YTDLP_MODE   ok | carousel | images_only | private | login | network | not_found |
                    rate_limit | unsupported | unknown | slow | partial_then_fail |
                    ok_without_vxfile | escape_path | linger | no_audio
  FAKE_YTDLP_LOG    arquivo onde cada execução grava uma linha JSON com argv/cwd/pid
  FAKE_YTDLP_MARKER arquivo tocado (com time.time()) imediatamente antes do processo sair
  FAKE_YTDLP_DURATION duração do vídeo gerado (s, padrão 2)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ERRORS = {
    "private": "ERROR: [Instagram] {id}: This content isn't available because the account is private",
    "login": "ERROR: [Instagram] {id}: Requested content is not available, rate-limit reached or login required. Use --cookies, --cookies-from-browser, --username and --password, --netrc-cmd, or --netrc (instagram) to provide account credentials",
    "network": "ERROR: [Instagram] {id}: Unable to download webpage: <urlopen error [Errno -3] Temporary failure in name resolution> (caused by TransportError('<urlopen error [Errno -3] Temporary failure in name resolution>'))",
    "not_found": "ERROR: [Instagram] {id}: HTTP Error 404: Not Found",
    "rate_limit": "ERROR: [Instagram] {id}: HTTP Error 429: Too Many Requests",
    "unsupported": "ERROR: Unsupported URL: {url}",
    "unknown": "ERROR: [Instagram] {id}: algo inesperado aconteceu xyz",
    "images_only": "ERROR: [Instagram] {id}: There is no video in this post",
}


def log(argv):
    path = os.environ.get("FAKE_YTDLP_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "pid": os.getpid(),
                                 "t": time.time()}, ensure_ascii=False) + "\n")


def finish(code: int) -> None:
    marker = os.environ.get("FAKE_YTDLP_MARKER")
    if marker:
        Path(marker).write_text(repr(time.time()))
    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(code)


def make_video(dst: Path, audio: bool = True) -> None:
    dur = os.environ.get("FAKE_YTDLP_DURATION", "2")
    ffmpeg = shutil.which("ffmpeg")
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size=160x120:rate=25:duration={dur}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=330:duration={dur}"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast"]
    if audio:
        args += ["-c:a", "aac"]
    args += ["-t", dur, str(dst)]
    subprocess.run(args, check=True)


def progress(n=3, idx="NA", total="NA", delay=0.0):
    size = 1_000_000
    for i in range(1, n + 1):
        print(f"VXPROG {size * i // n} {size} NA {idx} {total}", flush=True)
        if delay:
            time.sleep(delay)


def main() -> None:
    argv = sys.argv[1:]
    log(argv)
    if argv == ["--version"]:
        print("2099.01.01-fake")
        finish(0)

    mode = os.environ.get("FAKE_YTDLP_MODE", "ok")
    if "--" not in argv:
        print("ERROR: fake: '--' ausente antes da URL", file=sys.stderr)
        finish(2)
    url = argv[argv.index("--") + 1]
    outdir = Path(argv[argv.index("-P") + 1]) if "-P" in argv else Path.cwd()
    shortcode = url.rstrip("/").rsplit("/", 1)[-1]

    if mode in ERRORS:
        progress(1)
        if mode == "images_only":
            print(f"WARNING: [Instagram] {shortcode}: There is no video in this post", file=sys.stderr)
        print(ERRORS[mode].format(id=shortcode, url=url), file=sys.stderr)
        finish(1)

    if mode == "ok_without_vxfile":
        progress(2)
        finish(0)

    if mode == "slow":
        part = outdir / f"{shortcode}.mp4.part"
        part.write_bytes(b"\0" * 1024)
        for i in range(600):
            print(f"VXPROG {i * 1000} NA 600000 NA NA", flush=True)
            time.sleep(0.1)
        finish(0)

    if mode == "partial_then_fail":
        dst = outdir / f"{shortcode}.mp4"
        make_video(dst)
        (outdir / f"{shortcode}.f2.mp4.part").write_bytes(b"\0" * 2048)
        print(f"VXFILE {dst}", flush=True)
        print(f"ERROR: [Instagram] {shortcode}: Unable to download webpage: <urlopen error timed out>",
              file=sys.stderr)
        finish(1)

    if mode == "escape_path":
        evil = outdir.parent / f"fora_do_temp_{shortcode}.mp4"
        make_video(evil)
        print(f"VXFILE {evil}", flush=True)
        finish(0)

    if mode == "carousel":
        files = []
        for idx in (1, 2):
            progress(2, idx, 3)
            dst = outdir / f"{shortcode}_{idx}.mp4"
            make_video(dst)
            files.append(dst)
            print(f"VXFILE {dst}", flush=True)
        print(f"WARNING: [Instagram] {shortcode}: No video formats found!", file=sys.stderr)
        finish(0)

    # ok / linger / no_audio
    progress(3)
    dst = outdir / f"{shortcode}.mp4"
    tmp = outdir / f"{shortcode}.mp4.part"
    make_video(tmp.with_suffix(".tmp.mp4"), audio=(mode != "no_audio"))
    os.replace(tmp.with_suffix(".tmp.mp4"), dst)
    print(f"VXFILE {dst}", flush=True)
    if mode == "linger":
        time.sleep(1.5)   # arquivo já publicado, mas o processo ainda não terminou
    finish(0)


if __name__ == "__main__":
    main()
