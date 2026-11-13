"""Helpers de QA: geração de vídeos sintéticos reais via ffmpeg e inspeção via ffprobe.

Nada aqui é mock: os fixtures são mídias reais produzidas pelo ffmpeg do sistema.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
HAVE_FFMPEG = bool(FFMPEG and FFPROBE)

DURATION = 2.0          # segundos dos vídeos sintéticos
DURATION_TOL = 0.30     # tolerância (MP3 tem padding de encoder; copy de GOP)


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"fixture ffmpeg falhou: {' '.join(args)}\n{proc.stderr[-2000:]}")


def make_video(path: Path, *, audio: bool = True, video: bool = True,
               vcodec: str = "libx264", acodec: str = "aac",
               duration: float = DURATION, size: str = "160x120") -> Path:
    """Gera mídia sintética real (testsrc + sine)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    args = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    if video:
        args += ["-f", "lavfi", "-i", f"testsrc=size={size}:rate=25:duration={duration}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:duration={duration}"]
    if video:
        args += ["-c:v", vcodec]
        if vcodec == "libx264":
            args += ["-pix_fmt", "yuv420p", "-preset", "ultrafast"]
        if vcodec.startswith("libvpx"):
            args += ["-deadline", "realtime", "-b:v", "200k"]
    if audio:
        args += ["-c:a", acodec]
    args += ["-t", str(duration), str(path)]
    _run(args)
    return path


def make_invalid(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"isto nao e um video\x00\x01\x02" * 100)
    return path


def make_truncated(src: Path, dst: Path) -> Path:
    """Cópia truncada (cabeçalho só) de um vídeo real -> mídia corrompida."""
    data = Path(src).read_bytes()
    Path(dst).write_bytes(data[: max(64, len(data) // 20)])
    return Path(dst)


def probe(path: Path) -> dict:
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"ffprobe não conseguiu ler {path}: {proc.stderr}")
    return json.loads(proc.stdout)


def streams(path: Path, kind: str) -> list[dict]:
    return [s for s in probe(path).get("streams", []) if s.get("codec_type") == kind]


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def decodes_cleanly(path: Path) -> bool:
    """Decodifica o arquivo inteiro; falso se ffmpeg reportar erro."""
    proc = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-f", "null", "-"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode == 0 and not proc.stderr.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(folder: Path) -> dict[str, tuple[str, float]]:
    """Mapa nome -> (sha256, mtime) de todos os arquivos de uma pasta."""
    return {p.name: (sha256(p), p.stat().st_mtime) for p in sorted(Path(folder).iterdir()) if p.is_file()}


def leftover_temp_files(*folders: Path) -> list[Path]:
    out = []
    for f in folders:
        for p in Path(f).iterdir():
            if p.name.endswith(".part") or p.name.startswith(".") and p.is_file():
                out.append(p)
    return out


def fake_bin_dir(base: Path) -> Path:
    """Diretório com PATH 'vazio' (sem ffmpeg/ffprobe)."""
    d = Path(base) / "empty_path"
    d.mkdir(parents=True, exist_ok=True)
    return d


ENGINE_ENV_KEYS = ("VIDEO_EXTRACTOR_FFMPEG", "VIDEO_EXTRACTOR_FFPROBE")


class EnvPatch:
    """Context manager para alterar variáveis de ambiente de forma reversível."""

    def __init__(self, **values):
        self.values = values
        self.saved = {}

    def __enter__(self):
        for k, v in self.values.items():
            self.saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---- V3: frames JPG ----------------------------------------------------------------
def jpeg_info(path: Path) -> tuple[str, int, int]:
    """(format, largura, altura) via ffprobe (independe do PIL)."""
    s = streams(path, "video")
    assert len(s) == 1, f"JPG sem stream de imagem: {path}"
    return s[0]["codec_name"], int(s[0]["width"]), int(s[0]["height"])


def video_size(path: Path) -> tuple[int, int]:
    s = streams(path, "video")[0]
    return int(s["width"]), int(s["height"])


def reference_frame_png(src: Path, t: float, dst: Path) -> Path:
    """Extrai, com ffmpeg, o quadro do vídeo de origem no instante t (seek preciso)."""
    _run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-ss", f"{t:.3f}",
          "-frames:v", "1", str(dst)])
    return Path(dst)


def image_distance(a: Path, b: Path) -> float:
    """Diferença média absoluta por pixel (0..255) entre duas imagens (PIL)."""
    from PIL import Image, ImageChops, ImageStat
    ia = Image.open(a).convert("L")
    ib = Image.open(b).convert("L").resize(ia.size)
    return sum(ImageStat.Stat(ImageChops.difference(ia, ib)).mean)
