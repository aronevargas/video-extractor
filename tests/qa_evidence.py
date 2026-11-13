#!/usr/bin/env python3
"""Evidência ffprobe reproduzível da fila V3 (pasta NNN por vídeo) — usado em docs/qa.md.

Uso:  python3 tests/qa_evidence.py [pasta_de_trabalho]
Cria vídeos sintéticos, roda a fila do engine num destino único e imprime a árvore de
saída com streams, durações, dimensões dos frames e instantes sorteados.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests import helpers as H  # noqa: E402
import extractor as E  # noqa: E402


def main() -> int:
    work = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="qa evidência "))
    src, out = work / "entrada", work / "saída única"
    queue = [
        H.make_video(src / "01 Férias ação.mp4", duration=6.0),
        H.make_invalid(src / "02 corrompido.mp4"),
        H.make_video(src / "03 sem áudio.mp4", audio=False),
        H.make_video(src / "04 vp9 opus.webm", vcodec="libvpx-vp9", acodec="libopus", size="320x240"),
    ]
    before = {p.name: H.sha256(p) for p in queue}
    results = E.run_batch(E.list_videos(src), out)
    print(f"destino: {out}")
    for r in results:
        print(f"\n[{r.status}] {Path(r.source).name} -> pasta={r.folder and Path(r.folder).name}"
              f"  erro={r.error!r}  avisos={r.warnings}")
        if not r.folder:
            continue
        for label, p in (("audio.mp3", r.audio_path), ("video.mp4", r.video_path)):
            if not p:
                print(f"  {label}: (não gerado)")
                continue
            ss = ", ".join(f"{s['codec_type']}:{s['codec_name']}" for s in H.probe(p)["streams"])
            print(f"  {label}: dur={H.duration(p):.3f}s streams=[{ss}]")
        for fp, t in zip(r.frame_paths, r.frame_times):
            codec, w, h = H.jpeg_info(fp)
            print(f"  frames/{Path(fp).name}: {codec} {w}x{h} t={t:.3f}s")
    print("\nárvore:")
    for p in sorted(out.rglob("*")):
        print("  " + str(p.relative_to(out)) + ("/" if p.is_dir() else ""))
    same = all(H.sha256(src / n) == h for n, h in before.items())
    print(f"\noriginais intactos (sha256 antes == depois): {same}")
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
