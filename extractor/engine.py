"""Motor de extração: gera MP3 (áudio) e MP4 sem áudio a partir de vídeos.

Somente biblioteca padrão + binários ``ffmpeg``/``ffprobe``. Não importa tkinter.
Contrato documentado em ``docs/backend.md``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import random
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence, Union

PathLike = Union[str, os.PathLike]

VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v",
        ".mpg", ".mpeg", ".ts", ".3gp", ".mts", ".m2ts",
    }
)

ENV_FFMPEG = "VIDEO_EXTRACTOR_FFMPEG"
ENV_FFPROBE = "VIDEO_EXTRACTOR_FFPROBE"

STATUS_SUCCESS = "success"
STATUS_NO_AUDIO = "no_audio"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

_PART_SUFFIX = ".part"
_NUM_DIR_RE = re.compile(r"^\d+$")
AUDIO_NAME = "audio.mp3"
VIDEO_NAME = "video.mp4"
FRAMES_DIRNAME = "frames"
FRAME_COUNT = 4
_STDERR_TAIL = 40
_CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


# --------------------------------------------------------------------------- erros


class EngineError(Exception):
    """Base de todos os erros do motor. ``str(e)`` é uma mensagem em PT-BR."""


class DependencyMissingError(EngineError):
    """ffmpeg/ffprobe ausente ou inutilizável."""


FFmpegNotFoundError = DependencyMissingError  # nome alternativo


class InvalidInputError(EngineError):
    """Entrada inválida: pasta/arquivo inexistente, pasta não gravável, etc."""


class ExtractionError(EngineError):
    """Falha ao executar o ffmpeg para uma saída."""


class CancelledError(EngineError):
    """Processamento cancelado pelo usuário."""


# --------------------------------------------------------------------------- tipos


@dataclass
class DependencyStatus:
    ok: bool
    ffmpeg_path: Optional[str]
    ffprobe_path: Optional[str]
    message: str


@dataclass
class MediaInfo:
    duration: Optional[float]
    has_video: bool
    has_audio: bool
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    pix_fmt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    video_index: Optional[int] = None
    audio_index: Optional[int] = None
    video_duration: Optional[float] = None  # duração do stream de vídeo (s), se informada
    fps: Optional[float] = None


@dataclass
class VideoResult:
    source: Path
    status: str
    folder: Optional[Path] = None  # pasta numerada da entrega (NNN) ou None se nada foi entregue
    audio_path: Optional[Path] = None  # NNN/audio.mp3
    video_path: Optional[Path] = None  # NNN/video.mp4 (sem áudio)
    frame_paths: list = field(default_factory=list)  # NNN/frames/frame_01.jpg..frame_04.jpg
    frame_times: list = field(default_factory=list)  # instantes (s) na mesma ordem, crescentes
    warnings: list = field(default_factory=list)
    error: Optional[str] = None
    video_mode: Optional[str] = None  # "copy" | "reencode" | "reencode-mpeg4" | None

    # aliases de compatibilidade
    @property
    def mp3_path(self) -> Optional[Path]:
        return self.audio_path

    @property
    def mp4_path(self) -> Optional[Path]:
        return self.video_path

    @property
    def frames(self) -> list:
        return self.frame_paths

    @property
    def ok(self) -> bool:
        return self.status in (STATUS_SUCCESS, STATUS_NO_AUDIO)

    def summary(self) -> str:
        name = self.source.name
        where = f" -> {self.folder.name}" if self.folder is not None else ""
        if self.status == STATUS_SUCCESS:
            return f"{name}{where}: concluído (áudio, vídeo sem áudio e 4 frames)."
        if self.status == STATUS_NO_AUDIO:
            return f"{name}{where}: concluído (vídeo sem áudio; audio.mp3 não gerado)."
        if self.status == STATUS_PARTIAL:
            return f"{name}{where}: concluído parcialmente — {self.error}"
        if self.status == STATUS_CANCELLED:
            return f"{name}: cancelado."
        return f"{name}: falhou — {self.error}"


@dataclass
class Event:
    # batch_started | file_started | progress | file_finished | batch_finished
    # (Instagram) download_started | download_progress | download_finished | download_failed
    kind: str
    index: int
    total: int
    path: Optional[Path] = None
    stage: Optional[str] = None  # audio | video | frames | download
    percent: float = 0.0  # 0-100 do arquivo atual
    batch_percent: float = 0.0  # 0-100 da fila
    message: str = ""
    result: Optional[VideoResult] = None
    results: Optional[list] = None
    error: Optional[str] = None  # preenchido em download_failed
    folder: Optional[Path] = None  # pasta NNN do item (file_started/progress/file_finished)


ProgressCallback = Callable[[str, float], None]
EventCallback = Callable[[Event], None]


# --------------------------------------------------------------------------- dependências


def _install_hint() -> str:
    system = platform.system()
    if system == "Windows":
        return (
            "Instale o FFmpeg com: winget install Gyan.FFmpeg  (ou: choco install ffmpeg) "
            "e reabra o aplicativo para que o PATH seja atualizado."
        )
    if system == "Darwin":
        return "Instale o FFmpeg com: brew install ffmpeg"
    return (
        "Instale o FFmpeg com o gerenciador do seu sistema, por exemplo: "
        "sudo apt install ffmpeg  |  sudo dnf install ffmpeg  |  sudo pacman -S ffmpeg"
    )


def _resolve_tool(name: str, override: Optional[PathLike], env_var: str) -> Optional[str]:
    candidate = override if override is not None else os.environ.get(env_var) or None
    if candidate is not None:
        candidate = os.fspath(candidate)
        if os.path.sep in candidate or (os.altsep and os.altsep in candidate):
            return candidate if os.path.isfile(candidate) and os.access(candidate, os.X_OK) else None
        return shutil.which(candidate)
    return shutil.which(name)


def _tool_runs(path: str) -> bool:
    try:
        proc = subprocess.run(
            [path, "-version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            creationflags=_CREATIONFLAGS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def check_dependencies(ffmpeg: Optional[PathLike] = None, ffprobe: Optional[PathLike] = None) -> DependencyStatus:
    """Verifica ffmpeg/ffprobe. Nunca levanta exceção."""
    ff = _resolve_tool("ffmpeg", ffmpeg, ENV_FFMPEG)
    fp = _resolve_tool("ffprobe", ffprobe, ENV_FFPROBE)
    missing = []
    if ff is None or not _tool_runs(ff):
        missing.append("ffmpeg")
        ff = None
    if fp is None or not _tool_runs(fp):
        missing.append("ffprobe")
        fp = None
    if missing:
        msg = f"{' e '.join(missing)} não encontrado(s) ou não executável(is). {_install_hint()}"
        return DependencyStatus(False, ff, fp, msg)
    return DependencyStatus(True, ff, fp, "ffmpeg e ffprobe encontrados.")


def _require_tools(ffmpeg: Optional[PathLike], ffprobe: Optional[PathLike]) -> tuple:
    status = check_dependencies(ffmpeg, ffprobe)
    if not status.ok:
        raise DependencyMissingError(status.message)
    return status.ffmpeg_path, status.ffprobe_path


def check_ffmpeg(ffmpeg: Optional[PathLike] = None, ffprobe: Optional[PathLike] = None) -> None:
    """Levanta DependencyMissingError se ffmpeg/ffprobe estiverem ausentes."""
    _require_tools(ffmpeg, ffprobe)


_encoders_cache: dict = {}


def _available_encoders(ffmpeg: str) -> frozenset:
    if ffmpeg in _encoders_cache:
        return _encoders_cache[ffmpeg]
    names = set()
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=_CREATIONFLAGS,
        )
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
                names.add(parts[1])
    except (OSError, subprocess.SubprocessError):
        pass
    result = frozenset(names)
    _encoders_cache[ffmpeg] = result
    return result


# --------------------------------------------------------------------------- listagem / probe


def _inside_output_folder(root: Path, rel_parts: tuple) -> bool:
    """True se o caminho está dentro de uma pasta de entrega (``NNN`` com ``frames/``)."""
    cur = root
    for part in rel_parts[:-1]:
        cur = cur / part
        if _NUM_DIR_RE.match(part) and (cur / FRAMES_DIRNAME).is_dir():
            return True
    return False


def list_videos(folder: PathLike, recursive: bool = False) -> list:
    """Lista vídeos de uma pasta (ordenados por nome, sem ocultos nem ``*.part``)."""
    root = Path(folder).expanduser()
    if not root.exists():
        raise InvalidInputError(f"A pasta não existe: {root}")
    if not root.is_dir():
        raise InvalidInputError(f"O caminho não é uma pasta: {root}")
    try:
        iterator = root.rglob("*") if recursive else root.iterdir()
        found = []
        for p in iterator:
            rel_parts = p.relative_to(root).parts
            if any(part.startswith(".") for part in rel_parts):
                continue
            if recursive and _inside_output_folder(root, rel_parts):
                continue
            if p.name.lower().endswith(_PART_SUFFIX):
                continue
            if p.suffix.lower() in VIDEO_EXTENSIONS and p.is_file():
                found.append(p.resolve())
    except PermissionError as exc:
        raise InvalidInputError(f"Sem permissão para ler a pasta: {root} ({exc.strerror})") from exc
    except OSError as exc:
        raise InvalidInputError(f"Não foi possível ler a pasta: {root} ({exc.strerror or exc})") from exc
    return sorted(found, key=lambda p: (str(p.parent).casefold(), p.name.casefold(), p.name))


def _pos_float(value) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 and v == v and v != float("inf") else None


def _rate(value) -> Optional[float]:
    if not value or not isinstance(value, str):
        return None
    try:
        if "/" in value:
            num, den = value.split("/", 1)
            num_f, den_f = float(num), float(den)
            return num_f / den_f if num_f > 0 and den_f > 0 else None
        return _pos_float(value)
    except (TypeError, ValueError):
        return None


def probe(path: PathLike, ffprobe: Optional[PathLike] = None) -> MediaInfo:
    """Lê informações de mídia. Levanta InvalidInputError se não for mídia válida."""
    src = Path(path)
    fp = _resolve_tool("ffprobe", ffprobe, ENV_FFPROBE)
    if fp is None:
        raise DependencyMissingError(f"ffprobe não encontrado. {_install_hint()}")
    if not src.is_file():
        raise InvalidInputError(f"Arquivo não encontrado: {src}")
    try:
        proc = subprocess.run(
            [fp, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", "--", os.fspath(src)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            creationflags=_CREATIONFLAGS,
        )
    except subprocess.TimeoutExpired as exc:
        raise InvalidInputError(f"Tempo esgotado ao analisar o arquivo: {src.name}") from exc
    except OSError as exc:
        raise DependencyMissingError(f"Não foi possível executar o ffprobe: {exc}") from exc
    if proc.returncode != 0:
        detail = _last_lines(proc.stderr.replace(os.fspath(src), src.name), 2)
        raise InvalidInputError(f"Arquivo inválido ou corrompido: {src.name}" + (f" ({detail})" if detail else ""))
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise InvalidInputError(f"Não foi possível interpretar a análise do arquivo: {src.name}") from exc

    info = MediaInfo(duration=None, has_video=False, has_audio=False)
    for stream in data.get("streams", []):
        ctype = stream.get("codec_type")
        if ctype == "video" and not info.has_video:
            if (stream.get("disposition") or {}).get("attached_pic"):
                continue  # capa de álbum, não é vídeo
            info.has_video = True
            info.video_index = stream.get("index")
            info.video_codec = stream.get("codec_name")
            info.pix_fmt = stream.get("pix_fmt")
            info.width = stream.get("width")
            info.height = stream.get("height")
            info.video_duration = _pos_float(stream.get("duration"))
            info.fps = _rate(stream.get("avg_frame_rate")) or _rate(stream.get("r_frame_rate"))
        elif ctype == "audio" and not info.has_audio:
            info.has_audio = True
            info.audio_index = stream.get("index")
            info.audio_codec = stream.get("codec_name")
    duration = (data.get("format") or {}).get("duration")
    try:
        info.duration = float(duration) if duration not in (None, "N/A") else None
        if info.duration is not None and info.duration <= 0:
            info.duration = None
    except (TypeError, ValueError):
        info.duration = None
    return info


# --------------------------------------------------------------------------- utilidades de arquivo


def _last_lines(text: str, n: int = 3) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return " | ".join(lines[-n:])


def prepare_output_dir(folder: PathLike) -> Path:
    """Cria a pasta de saída se necessário e garante que é gravável."""
    d = Path(folder).expanduser()
    if d.exists() and not d.is_dir():
        raise InvalidInputError(f"O destino não é uma pasta: {d}")
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InvalidInputError(f"Não foi possível criar a pasta de saída: {d} ({exc.strerror or exc})") from exc
    try:
        with tempfile.NamedTemporaryFile(dir=d, prefix=".write-test-", suffix=_PART_SUFFIX):
            pass
    except OSError as exc:
        raise InvalidInputError(f"Sem permissão de escrita na pasta de saída: {d} ({exc.strerror or exc})") from exc
    return d.resolve()


def _temp_path(dest_dir: Path, stem: str, ext: str) -> Path:
    short = stem[:80]
    return dest_dir / f".{short}.{secrets.token_hex(4)}{ext}{_PART_SUFFIX}"


def _safe_unlink(p: Optional[Path]) -> None:
    if p is None:
        return
    try:
        p.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def unique_path(dest_dir: Path, stem: str, ext: str) -> Path:
    """Primeiro nome livre: ``stem.ext``, ``stem (1).ext``, ``stem (2).ext``... (sem reservar)."""
    n = 0
    while True:
        name = f"{stem}{ext}" if n == 0 else f"{stem} ({n}){ext}"
        candidate = dest_dir / name
        if not os.path.lexists(candidate):
            return candidate
        n += 1


def _publish(tmp: Path, dest_dir: Path, stem: str, ext: str) -> Path:
    """Move ``tmp`` para um nome único sem jamais sobrescrever arquivo existente.

    Reserva o nome com O_EXCL (atômico) e então substitui a reserva vazia pelo temporário.
    """
    n = 0
    while n < 100000:
        name = f"{stem}{ext}" if n == 0 else f"{stem} ({n}){ext}"
        candidate = dest_dir / name
        n += 1
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            continue
        except IsADirectoryError:
            continue
        os.close(fd)
        try:
            os.replace(tmp, candidate)
        except OSError:
            _safe_unlink(candidate)
            raise
        return candidate
    raise ExtractionError(f"Não foi possível encontrar um nome livre para {stem}{ext} em {dest_dir}")


# --------------------------------------------------------------------------- execução ffmpeg

_TIME_RE = re.compile(r"^out_time_(?:us|ms)=(\d+)$")


def _run_process(
    args: Sequence[str],
    on_stdout_line: Optional[Callable[[str], None]],
    cancel_event: Optional[threading.Event],
    tool_name: str,
    env: Optional[dict] = None,
    stderr_keep: int = _STDERR_TAIL,
) -> tuple:
    """Executa um processo (sem shell) lendo stdout linha a linha.

    Retorna ``(returncode, stderr_lines)``. Levanta CancelledError se ``cancel_event``
    for acionado (o processo é morto imediatamente) e DependencyMissingError se o
    executável não puder ser iniciado.
    """
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("Processamento cancelado.")
    try:
        proc = subprocess.Popen(
            list(args),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=_CREATIONFLAGS,
        )
    except OSError as exc:
        raise DependencyMissingError(f"Não foi possível executar o {tool_name}: {exc}") from exc

    stderr_tail: deque = deque(maxlen=stderr_keep)
    cancelled = threading.Event()

    def read_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_tail.append(line.rstrip())

    def watch_cancel() -> None:
        if cancel_event is None:
            return
        while proc.poll() is None:
            if cancel_event.wait(0.2):
                cancelled.set()
                # kill imediato: com SIGTERM o ffmpeg finaliza o arquivo de forma
                # "graciosa" (flush do encoder), o que levava vários segundos; a saída
                # parcial é descartada de qualquer forma.
                try:
                    proc.kill()
                except OSError:
                    pass
                return

    t_err = threading.Thread(target=read_stderr, daemon=True)
    t_cancel = threading.Thread(target=watch_cancel, daemon=True)
    t_err.start()
    t_cancel.start()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if on_stdout_line is not None:
                try:
                    on_stdout_line(line.rstrip("\r\n"))
                except Exception:
                    pass
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        t_err.join(timeout=5)
        t_cancel.join(timeout=6)
        for pipe in (proc.stdout, proc.stderr):
            try:
                if pipe is not None:
                    pipe.close()
            except OSError:
                pass

    if cancelled.is_set() or (cancel_event is not None and cancel_event.is_set()):
        raise CancelledError("Processamento cancelado.")
    return proc.returncode, list(stderr_tail)


def _run_ffmpeg(
    args: Sequence[str],
    duration: Optional[float],
    on_fraction: Optional[Callable[[float], None]],
    cancel_event: Optional[threading.Event],
) -> None:
    """Executa ffmpeg com ``-progress pipe:1``; levanta ExtractionError/CancelledError."""

    def on_line(line: str) -> None:
        m = _TIME_RE.match(line.strip())
        if m and duration and on_fraction is not None:
            frac = int(m.group(1)) / 1_000_000 / duration
            on_fraction(max(0.0, min(1.0, frac)))

    returncode, stderr_lines = _run_process(args, on_line, cancel_event, "ffmpeg")
    if returncode != 0:
        detail = _last_lines("\n".join(stderr_lines))
        raise ExtractionError(f"ffmpeg falhou (código {returncode})" + (f": {detail}" if detail else "."))


def _base_args(ffmpeg: str, src: Path) -> list:
    return [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-nostats",
            "-progress", "pipe:1", "-n", "-i", os.fspath(src)]


def _mp4_is_copy_compatible(info: MediaInfo) -> bool:
    return info.video_codec == "h264" and info.pix_fmt in ("yuv420p", "yuvj420p", None)


def _video_args(mode: str, info: MediaInfo) -> list:
    vmap = f"0:{info.video_index}" if info.video_index is not None else "0:v:0"
    common = ["-map", vmap, "-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1"]
    even = ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
    if mode == "copy":
        codec = ["-c:v", "copy"]
    elif mode == "reencode":
        codec = even + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
    else:  # reencode-mpeg4
        codec = even + ["-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p"]
    return common + codec + ["-movflags", "+faststart", "-f", "mp4"]


def _verify_output(path: Path, ffprobe: str, want_video: bool) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise ExtractionError("o ffmpeg não gerou dados de saída.")
    try:
        info = probe(path, ffprobe)
    except EngineError as exc:
        raise ExtractionError(f"arquivo gerado é inválido ({exc}).") from exc
    if want_video:
        if not info.has_video:
            raise ExtractionError("arquivo MP4 gerado não contém vídeo.")
        if info.has_audio:
            raise ExtractionError("arquivo MP4 gerado ainda contém áudio.")
    elif not info.has_audio:
        raise ExtractionError("arquivo MP3 gerado não contém áudio.")


# --------------------------------------------------------------------------- pastas numeradas


def _max_number(dest: Path) -> int:
    best = 0
    try:
        with os.scandir(dest) as it:
            for entry in it:
                if _NUM_DIR_RE.match(entry.name):
                    best = max(best, int(entry.name))
    except OSError as exc:
        raise InvalidInputError(f"Não foi possível ler a pasta de saída: {dest} ({exc.strerror or exc})") from exc
    return best


def _folder_name(n: int) -> str:
    return f"{n:03d}"


def next_output_folder(output_dir: PathLike) -> Path:
    """Próxima pasta numerada que seria usada (só consulta; não reserva)."""
    d = Path(output_dir).expanduser()
    n = _max_number(d) + 1 if d.is_dir() else 1
    return d / _folder_name(n)


def _reserve_folder(dest: Path) -> Path:
    """Cria atomicamente a próxima pasta NNN (maior número existente + 1). Nunca reutiliza nome existente."""
    n = _max_number(dest) + 1
    for _ in range(100000):
        cand = dest / _folder_name(n)
        try:
            os.mkdir(cand)
            return cand
        except FileExistsError:
            n += 1
    raise ExtractionError(f"Não foi possível reservar uma pasta numerada em {dest}")


def _hidden_tmp(folder: Path, name: str) -> Path:
    return folder / f".{name}.{secrets.token_hex(4)}{_PART_SUFFIX}"


def _rmtree(p: Optional[Path]) -> None:
    if p is not None:
        shutil.rmtree(p, ignore_errors=True)


# --------------------------------------------------------------------------- frames


def _frame_times(info: MediaInfo, rng: random.Random) -> tuple:
    """4 instantes crescentes em [0, fim_seguro]: 1 aleatório em cada quarto. Retorna (tempos, aviso|None)."""
    candidates = [d for d in (info.video_duration, info.duration) if d]
    if not candidates:
        return [0.0] * FRAME_COUNT, "Duração do vídeo desconhecida: os 4 frames foram extraídos do início."
    duration = min(candidates)
    frame = 1.0 / info.fps if info.fps else 0.04
    # margem para nunca pedir instante além do último quadro; em vídeos < 1 s usa só 1 quadro
    margin = frame if duration < 1.0 else max(frame, 0.1)
    end = max(0.0, duration - margin)
    width = end / FRAME_COUNT
    times = [round(i * width + rng.random() * width, 3) for i in range(FRAME_COUNT)]
    warning = None
    if end < FRAME_COUNT * frame:
        warning = "Vídeo muito curto: alguns dos 4 frames podem ser iguais."
    return times, warning


def _extract_frame(ff: str, fp: str, src: Path, info: MediaInfo, t: float, out_tmp: Path,
                   cancel_event: Optional[threading.Event]) -> None:
    vmap = f"0:{info.video_index}" if info.video_index is not None else "0:v:0"
    args = [ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-nostats", "-n",
            "-ss", f"{t:.3f}", "-i", os.fspath(src), "-map", vmap, "-frames:v", "1",
            "-an", "-sn", "-dn", "-c:v", "mjpeg", "-q:v", "2", "-f", "image2", "-update", "1",
            os.fspath(out_tmp)]
    returncode, stderr_lines = _run_process(args, None, cancel_event, "ffmpeg")
    if returncode != 0:
        raise ExtractionError(_last_lines("\n".join(stderr_lines)) or f"ffmpeg código {returncode}")
    if not out_tmp.exists() or out_tmp.stat().st_size == 0:
        raise ExtractionError("nenhuma imagem gerada nesse instante.")
    try:
        img = probe(out_tmp, fp)
    except EngineError as exc:
        raise ExtractionError(f"imagem inválida ({exc}).") from exc
    if not img.has_video or not img.width:
        raise ExtractionError("imagem inválida.")


def _make_frames(ff, fp, src, info, folder, rng, report, cancel_event) -> tuple:
    """Gera NNN/frames/frame_01..04.jpg. Tudo ou nada. Retorna (paths, times, avisos)."""
    times, warning = _frame_times(info, rng)
    frames_dir = folder / FRAMES_DIRNAME
    frames_dir.mkdir()
    paths, used = [], []
    try:
        for i, t in enumerate(times, start=1):
            name = f"frame_{i:02d}.jpg"
            last_exc: Optional[Exception] = None
            for cand in dict.fromkeys((t, round(t / 2, 3), 0.0)):
                tmp = _hidden_tmp(frames_dir, name)
                try:
                    _extract_frame(ff, fp, src, info, cand, tmp, cancel_event)
                    final = frames_dir / name
                    os.replace(tmp, final)
                    paths.append(final)
                    used.append(cand)
                    last_exc = None
                    break
                except ExtractionError as exc:
                    last_exc = exc
                finally:
                    _safe_unlink(tmp)
            if last_exc is not None:
                raise ExtractionError(f"frame {i:02d} em {t:.3f}s: {last_exc}")
            report("frames", i / FRAME_COUNT)
    except BaseException:
        _rmtree(frames_dir)
        raise
    warnings = [warning] if warning else []
    if used != times:
        warnings.append("Alguns frames foram extraídos de instantes anteriores porque o instante sorteado não gerou imagem.")
    return paths, used, warnings


# --------------------------------------------------------------------------- processamento


def process_video(
    path: PathLike,
    output_dir: PathLike,
    on_progress: Optional[ProgressCallback] = None,
    cancel_event: Optional[threading.Event] = None,
    ffmpeg: Optional[PathLike] = None,
    ffprobe: Optional[PathLike] = None,
    seed: Optional[int] = None,
    rng: Optional[random.Random] = None,
    on_folder: Optional[Callable[[Path], None]] = None,
) -> VideoResult:
    """Processa um vídeo para ``output_dir/NNN/`` (audio.mp3, video.mp4 sem áudio, frames/frame_01..04.jpg).

    Não levanta exceção para problemas do arquivo (status "failed"). Levanta InvalidInputError
    (destino) e DependencyMissingError. ``on_progress(stage, fraction)``: stage em
    {"probe", "audio", "video", "frames"}. ``on_folder(pasta)`` é chamado logo após reservar NNN.
    """
    if output_dir is None:
        raise InvalidInputError("Escolha a pasta de saída.")
    ff, fp = _require_tools(ffmpeg, ffprobe)
    out = prepare_output_dir(output_dir)
    if rng is None:
        rng = random.Random(seed) if seed is not None else random.SystemRandom()

    src = Path(path).expanduser()
    result = VideoResult(source=src, status=STATUS_FAILED)

    def report(stage: str, frac: float) -> None:
        if on_progress is not None:
            try:
                on_progress(stage, frac)
            except Exception:  # callback da UI nunca derruba o processamento
                pass

    if not src.exists():
        result.error = f"Arquivo não encontrado: {src}"
        return result
    if not src.is_file():
        result.error = f"Não é um arquivo: {src}"
        return result
    if not os.access(src, os.R_OK):
        result.error = f"Sem permissão de leitura: {src.name}"
        return result
    src = src.resolve()
    result.source = src

    report("probe", 0.0)
    try:
        info = probe(src, fp)
    except InvalidInputError as exc:
        result.error = str(exc)
        return result
    report("probe", 1.0)
    if not info.has_video and not info.has_audio:
        result.error = f"O arquivo não contém trilhas de áudio nem de vídeo: {src.name}"
        return result
    if cancel_event is not None and cancel_event.is_set():
        result.status = STATUS_CANCELLED
        result.error = "Processamento cancelado."
        return result

    try:
        folder = _reserve_folder(out)
    except EngineError as exc:
        result.error = str(exc)
        return result
    result.folder = folder
    if on_folder is not None:
        try:
            on_folder(folder)
        except Exception:
            pass

    errors: list = []
    tmp: Optional[Path] = None
    try:
        # ---- audio.mp3
        if not info.has_audio:
            result.warnings.append("O vídeo não possui trilha de áudio; audio.mp3 não foi gerado.")
        elif "libmp3lame" not in _available_encoders(ff):
            errors.append("áudio: o ffmpeg instalado não possui o codificador libmp3lame.")
        else:
            tmp = _hidden_tmp(folder, AUDIO_NAME)
            amap = f"0:{info.audio_index}" if info.audio_index is not None else "0:a:0"
            args = _base_args(ff, src) + [
                "-map", amap, "-vn", "-sn", "-dn", "-c:a", "libmp3lame", "-q:a", "2",
                "-f", "mp3", os.fspath(tmp),
            ]
            try:
                report("audio", 0.0)
                _run_ffmpeg(args, info.duration, lambda f: report("audio", f), cancel_event)
                _verify_output(tmp, fp, want_video=False)
                final = folder / AUDIO_NAME
                os.replace(tmp, final)
                result.audio_path = final
                report("audio", 1.0)
            except ExtractionError as exc:
                errors.append(f"áudio: {exc}")
            finally:
                _safe_unlink(tmp)
                tmp = None

        if not info.has_video:
            errors.append("o arquivo não contém trilha de vídeo (video.mp4 e frames não gerados).")
        else:
            # ---- video.mp4 sem áudio
            encoders = _available_encoders(ff)
            modes = []
            if _mp4_is_copy_compatible(info):
                modes.append("copy")
            if "libx264" in encoders:
                modes.append("reencode")
            if "mpeg4" in encoders:
                modes.append("reencode-mpeg4")
            if not modes:
                modes.append("reencode")
            last_error: Optional[str] = None
            for i, mode in enumerate(modes):
                tmp = _hidden_tmp(folder, VIDEO_NAME)
                args = _base_args(ff, src) + _video_args(mode, info) + [os.fspath(tmp)]
                try:
                    report("video", 0.0)
                    _run_ffmpeg(args, info.duration, lambda f: report("video", f), cancel_event)
                    _verify_output(tmp, fp, want_video=True)
                    final = folder / VIDEO_NAME
                    os.replace(tmp, final)
                    result.video_path = final
                    result.video_mode = mode
                    if i > 0:
                        result.warnings.append(f"Primeira tentativa de video.mp4 falhou ({last_error}); usado modo '{mode}'.")
                    report("video", 1.0)
                    last_error = None
                    break
                except ExtractionError as exc:
                    last_error = str(exc)
                finally:
                    _safe_unlink(tmp)
                    tmp = None
            if last_error is not None:
                errors.append(f"vídeo: {last_error}")

            # ---- frames
            try:
                report("frames", 0.0)
                paths, used, warns = _make_frames(ff, fp, src, info, folder, rng, report, cancel_event)
                result.frame_paths, result.frame_times = paths, used
                result.warnings.extend(warns)
            except ExtractionError as exc:
                errors.append(f"frames: {exc}")
    except CancelledError:
        _safe_unlink(tmp)
        _rmtree(folder)  # entrega incompleta: removida inteira
        result.folder = None
        result.audio_path = result.video_path = None
        result.frame_paths, result.frame_times = [], []
        result.status = STATUS_CANCELLED
        result.error = "Processamento cancelado."
        return result
    except OSError as exc:
        _safe_unlink(tmp)
        errors.append(f"erro de arquivo: {exc.strerror or exc}")

    produced = result.audio_path is not None or result.video_path is not None or bool(result.frame_paths)
    if not produced:
        _rmtree(folder)
        result.folder = None
        result.status = STATUS_FAILED
        result.error = "; ".join(errors) or "Nenhum arquivo gerado."
    elif errors:
        result.status = STATUS_PARTIAL
        result.error = "; ".join(errors)
    elif not info.has_audio:
        result.status = STATUS_NO_AUDIO
    else:
        result.status = STATUS_SUCCESS
    return result


# --------------------------------------------------------------------------- fila


def _validate_batch(videos: Iterable[PathLike], output_dir, ffmpeg, ffprobe) -> tuple:
    vids = [Path(v).expanduser() for v in videos]
    if not vids:
        raise InvalidInputError("Nenhum vídeo para processar.")
    if output_dir is None:
        raise InvalidInputError("Escolha a pasta de saída.")
    tools = _require_tools(ffmpeg, ffprobe)
    out = prepare_output_dir(output_dir)
    return vids, out, tools


_STAGE_LABEL = {"probe": "Analisando", "audio": "Extraindo áudio", "video": "Gerando vídeo sem áudio",
                "frames": "Extraindo frames"}
_WEIGHTS = {"audio": 0.25, "video": 0.5, "frames": 0.25}
_ORDER = ("audio", "video", "frames")


def _run_batch_validated(vids, out, tools, on_event, cancel_event, rng) -> list:
    ff, fp = tools
    total = len(vids)
    results: list = []

    def emit(ev: Event) -> None:
        if on_event is None:
            return
        try:
            on_event(ev)
        except Exception:
            pass

    emit(Event("batch_started", 0, total, message=f"Iniciando fila com {total} vídeo(s)."))
    for idx, src in enumerate(vids):
        if cancel_event.is_set():
            r = VideoResult(source=src, status=STATUS_CANCELLED, error="Processamento cancelado.")
            results.append(r)
            emit(Event("file_finished", idx, total, src, percent=0.0,
                       batch_percent=100.0 * (idx + 1) / total, message=r.summary(), result=r))
            continue

        state = {"folder": None, "started": False}

        def on_folder(folder: Path, _idx=idx, _src=src, _state=state) -> None:
            _state["folder"] = folder
            _state["started"] = True
            emit(Event("file_started", _idx, total, _src, batch_percent=100.0 * _idx / total, folder=folder,
                       message=f"[{_idx + 1}/{total}] {_src.name} -> pasta {folder.name}"))

        def on_progress(stage: str, frac: float, _idx=idx, _src=src, _state=state) -> None:
            if stage not in _WEIGHTS or not _state["started"]:
                return
            done = sum(_WEIGHTS[k] for k in _ORDER[: _ORDER.index(stage)])
            pct = 100.0 * (done + _WEIGHTS[stage] * frac)
            folder = _state["folder"]
            emit(Event("progress", _idx, total, _src, stage=stage, percent=pct, folder=folder,
                       batch_percent=100.0 * (_idx + pct / 100.0) / total,
                       message=f"[{_idx + 1}/{total}] {_src.name} -> {folder.name}: "
                               f"{_STAGE_LABEL.get(stage, stage)} ({pct:.0f}%)"))

        try:
            r = process_video(src, out, on_progress, cancel_event, ff, fp, rng=rng, on_folder=on_folder)
        except EngineError as exc:  # p.ex. pasta de saída removida durante a fila
            r = VideoResult(source=src, status=STATUS_FAILED, error=str(exc))
        except Exception as exc:  # nunca derruba a fila
            r = VideoResult(source=src, status=STATUS_FAILED, error=f"Erro inesperado: {exc}")
        if not state["started"]:
            emit(Event("file_started", idx, total, src, batch_percent=100.0 * idx / total,
                       message=f"[{idx + 1}/{total}] {src.name}"))
        results.append(r)
        emit(Event("file_finished", idx, total, src, percent=100.0, folder=r.folder,
                   batch_percent=100.0 * (idx + 1) / total, message=r.summary(), result=r))

    counts: dict = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    labels = [
        (STATUS_SUCCESS, "concluído(s)"), (STATUS_NO_AUDIO, "sem áudio"), (STATUS_PARTIAL, "parcial(is)"),
        (STATUS_FAILED, "com falha"), (STATUS_CANCELLED, "cancelado(s)"),
    ]
    parts = [f"{counts[k]} {lbl}" for k, lbl in labels if counts.get(k)]
    prefix = "Fila cancelada" if cancel_event.is_set() else "Fila finalizada"
    emit(Event("batch_finished", total, total, percent=100.0, batch_percent=100.0,
               message=f"{prefix}: " + ", ".join(parts) + f". Saída: {out}", results=list(results)))
    return results


def _make_rng(seed: Optional[int]) -> random.Random:
    return random.Random(seed) if seed is not None else random.SystemRandom()


def run_batch(
    videos: Iterable[PathLike],
    output_dir: PathLike,
    on_event: Optional[EventCallback] = None,
    cancel_event: Optional[threading.Event] = None,
    ffmpeg: Optional[PathLike] = None,
    ffprobe: Optional[PathLike] = None,
    seed: Optional[int] = None,
) -> list:
    """Processa vídeos em sequência na thread atual; falhas individuais não param a fila."""
    vids, out, tools = _validate_batch(videos, output_dir, ffmpeg, ffprobe)
    return _run_batch_validated(vids, out, tools, on_event, cancel_event or threading.Event(), _make_rng(seed))


class BatchProcessor:
    """Processa uma fila de vídeos em uma thread daemon (uma pasta NNN por vídeo em ``output_dir``).

    ``on_event`` é chamado NA THREAD DE TRABALHO: a UI deve repassar via ``queue.Queue``
    + ``root.after`` e não tocar widgets diretamente.
    """

    def __init__(
        self,
        videos: Iterable[PathLike],
        output_dir: PathLike,
        on_event: Optional[EventCallback] = None,
        ffmpeg: Optional[PathLike] = None,
        ffprobe: Optional[PathLike] = None,
        seed: Optional[int] = None,
    ) -> None:
        self._videos = list(videos)
        self._output_dir = output_dir
        self._on_event = on_event
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe
        self._seed = seed
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._results: list = []
        self._lock = threading.Lock()

    def _collect(self, ev: Event) -> None:
        if ev.kind == "file_finished" and ev.result is not None:
            with self._lock:
                self._results.append(ev.result)
        if self._on_event is not None:
            self._on_event(ev)

    def start(self) -> None:
        """Valida (pode levantar DependencyMissingError/InvalidInputError) e inicia a thread."""
        if self._thread is not None:
            raise EngineError("Este processamento já foi iniciado.")
        vids, out, tools = _validate_batch(self._videos, self._output_dir, self._ffmpeg, self._ffprobe)
        rng = _make_rng(self._seed)

        def target() -> None:
            _run_batch_validated(vids, out, tools, self._collect, self._cancel, rng)

        self._thread = threading.Thread(target=target, name="video-extractor-batch", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        """Pede cancelamento: interrompe o processo atual e marca os restantes como cancelados."""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Aguarda o fim. Retorna True se terminou."""
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @property
    def results(self) -> list:
        with self._lock:
            return list(self._results)


# =========================================================================== Instagram (yt-dlp opcional)

ENV_YTDLP = "VIDEO_EXTRACTOR_YTDLP"
IG_MAX_ITEMS = 20
_IG_HOSTS = frozenset({"instagram.com", "www.instagram.com", "m.instagram.com"})
_IG_POST_KINDS = {"p": "p", "reel": "reel", "reels": "reel", "tv": "tv"}
_IG_LOGIN_PATHS = frozenset({"stories", "explore", "accounts", "direct", "s", "share"})
_SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_INCOMPLETE_SUFFIXES = (".part", ".ytdl", ".temp", ".tmp")
_PROGRESS_PREFIX = "VXPROG "
_FILE_PREFIX = "VXFILE "


class DownloadError(EngineError):
    """Falha ao baixar do Instagram. ``kind`` classifica a causa."""

    def __init__(self, message: str, kind: str = "unknown") -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class DownloaderStatus:
    ok: bool
    command: Optional[list]
    version: Optional[str]
    message: str


@dataclass
class DownloadResult:
    url: str
    files: list
    warnings: list = field(default_factory=list)


# --------------------------------------------------------------------------- validação de URL


def validate_instagram_url(text: str) -> str:
    """Valida e normaliza um link público de publicação/reel/vídeo do Instagram.

    Retorna ``https://www.instagram.com/<p|reel|tv>/<shortcode>/``. Levanta InvalidInputError.
    """
    if not isinstance(text, str):
        raise InvalidInputError("Informe o link como texto.")
    s = text.strip()
    if not s:
        raise InvalidInputError("Informe um link do Instagram.")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in s):
        raise InvalidInputError("O link não pode conter espaços ou quebras de linha.")
    if not _SCHEME_RE.match(s):
        if s.lower().split("/", 1)[0].rstrip(".") in _IG_HOSTS:
            s = "https://" + s
        else:
            raise InvalidInputError("Link inválido: use um endereço https://www.instagram.com/...")
    try:
        parts = urllib.parse.urlsplit(s)
    except ValueError as exc:
        raise InvalidInputError("Link inválido.") from exc
    if parts.scheme.lower() not in ("http", "https"):
        raise InvalidInputError("Apenas links http(s) do Instagram são aceitos.")
    netloc = parts.netloc
    if "@" in netloc or "\\" in netloc:
        raise InvalidInputError("Links com usuário/senha embutidos não são aceitos.")
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidInputError("Link inválido: porta mal formada.") from exc
    if port is not None or netloc.endswith(":"):
        raise InvalidInputError("Links do Instagram com porta explícita não são aceitos.")
    host = (parts.hostname or "").rstrip(".")
    if not host.isascii() or host not in _IG_HOSTS:
        raise InvalidInputError("Apenas links do Instagram (instagram.com) são aceitos.")
    segs = [seg for seg in parts.path.split("/") if seg]
    if segs and segs[0].lower() in _IG_LOGIN_PATHS:
        raise InvalidInputError(
            "Stories, destaques, explorar e links de compartilhamento não são suportados "
            "(exigem login ou não são publicações). Use o link de uma publicação ou reel público."
        )
    kind = code = None
    if len(segs) >= 2 and segs[0].lower() in _IG_POST_KINDS:
        kind, code = _IG_POST_KINDS[segs[0].lower()], segs[1]
    elif len(segs) >= 3 and segs[1].lower() in _IG_POST_KINDS:
        kind, code = _IG_POST_KINDS[segs[1].lower()], segs[2]
    if kind is None or code is None:
        raise InvalidInputError(
            "O link precisa ser de uma publicação, reel ou vídeo (instagram.com/p/..., /reel/..., /tv/...). "
            "Perfis não são suportados."
        )
    if not _SHORTCODE_RE.match(code) or code.lower() == "audio":
        raise InvalidInputError("Código da publicação inválido no link do Instagram.")
    return f"https://www.instagram.com/{kind}/{code}/"


def is_instagram_url(text: str) -> bool:
    try:
        validate_instagram_url(text)
    except InvalidInputError:
        return False
    return True


def _shortcode(normalized_url: str) -> str:
    return normalized_url.rstrip("/").rsplit("/", 1)[-1]


# --------------------------------------------------------------------------- yt-dlp


def _ytdlp_install_hint() -> str:
    system = platform.system()
    if system == "Windows":
        how = (
            "na pasta do programa: py -m venv .venv && .venv\\Scripts\\python -m pip install -r "
            "requirements-instagram.txt e abra com run.bat (ou: winget install yt-dlp.yt-dlp)"
        )
    else:
        alt = "brew install yt-dlp ou pipx install yt-dlp" if system == "Darwin" else "pipx install yt-dlp"
        how = (
            "na pasta do programa: python3 -m venv .venv && .venv/bin/python -m pip install -r "
            f"requirements-instagram.txt e abra com ./run.sh (ou: {alt})"
        )
    return (
        "Para baixar do Instagram instale o yt-dlp (opcional; arquivos locais funcionam sem ele) "
        f"{how}. A versão atual do yt-dlp exige Python 3.11+."
    )


def _resolve_ytdlp(override: Optional[PathLike] = None) -> Optional[list]:
    cand = override if override is not None else os.environ.get(ENV_YTDLP) or None
    if cand is not None:
        cand = os.fspath(cand)
        if os.path.sep in cand or (os.altsep and os.altsep in cand):
            if not os.path.isfile(cand):
                return None
            if cand.lower().endswith(".py"):
                return [sys.executable, cand]
            return [cand] if os.access(cand, os.X_OK) else None
        found = shutil.which(cand)
        return [found] if found else None
    found = shutil.which("yt-dlp")
    if found:
        return [found]
    try:
        if importlib.util.find_spec("yt_dlp") is not None:
            return [sys.executable, "-m", "yt_dlp"]
    except (ImportError, ValueError):
        pass
    return None


def _ytdlp_env() -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def check_downloader(ytdlp: Optional[PathLike] = None) -> DownloaderStatus:
    """Verifica o yt-dlp (opcional). Nunca levanta exceção."""
    cmd = _resolve_ytdlp(ytdlp)
    if cmd is None:
        return DownloaderStatus(False, None, None, f"yt-dlp não encontrado. {_ytdlp_install_hint()}")
    try:
        proc = subprocess.run(
            cmd + ["--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=_ytdlp_env(),
            creationflags=_CREATIONFLAGS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return DownloaderStatus(False, None, None, f"yt-dlp não pôde ser executado ({exc}). {_ytdlp_install_hint()}")
    version = (proc.stdout or "").strip().splitlines()[0].strip() if (proc.stdout or "").strip() else None
    if proc.returncode != 0 or not version:
        detail = _last_lines(proc.stderr, 1)
        return DownloaderStatus(
            False, None, None,
            f"yt-dlp não funcionou (código {proc.returncode}{': ' + detail if detail else ''}). {_ytdlp_install_hint()}",
        )
    return DownloaderStatus(True, cmd, version, f"yt-dlp {version} disponível.")


def _require_ytdlp(ytdlp: Optional[PathLike]) -> list:
    st = check_downloader(ytdlp)
    if not st.ok:
        raise DependencyMissingError(st.message)
    return st.command


# Trechos de mensagens reais do yt-dlp (stderr "ERROR: ...") -> (kind, mensagem PT). Ordem importa.
_ERROR_PATTERNS = (
    ("no_video", ("there is no video in this post", "no video formats found", "no video could be found"),
     "A publicação não contém vídeo (apenas imagens)."),
    ("drm", ("drm",), "O vídeo é protegido por DRM; não é possível baixá-lo."),
    ("rate_limit", ("rate-limit", "rate limit", "too many requests", "http error 429",
                    "redirected to the login page"),
     "O Instagram bloqueou o acesso anônimo temporariamente (limite de requisições). "
     "Tente novamente mais tarde. O aplicativo não usa login."),
    ("login", ("only available for registered users", "restricted video", "login required",
               "log in", "login", "private", "cookies"),
     "Esta publicação é privada, restrita ou exige login. Apenas vídeos públicos acessíveis sem login são suportados."),
    ("not_found", ("http error 404", "not found", "does not exist", "has been removed", "is not available",
                   "content is unreachable", "empty media response"),
     "Publicação não encontrada ou indisponível sem login (removida, privada ou bloqueada pelo Instagram)."),
    ("network", ("unable to download webpage", "urlopen error", "name or service not known",
                 "temporary failure in name resolution", "nodename nor servname", "getaddrinfo failed",
                 "timed out", "connection refused", "connection reset", "network is unreachable",
                 "no route to host", "ssl", "certificate", "connection aborted", "remote end closed",
                 "transporterror", "unable to connect", "failed to resolve"),
     "Falha de rede ao acessar o Instagram. Verifique sua conexão e tente novamente."),
    ("unsupported", ("unsupported url",), "Link não suportado pelo yt-dlp."),
)


def _classify_download_error(stderr_lines: Sequence[str], returncode: int) -> DownloadError:
    errors = [ln for ln in stderr_lines if ln.startswith("ERROR:")]
    relevant = errors or [ln for ln in stderr_lines if ln.strip()]
    text = "\n".join(relevant).lower()
    detail = (errors[-1] if errors else (relevant[-1] if relevant else "")).replace("ERROR:", "").strip()
    if len(detail) > 300:
        detail = detail[:300] + "…"
    # "empty media response" cita cookies; trate como not_found antes de login
    if "empty media response" in text:
        kind, msg = "not_found", _ERROR_PATTERNS[4][2]
        return DownloadError(f"{msg} (yt-dlp: {detail})", kind)
    for kind, needles, msg in _ERROR_PATTERNS:
        if any(n in text for n in needles):
            return DownloadError(f"{msg}" + (f" (yt-dlp: {detail})" if detail else ""), kind)
    return DownloadError(
        f"Falha no download (yt-dlp código {returncode})" + (f": {detail}" if detail else "."), "unknown"
    )


def _ytdlp_args(cmd: Sequence[str], url: str, workdir: Path, ffmpeg: Optional[str]) -> list:
    args = list(cmd) + [
        "--ignore-config", "--no-cache-dir", "--no-cookies", "--no-cookies-from-browser",
        "--color", "never", "--newline", "--progress",
        "--progress-template",
        "download:" + _PROGRESS_PREFIX + "%(progress.downloaded_bytes)s %(progress.total_bytes)s "
        "%(progress.total_bytes_estimate)s %(info.playlist_index)s %(info.n_entries)s",
        "--print", "after_move:" + _FILE_PREFIX + "%(filepath)s",
        "-P", os.fspath(workdir),
        "-o", "%(id)s.%(ext)s",
        "--restrict-filenames", "--no-overwrites", "--no-mtime",
        "--yes-playlist", "-I", f":{IG_MAX_ITEMS}", "--ignore-no-formats-error",
        "--socket-timeout", "30", "--retries", "3", "--fragment-retries", "3",
        "-f", "bv*+ba/b", "--merge-output-format", "mp4",
    ]
    if ffmpeg:
        args += ["--ffmpeg-location", ffmpeg]
    return args + ["--", url]


def _num(tok: str) -> Optional[float]:
    try:
        v = float(tok)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None


DownloadProgressCallback = Callable[[float, str], None]  # (percent 0-100 ou -1, mensagem PT)


def _ytdlp_download(
    cmd: Sequence[str],
    url: str,
    workdir: Path,
    ffmpeg: Optional[str],
    on_progress: Optional[DownloadProgressCallback],
    cancel_event: Optional[threading.Event],
) -> tuple:
    """Baixa para ``workdir``. Retorna (arquivos concluídos, avisos). Levanta DownloadError/CancelledError."""
    reported: list = []
    last_emit = [0.0, None]

    def on_line(line: str) -> None:
        if line.startswith(_FILE_PREFIX):
            reported.append(line[len(_FILE_PREFIX):].strip())
            return
        if not line.startswith(_PROGRESS_PREFIX) or on_progress is None:
            return
        toks = line[len(_PROGRESS_PREFIX):].split()
        toks += ["NA"] * (5 - len(toks))
        done, total, estimate, idx, n = (_num(t) for t in toks[:5])
        total = total or estimate
        percent = -1.0
        if done is not None and total:
            frac = max(0.0, min(1.0, done / total))
            if n and n > 1 and idx:
                frac = (idx - 1 + frac) / n
            percent = 100.0 * frac
        mb = (done or 0) / 1_048_576
        item = f" (vídeo {int(idx)}/{int(n)})" if n and n > 1 and idx else ""
        if total:
            msg = f"Baixando do Instagram{item}: {mb:.1f} de {total / 1_048_576:.1f} MB"
        else:
            msg = f"Baixando do Instagram{item}: {mb:.1f} MB"
        now = time.monotonic()
        if now - last_emit[0] >= 0.1 or percent >= 100.0:
            last_emit[0] = now
            on_progress(percent, msg)

    if on_progress is not None:
        on_progress(-1.0, "Conectando ao Instagram...")
    returncode, stderr_lines = _run_process(
        _ytdlp_args(cmd, url, workdir, ffmpeg), on_line, cancel_event, "yt-dlp",
        env=_ytdlp_env(), stderr_keep=400,
    )
    warnings_raw = [ln for ln in stderr_lines if ln.startswith("WARNING:")]
    if returncode != 0:
        raise _classify_download_error(stderr_lines, returncode)

    root = workdir.resolve()
    files: list = []
    for raw in reported:
        p = Path(raw)
        try:
            rp = p.resolve()
        except OSError:
            continue
        if rp.parent != root or not rp.is_file() or rp.name.lower().endswith(_INCOMPLETE_SUFFIXES):
            continue
        if rp not in files:
            files.append(rp)

    warnings: list = []
    skipped = sum(
        1 for w in warnings_raw
        if any(n in w.lower() for n in ("there is no video in this post", "no video formats found"))
    )
    if not files:
        if skipped or not reported:
            raise DownloadError("A publicação não contém vídeo (apenas imagens).", "no_video")
        raise DownloadError("O yt-dlp terminou sem gerar arquivo de vídeo.", "unknown")
    if skipped:
        warnings.append(f"{skipped} item(ns) da publicação sem vídeo (imagens) foram ignorados.")
    return files, warnings


def _rename_downloads(files: Sequence[Path], workdir: Path, code: str) -> list:
    """Renomeia (dentro do temporário) para instagram_<shortcode>[_N].<ext> só com [A-Za-z0-9_-]."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", code)[:64] or "video"
    out = []
    for i, f in enumerate(files, start=1):
        ext = f.suffix.lower() if re.fullmatch(r"\.[a-z0-9]{1,5}", f.suffix.lower()) else ".mp4"
        stem = f"instagram_{safe}" + (f"_{i}" if len(files) > 1 else "")
        target = workdir / f"{stem}{ext}"
        if target != f:
            if target.exists():
                target = workdir / f"{stem}_{secrets.token_hex(3)}{ext}"
            os.replace(f, target)
        out.append(target)
    return out


def download_instagram(
    url: str,
    dest_dir: PathLike,
    on_progress: Optional[DownloadProgressCallback] = None,
    cancel_event: Optional[threading.Event] = None,
    ytdlp: Optional[PathLike] = None,
    ffmpeg: Optional[PathLike] = None,
) -> DownloadResult:
    """Baixa vídeo(s) de um link público do Instagram para ``dest_dir`` (nomes únicos, sem sobrescrever).

    Síncrono. Baixa em pasta temporária própria (sempre removida). Levanta InvalidInputError,
    DependencyMissingError, DownloadError ou CancelledError.
    """
    norm = validate_instagram_url(url)
    cmd = _require_ytdlp(ytdlp)
    ff = _resolve_tool("ffmpeg", ffmpeg, ENV_FFMPEG)
    dest = prepare_output_dir(dest_dir)
    workdir = Path(tempfile.mkdtemp(prefix="video-extractor-ig-"))
    try:
        files, warnings = _ytdlp_download(cmd, norm, workdir, ff, on_progress, cancel_event)
        files = _rename_downloads(files, workdir, _shortcode(norm))
        published = [_publish(f, dest, f.stem, f.suffix) for f in files]
        return DownloadResult(norm, published, warnings)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _validate_instagram(url, output_dir, keep_video_dir, ytdlp, ffmpeg, ffprobe) -> tuple:
    norm = validate_instagram_url(url)
    if output_dir is None:
        raise InvalidInputError("Escolha a pasta de saída.")
    cmd = _require_ytdlp(ytdlp)
    tools = _require_tools(ffmpeg, ffprobe)
    out = prepare_output_dir(output_dir)
    keep = prepare_output_dir(keep_video_dir) if keep_video_dir is not None else None
    return norm, cmd, tools, out, keep


def _run_instagram_validated(norm, cmd, tools, out, keep, on_event, cancel_event, sink, rng) -> list:
    """Download + fila. Nunca levanta; ``batch_finished`` é sempre o último evento (após limpar o temp).

    ``sink`` (dict) recebe 'error' e 'downloaded'.
    """
    ff, _fp = tools

    def emit(ev: Event) -> None:
        if on_event is None:
            return
        try:
            on_event(ev)
        except Exception:
            pass

    results: list = []
    final: Optional[Event] = None
    workdir: Optional[Path] = None
    try:
        workdir = Path(tempfile.mkdtemp(prefix="video-extractor-ig-"))
        emit(Event("download_started", 0, 1, stage="download", percent=-1.0,
                   message=f"Baixando do Instagram: {norm}"))

        def dl_progress(percent: float, msg: str) -> None:
            emit(Event("download_progress", 0, 1, stage="download", percent=percent,
                       batch_percent=-1.0 if percent < 0 else percent, message=msg))

        try:
            files, warnings = _ytdlp_download(cmd, norm, workdir, ff, dl_progress, cancel_event)
            files = _rename_downloads(files, workdir, _shortcode(norm))
        except CancelledError:
            sink["error"] = "Download cancelado."
            final = Event("batch_finished", 0, 0, percent=100.0, batch_percent=100.0,
                          message="Download cancelado.", results=[])
            return results
        except (DownloadError, DependencyMissingError) as exc:
            sink["error"] = str(exc)
            emit(Event("download_failed", 0, 1, stage="download", message=f"Falha no download: {exc}",
                       error=str(exc)))
            final = Event("batch_finished", 0, 0, percent=100.0, batch_percent=100.0,
                          message=f"Falha no download: {exc}", results=[], error=str(exc))
            return results

        extra = (" " + " ".join(warnings)) if warnings else ""
        emit(Event("download_finished", 0, 1, stage="download", percent=100.0, batch_percent=100.0,
                   message=f"Download concluído: {len(files)} vídeo(s).{extra}"))

        pending: list = []

        def relay(ev: Event) -> None:
            if ev.kind == "batch_finished":
                pending.append(ev)
            else:
                emit(ev)

        results = _run_batch_validated(files, out, tools, relay, cancel_event, rng)
        if warnings and results:
            results[0].warnings.extend(warnings)
        if keep is not None:
            kept = []
            for f, r in zip(files, results):
                try:
                    dst = _publish(f, keep, f.stem, f.suffix)
                    kept.append(dst)
                    r.source = dst
                except (OSError, EngineError) as exc:
                    r.warnings.append(f"Não foi possível guardar o vídeo baixado: {exc}")
            sink["downloaded"] = kept
        final = pending[-1] if pending else Event(
            "batch_finished", len(results), len(results), percent=100.0, batch_percent=100.0,
            message="Fila finalizada.", results=list(results))
        return results
    except Exception as exc:  # nunca derruba a thread sem batch_finished
        sink["error"] = f"Erro inesperado: {exc}"
        emit(Event("download_failed", 0, 1, stage="download", message=sink["error"], error=sink["error"]))
        final = Event("batch_finished", 0, 0, percent=100.0, batch_percent=100.0,
                      message=sink["error"], results=list(results), error=sink["error"])
        return results
    finally:
        if workdir is not None:
            shutil.rmtree(workdir, ignore_errors=True)
        if final is not None:
            emit(final)


def run_instagram(
    url: str,
    output_dir: PathLike,
    on_event: Optional[EventCallback] = None,
    cancel_event: Optional[threading.Event] = None,
    keep_video_dir: Optional[PathLike] = None,
    ytdlp: Optional[PathLike] = None,
    ffmpeg: Optional[PathLike] = None,
    ffprobe: Optional[PathLike] = None,
    seed: Optional[int] = None,
) -> list:
    """Síncrono: baixa o link e processa cada vídeo em ``output_dir/NNN``. Retorna list[VideoResult]."""
    norm, cmd, tools, out, keep = _validate_instagram(url, output_dir, keep_video_dir, ytdlp, ffmpeg, ffprobe)
    return _run_instagram_validated(norm, cmd, tools, out, keep, on_event,
                                    cancel_event or threading.Event(), {}, _make_rng(seed))


class InstagramProcessor(BatchProcessor):
    """Baixa um link do Instagram e processa os vídeos numa thread daemon.

    Mesma interface do BatchProcessor (start/cancel/is_running/wait/results) + ``error`` e
    ``downloaded``. ``on_event`` roda NA THREAD DE TRABALHO.
    """

    def __init__(
        self,
        url: str,
        output_dir: PathLike,
        on_event: Optional[EventCallback] = None,
        keep_video_dir: Optional[PathLike] = None,
        ytdlp: Optional[PathLike] = None,
        ffmpeg: Optional[PathLike] = None,
        ffprobe: Optional[PathLike] = None,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__([], output_dir, on_event, ffmpeg, ffprobe, seed)
        self.url = url
        self._keep = keep_video_dir
        self._ytdlp = ytdlp
        self._sink: dict = {"error": None, "downloaded": []}

    def start(self) -> None:
        if self._thread is not None:
            raise EngineError("Este processamento já foi iniciado.")
        norm, cmd, tools, out, keep = _validate_instagram(
            self.url, self._output_dir, self._keep, self._ytdlp, self._ffmpeg, self._ffprobe)
        self.url = norm
        rng = _make_rng(self._seed)

        def target() -> None:
            _run_instagram_validated(norm, cmd, tools, out, keep, self._collect, self._cancel, self._sink, rng)

        self._thread = threading.Thread(target=target, name="video-extractor-instagram", daemon=True)
        self._thread.start()

    @property
    def error(self) -> Optional[str]:
        return self._sink.get("error")

    @property
    def downloaded(self) -> list:
        return list(self._sink.get("downloaded") or [])


__all__ = [
    "VIDEO_EXTENSIONS", "ENV_FFMPEG", "ENV_FFPROBE",
    "STATUS_SUCCESS", "STATUS_NO_AUDIO", "STATUS_PARTIAL", "STATUS_FAILED", "STATUS_CANCELLED",
    "EngineError", "DependencyMissingError", "FFmpegNotFoundError", "InvalidInputError",
    "ExtractionError", "CancelledError",
    "DependencyStatus", "MediaInfo", "VideoResult", "Event",
    "AUDIO_NAME", "VIDEO_NAME", "FRAMES_DIRNAME", "FRAME_COUNT",
    "check_dependencies", "check_ffmpeg", "list_videos", "probe", "prepare_output_dir", "unique_path",
    "next_output_folder",
    "process_video", "run_batch", "BatchProcessor",
    # Instagram (yt-dlp opcional)
    "ENV_YTDLP", "IG_MAX_ITEMS", "DownloadError", "DownloaderStatus", "DownloadResult",
    "check_downloader", "validate_instagram_url", "is_instagram_url",
    "download_instagram", "run_instagram", "InstagramProcessor",
]
