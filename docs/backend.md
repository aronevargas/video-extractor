# Backend — `extractor/engine.py` (v3)

Motor do Video Extractor. Recebe vídeos (arquivos locais ou um link público do Instagram) e, para
**cada vídeo**, cria **uma pasta numerada** dentro de **um único destino** escolhido:

```
<destino>/
  001/
    audio.mp3            # áudio (só se o vídeo tiver trilha de áudio)
    video.mp4            # vídeo SEM áudio
    frames/
      frame_01.jpg … frame_04.jpg   # 4 quadros de instantes aleatórios
  002/
  …
```

Usa só a biblioteca padrão do Python 3 e os binários `ffmpeg`/`ffprobe` (o yt-dlp é opcional, só para
links). Não importa tkinter. Tudo é exportado por `extractor/__init__.py`.

## Requisitos

- Python 3.8+ (arquivos locais). Opção Instagram: yt-dlp, que exige Python 3.11+ (ver abaixo).
- `ffmpeg` e `ffprobe` no `PATH`, com os codificadores `libmp3lame` (áudio), `mjpeg` (frames) e, de
  preferência, `libx264` (vídeo). Instalação: `sudo apt install ffmpeg` · `sudo dnf install ffmpeg` ·
  `sudo pacman -S ffmpeg` · `winget install Gyan.FFmpeg` · `brew install ffmpeg`.
- Caminhos alternativos (ou simulação de ausência em testes): variáveis de ambiente
  `VIDEO_EXTRACTOR_FFMPEG` / `VIDEO_EXTRACTOR_FFPROBE`, ou os argumentos `ffmpeg=`/`ffprobe=`.

## API

```python
from extractor import engine

st = engine.check_dependencies()          # DependencyStatus(ok, ffmpeg_path, ffprobe_path, message); nunca levanta
engine.check_ffmpeg()                     # levanta DependencyMissingError (alias FFmpegNotFoundError)
videos = engine.list_videos(pasta, recursive=False)   # list[Path], ordenada; InvalidInputError se pasta inválida
info = engine.probe(video)                # MediaInfo(duration, video_duration, fps, has_video, has_audio, ...)
engine.prepare_output_dir(destino)        # cria se faltar; InvalidInputError se for arquivo/não gravável
engine.next_output_folder(destino)        # Path da próxima pasta NNN (só consulta, não reserva)

r  = engine.process_video(video, destino, on_progress=None, cancel_event=None, seed=None, rng=None, on_folder=None)
rs = engine.run_batch(videos, destino, on_event=None, cancel_event=None, seed=None)       # síncrono, fila

job = engine.BatchProcessor(videos, destino, on_event=callback, seed=None)  # fila em thread daemon
job.start()        # valida dependências e destino ANTES de criar a thread: DependencyMissingError / InvalidInputError
job.cancel()       # mata o ffmpeg atual na hora; restantes viram "cancelled"
job.is_running; job.wait(timeout) -> bool; job.results -> list[VideoResult]
```

- Um único destino (`output_dir`); a seleção separada de pastas MP3/MP4 das versões anteriores foi removida.
- O destino é criado se não existir; se não for possível criar/gravar, ou o caminho for um arquivo →
  `InvalidInputError` **antes** de qualquer processamento.
- `process_video` **não levanta** para problemas do próprio arquivo (inexistente, sem permissão,
  não-mídia, corrompido): devolve `VideoResult` com `status="failed"`. Só levanta para erros de
  configuração (destino, dependências).
- `seed` (int) ou `rng` (`random.Random`) tornam os instantes dos frames determinísticos (testes).
  Sem eles usa `random.SystemRandom()`.
- Callbacks (`on_progress(stage, fraction)`, `on_event(Event)`, `on_folder(Path)`) rodam **na thread
  de trabalho**. A UI deve repassá-los via `queue.Queue` + `root.after`. Exceções dentro de callbacks
  são ignoradas e nunca derrubam a fila.

### Tipos

`VideoResult`: `source`, `status`, `folder` (Path da pasta `NNN` entregue, ou `None`), `audio_path`,
`video_path`, `frame_paths` (`frame_01..04`, nessa ordem), `frame_times` (segundos, mesma ordem,
crescentes), `warnings: list[str]`, `error: str|None`, `video_mode` (`"copy"`, `"reencode"`,
`"reencode-mpeg4"` ou `None`), `ok` (property), `summary()`. Aliases de compatibilidade:
`mp3_path` = `audio_path`, `mp4_path` = `video_path`, `frames` = `frame_paths`.

| status      | pasta `NNN` | conteúdo |
|-------------|-------------|----------|
| `success`   | mantida | `audio.mp3` + `video.mp4` + 4 frames |
| `no_audio`  | mantida | vídeo **mudo**: `video.mp4` + 4 frames, **sem** `audio.mp3` (nunca um MP3 vazio); aviso em `warnings` |
| `partial`   | mantida | só os itens que deram certo; `error` lista o que falhou (ex.: arquivo só de áudio → só `audio.mp3`; frames falharam → sem `frames/`) |
| `failed`    | **removida** (`folder=None`) | nada gerado; motivo em `error`. Arquivo inválido nem chega a criar pasta |
| `cancelled` | **removida** (`folder=None`) | item em andamento é descartado inteiro (entrega incompleta); pastas de itens já concluídos ficam intactas |

`Event`: `kind` (`batch_started`, `file_started`, `progress`, `file_finished`, `batch_finished`;
para links: `download_started`, `download_progress`, `download_finished`, `download_failed`),
`index` (0-based), `total`, `path`, `folder` (pasta `NNN` do item), `stage`
(`audio`/`video`/`frames`/`download`), `percent` (0–100 do item; pesos áudio 25 %, vídeo 50 %,
frames 25 %), `batch_percent`, `message` (PT-BR, inclui a pasta, ex. `"[2/5] aula.mkv -> 007: Extraindo
frames (80%)"`), `result` (em `file_finished`), `results` (em `batch_finished`), `error`.

- `file_started` é emitido logo após validar o arquivo com ffprobe e reservar a pasta, já com
  `folder`. Para arquivo inválido vem `file_started` com `folder=None` seguido de `file_finished` `failed`.
- `progress` e `file_finished` trazem `folder` (em `file_finished` é `result.folder`: `None` se a
  pasta foi removida).
- `batch_finished` é sempre o último evento, inclusive após cancelamento.

Exceções: `EngineError` ⊃ `DependencyMissingError` (= `FFmpegNotFoundError`), `InvalidInputError`,
`ExtractionError`, `CancelledError`, `DownloadError`. `str(e)` é mensagem em PT-BR pronta para o usuário.

## Decisões

### Numeração das pastas

- Nome = **maior número existente no destino + 1**, com 3 dígitos (`001`…`999`; depois `1000`, `1001`…).
  "Existente" é qualquer entrada cujo nome seja só dígitos (`^\d+$`), **pasta ou arquivo**. Por exemplo,
  um arquivo `001` faz a próxima pasta ser `002`.
- Lacunas **não** são reaproveitadas: com `001` e `005` existentes, a próxima é `006`. Assim números já
  usados nunca voltam a aparecer depois de entregas mais novas.
- Reserva **atômica** com `os.mkdir` (sem `exist_ok`): se outro processo criar o mesmo nome no meio
  tempo, tenta o próximo. Nunca sobrescreve nem escreve numa pasta existente, nem entre execuções.
- A reserva só acontece **depois** que o ffprobe valida o arquivo: arquivo inválido e falha de download
  não consomem número. Como pastas de `failed`/`cancelled` são removidas, o número delas pode ser usado
  pelo próximo item (continua sendo o "maior + 1").
- Uma pasta por **vídeo real**: cada vídeo de um carrossel do Instagram ganha sua própria pasta.

### Conteúdo de cada pasta

- Ordem de geração: `audio.mp3` → `video.mp4` → `frames/`. Cada arquivo é escrito num temporário
  oculto (`.<nome>.<aleatório>.part`) dentro da pasta `NNN` (frames dentro de `NNN/frames`) e só então
  renomeado para o nome final. Em falha ou cancelamento nenhum `.part` fica para trás.
- **Áudio:** primeira trilha de áudio, `libmp3lame` VBR `-q:a 2` (~190 kbps). Sem trilha de áudio:
  nenhum `audio.mp3` é criado e o status é `no_audio` (ou `partial` se outra parte falhar).
- **Vídeo sem áudio (`video.mp4`):** sem áudio/legendas/dados (`-an -sn -dn`), `+faststart`.
  1. Se já é H.264 `yuv420p` → cópia do stream (rápido, sem perda).
  2. Senão, ou se a cópia falhar → `libx264 -preset veryfast -crf 23 -pix_fmt yuv420p`, dimensões pares.
  3. Sem `libx264` ou se falhar → `mpeg4 -q:v 3`.
  Cada saída é verificada com ffprobe (vídeo presente e sem áudio; MP3 com áudio).
- **Frames:** 4 JPG (`mjpeg -q:v 2`), na **resolução original** do vídeo (rotação aplicada pelo ffmpeg).
  - Duração usada = a menor entre a duração do **stream de vídeo** e a do arquivo (um vídeo de 2 s com
    áudio de 8 s só tem frames sorteados nos 2 s de vídeo).
  - `fim_seguro = duração − margem`, com margem = 1 quadro (`1/fps`; 0,04 s se o fps é desconhecido) para
    vídeos < 1 s e `max(1 quadro, 0,1 s)` nos demais. Nunca se pede instante além do fim.
  - `[0, fim_seguro]` é dividido em 4 faixas iguais e um instante uniforme aleatório é sorteado em cada
    faixa. Os instantes ficam distintos, crescentes e espalhados pelo vídeo. Ficam em `frame_times`.
  - Cada frame é extraído com `ffmpeg -ss <t> -i <vídeo> -frames:v 1` e validado com ffprobe (JPG
    decodificável, largura > 0). Se um instante não gerar imagem, tenta `t/2` e depois `0`; o instante
    efetivo fica em `frame_times`, com aviso.
  - **Vídeo muito curto:** os instantes podem cair no mesmo quadro (ex.: 0,12 s a 25 fps tem 3 quadros),
    mas **sempre** são gerados 4 JPG válidos, com aviso "Vídeo muito curto: alguns dos 4 frames podem ser iguais."
  - **Duração desconhecida:** os 4 frames vêm do instante 0, com aviso.
  - Frames são **tudo ou nada**: se algum dos 4 falhar mesmo após os recuos, `frames/` é removida e o
    item fica `partial`.
- **Originais nunca são alterados.** Todo comando recebe argumentos em lista (sem shell), com `-n`
  (nunca sobrescrever), e lê o original apenas como entrada. Destino = pasta de origem funciona: as
  pastas `NNN` são criadas ao lado dos vídeos.
- **Espaços, acentos, Unicode:** suportados (caminhos via `pathlib`, I/O em UTF-8).

### Fila e cancelamento

- `list_videos` lista a pasta no momento do clique (sem monitoramento contínuo). O modo não recursivo
  nunca pega saídas (são pastas). O recursivo ignora subpastas `^\d+$` que contenham `frames/`.
- Processamento sequencial; a falha de um arquivo não interrompe os seguintes.
- `cancel()` mata imediatamente o processo atual (ffmpeg de áudio, vídeo ou frame, ou o yt-dlp), remove
  a pasta `NNN` do item em andamento e marca os restantes como `cancelled`. Medido: `cancel()` →
  `batch_finished` em ~0,00 s, sem ffmpeg vivo nem `.part`.
- **Windows:** subprocessos usam `CREATE_NO_WINDOW` (sem janelas de console).

## Instagram (link público) — opcional, via yt-dlp

Baixa o(s) vídeo(s) de um link **público** do Instagram e os passa automaticamente pela mesma
extração: cada vídeo baixado vira uma pasta `NNN` com `audio.mp3`, `video.mp4` sem áudio e `frames/`. Sem login, sem cookies, sem contorno de restrições ou DRM.

### Dependência

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (versão verificada: **2026.10.26**; a versão atual exige
  **Python 3.11+**). É **opcional**: sem ele o pacote importa normalmente e arquivos locais funcionam;
  só a opção de link fica indisponível (`check_downloader().ok == False` com instrução de instalação).
- Instalação reproduzível: `requirements-instagram.txt` (venv recomendado; instruções no arquivo).
- Resolução do executável: env `VIDEO_EXTRACTOR_YTDLP` (caminho; se terminar em `.py` roda com
  `sys.executable <script>`) → `yt-dlp` no `PATH` → `sys.executable -m yt_dlp` se o módulo existir.
  Também aceita o argumento `ytdlp=` nas funções/classes.

### API

```python
st = engine.check_downloader()                 # DownloaderStatus(ok, command, version, message); nunca levanta
url = engine.validate_instagram_url(texto)     # normaliza ou levanta InvalidInputError
engine.is_instagram_url(texto) -> bool

job = engine.InstagramProcessor(url, destino, on_event=cb, keep_video_dir=None, seed=None)
job.start()      # valida URL, yt-dlp, ffmpeg e destino ANTES da thread (InvalidInputError/DependencyMissingError)
job.cancel(); job.is_running; job.wait(t); job.results; job.error (str|None); job.downloaded (list[Path])

# síncronos (testes/scripts)
rs  = engine.run_instagram(url, destino, on_event=None, cancel_event=None, keep_video_dir=None, seed=None)
res = engine.download_instagram(url, dest_dir, on_progress=None, cancel_event=None)  # DownloadResult(url, files, warnings)
```

`download_instagram` levanta `DownloadError` (com `.kind`) ou `CancelledError`; `run_instagram` e
`InstagramProcessor` nunca levantam depois da validação: falhas viram eventos.

**Eventos** (mesma dataclass `Event`, novo campo `error`):
`download_started` → `download_progress` (`stage="download"`, `percent` 0–100 ou **-1 = indeterminado**,
`message` com MB) → `download_finished` (`"Download concluído: N vídeo(s)."` + avisos) → eventos
normais da fila (`batch_started`, `file_started`, `progress`, `file_finished`; `path` = vídeo baixado,
`index/total` relativos aos vídeos baixados) → `batch_finished`.
Falha: `download_failed` (`error` e `message` PT) → `batch_finished` (`results=[]`, `error`).
Cancelamento: `batch_finished` com `"Download cancelado."` (ou o resumo normal se já estava extraindo).
**`batch_finished` é sempre o último evento e só é emitido depois de apagar o temporário.**

### Validação de URL

Aceita `http(s)://` (normalizado para `https`), host `instagram.com`, `www.instagram.com` ou
`m.instagram.com` (maiúsculas e ponto final aceitos), caminhos `/p/<código>`, `/reel/<código>`,
`/reels/<código>` (→ `/reel/`), `/tv/<código>` e `/<usuário>/p/<código>`; sem esquema
(`instagram.com/p/...`) recebe `https://`. Query e fragmento são descartados. Resultado:
`https://www.instagram.com/<p|reel|tv>/<código>/`, com código só `[A-Za-z0-9_-]`.

Recusa: outros esquemas (`javascript:`, `file:`, `ftp:`), outros hosts (incl. `instagram.com.evil.com`,
`evilinstagram.com`, `instagrarn.com`, `xn--…`), usuário/senha ou `@` no host, `\`, porta explícita,
espaços/quebras de linha internos, stories/destaques/explorar/`/s/`/`/share/`, perfis e `reels/audio`.

### Execução do yt-dlp (contrato para o yt-dlp falso dos testes)

Processo sem shell, argumentos em lista, `--` antes da URL (sempre a URL **normalizada**):

```
<yt-dlp> --ignore-config --no-cache-dir --no-cookies --no-cookies-from-browser
  --color never --newline --progress
  --progress-template "download:VXPROG %(progress.downloaded_bytes)s %(progress.total_bytes)s %(progress.total_bytes_estimate)s %(info.playlist_index)s %(info.n_entries)s"
  --print "after_move:VXFILE %(filepath)s"
  -P <TEMP> -o "%(id)s.%(ext)s" --restrict-filenames --no-overwrites --no-mtime
  --yes-playlist -I :20 --ignore-no-formats-error
  --socket-timeout 30 --retries 3 --fragment-retries 3
  -f "bv*+ba/b" --merge-output-format mp4 --ffmpeg-location <ffmpeg>
  -- https://www.instagram.com/p/<código>/
```

- `<TEMP>` = `tempfile.mkdtemp(prefix="video-extractor-ig-")` no diretório temporário do sistema.
- **stdout** lido linha a linha: `VXPROG <baixados> <total> <estimado> <índice> <n>` (campos ausentes = `NA`)
  vira `download_progress` (no máx. 10/s); `VXFILE <caminho>` marca um arquivo **concluído**.
- Só são processados caminhos de `VXFILE` que existem, ficam diretamente em `<TEMP>` e não terminam em
  `.part/.ytdl/.temp/.tmp`. **Se o código de saída ≠ 0, nada é processado** (falha classificada pelo stderr).
- Código 0 sem nenhum `VXFILE` → falha `no_video`. Linhas `WARNING:` com `There is no video in this post`
  ou `No video formats found` contam itens só-imagem ignorados.
- Variáveis de ambiente do processo: as do usuário + `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`.
- Os arquivos são renomeados no temporário para `instagram_<código>.<ext>` (carrossel com vários vídeos:
  `instagram_<código>_1`, `_2`…, na ordem do post) e então extraídos.

**Classificação de erros** (linhas `ERROR:` do stderr, sem diferenciar maiúsculas, na ordem):

| `DownloadError.kind` | trechos | mensagem ao usuário (resumo) |
|---|---|---|
| `not_found` | `empty media response` (testado antes de todos) | não encontrada ou indisponível sem login |
| `no_video` | `there is no video in this post`, `no video formats found` | publicação não contém vídeo (apenas imagens) |
| `drm` | `drm` | protegido por DRM |
| `rate_limit` | `rate-limit`, `too many requests`, `http error 429`, `redirected to the login page` | bloqueio temporário do acesso anônimo |
| `login` | `only available for registered users`, `restricted video`, `login`, `log in`, `private`, `cookies` | privada/restrita/exige login |
| `not_found` | `http error 404`, `not found`, `does not exist`, `has been removed`, `is not available`, `content is unreachable` | não encontrada/removida |
| `network` | `unable to download webpage`, `urlopen error`, `name resolution`, `timed out`, `connection refused/reset`, `network is unreachable`, `ssl`, `certificate`, `transporterror`… | falha de rede |
| `unsupported` | `unsupported url` | link não suportado |
| `unknown` | demais | "Falha no download (yt-dlp código N): <última linha ERROR>" |

A mensagem final inclui `(yt-dlp: <última linha ERROR>)` para diagnóstico.

### Política de arquivos

- Tudo é baixado na pasta temporária própria, que é **sempre apagada** ao fim, em falha, em
  cancelamento ou em erro inesperado. Nenhum arquivo do usuário é tocado.
- A extração só começa depois que o yt-dlp termina com código 0 (download completo).
- Por padrão o vídeo original baixado **não é guardado**: ficam só as pastas `NNN` (uma por vídeo
  real, numeração contínua com o resto do destino). O nome `instagram_<código>[_N].mp4` aparece em
  `VideoResult.source` / `Event.path`. Falha de download não cria pasta nem consome número.
- Opcional `keep_video_dir=<pasta>`: o vídeo baixado é movido para lá com nome único, e
  `VideoResult.source` / `job.downloaded` apontam para ele.
- Carrossel: todos os vídeos (até 20 itens) são processados em sequência; imagens são ignoradas com
  aviso; post só com imagens → `download_failed` "A publicação não contém vídeo (apenas imagens)."
- Cancelar mata o processo atual (yt-dlp ou ffmpeg) imediatamente.

## Evidências v3 (execução real, ffmpeg 7.1.1, Python 3.13, Linux, 2026-11-13)

Vídeos sintéticos gerados com `ffmpeg -f lavfi`; fila `run_batch(..., seed=42)` num destino que já
tinha um **arquivo** `001` e uma **pasta** `005`:

| entrada | pasta | resultado |
|---|---|---|
| `corrompido.mkv` (texto) | — | `failed` "Arquivo inválido ou corrompido…", nenhuma pasta criada; fila seguiu |
| `curto.mp4` (H.264+AAC, 0,12 s, 25 fps) | `006` | `success`; 4 JPG 320×240 válidos; aviso "muito curto" (com margem de 1 quadro: 2 imagens distintas) |
| `mudo 10bit.webm` (VP9 yuv420p10le 321×241, sem áudio) | `007` | `no_audio`; `video.mp4` H.264 yuv420p 320×240 (`reencode`); 4 frames 321×241 distintos; **sem** `audio.mp3` |
| `normal com acento ção.mp4` (H.264+AAC 640×360, 12 s) | `008` | `success`, `copy`; frames em 1.255, 3.064, 6.6, 10.428 s, 4 imagens distintas |
| `so audio.m4v` (só AAC) | `009` | `partial`: só `audio.mp3`; "o arquivo não contém trilha de vídeo (video.mp4 e frames não gerados)" |
| `video_menor.mpg` (MPEG-2 + MP2) | `010` | `success`, `reencode` |
| vídeo de 2 s com áudio de 8 s | — | frames só em 0,15–1,46 s (dentro do stream de vídeo), 4 distintos |
| destino = pasta de origem | `in/001` | entrega criada ao lado dos vídeos; SHA-256 de todos os originais inalterado; `list_videos(recursive=True)` não lista `001/video.mp4` |
| cancelar durante áudio, vídeo e frames (VP9 1080p 40 s) | — | `batch_finished` em ~0,00 s; pasta do item removida; itens `cancelled`; nenhum `.part`, nenhum `ffmpeg` vivo |
| Instagram com yt-dlp falso: carrossel misto (2 vídeos + 1 imagem), depois link privado, depois 1 vídeo | `001`, `002`, —, `003` | uma pasta por vídeo real; falha de download não consumiu número; temporário removido |

ffprobe das saídas: `video.mp4` = 1 stream h264 yuv420p, 0 áudio, duração igual à original;
`audio.mp3` = 1 stream mp3, duração ≈ original; `frame_0N.jpg` = mjpeg na resolução do vídeo.

### Evidências — Instagram v2 (2026-11-12; download, antes da v3)

**Rede real (yt-dlp 2026.10.26 num venv isolado, sem login):** links tirados dos casos de teste do próprio yt-dlp.

| link | resultado |
|---|---|
| `https://instagram.com/p/aye83DjauH/?foo=bar#abc` (normalizado) | 1 vídeo baixado → `instagram_aye83DjauH.mp4` H.264 (`copy`); status `no_audio`: no acesso anônimo o Instagram só oferece formatos **sem áudio** para esse post (conferido com `yt-dlp -F` e ffprobe) |
| `https://www.instagram.com/p/BQ0eAlwhDrw/` (carrossel) | 3 vídeos → `instagram_BQ0eAlwhDrw_1..3.mp4`, todos `no_audio` pelo mesmo motivo |
| `https://www.instagram.com/reel/CWqAgUZgCku/` | `download_failed` kind `not_found` ("Instagram sent an empty media response…"), fila não iniciada |
| após as execuções | nenhuma pasta `video-extractor-ig-*` restante |

**Não verificado com o Instagram real:** um vídeo público **com áudio** (MP3 gerado a partir do Instagram),
post só de imagens, carrossel misto, conteúdo privado, limite de requisições e queda de rede. Esses casos
foram verificados com yt-dlp falso (stderr com as mensagens reais do yt-dlp) e extração real via ffmpeg:

| cenário (yt-dlp falso) | resultado |
|---|---|
| 1 vídeo com áudio, 2× | `success` (na v2: `instagram_<c>.mp3/.mp4` e depois `… (1)`; na v3: pastas `NNN` seguintes) |
| carrossel 3 vídeos / misto (1 item sem vídeo) | 3 `success` / 2 `success` + aviso de item ignorado |
| só imagens (exit 0 + `WARNING … There is no video in this post`) | `download_failed` "A publicação não contém vídeo (apenas imagens)." |
| privado / rede (`Temporary failure in name resolution`) / rate-limit | `download_failed` com kind `login` / `network` / `rate_limit` |
| `.part` deixado + exit 1 | `download_failed`; nada processado |
| `keep_video_dir` | vídeo movido para a pasta; `result.source` aponta para ele |
| cancelar durante o download | `batch_finished` "Download cancelado." em ~0,00 s; processo morto; temporário removido |
| URL de outro host / yt-dlp inexistente | `start()` levanta `InvalidInputError` / `DependencyMissingError` |
| yt-dlp **real** com servidor HTTP local (extrator genérico, sem passar pela validação) | argv aceito; `VXPROG`/`VXFILE` no formato acima; 404 → `not_found` |

Validação de URL: 7 formas válidas normalizadas e 19 inválidas recusadas (lista na seção acima).
(As regras de URL, yt-dlp e temporário não mudaram na v3; a v3 só troca o destino das saídas.)

## Limitações conhecidas

- Apenas a **primeira** trilha de áudio vira MP3; legendas e trilhas extras são descartadas.
- Vídeos não-H.264 (VP9, HEVC, MPEG-2...) são recodificados: mais lento e com perda leve. HEVC não é
  copiado de propósito (compatibilidade com players).
- Progresso depende da duração informada pelo arquivo; sem duração, só 0%/100% por etapa.
- Ao cancelar, a pasta do item em andamento é descartada inteira, mesmo que o `audio.mp3` dela já
  estivesse pronto (política: não entregar pasta incompleta). Pastas de itens concluídos ficam.
- Frames de vídeos muito curtos (poucos quadros) podem ser imagens iguais; de vídeos sem duração
  conhecida, os 4 vêm do início.
- Os instantes dos frames são sorteados (não buscam "cenas" nem evitam quadros pretos).
- Numeração: o número de uma pasta `failed`/`cancelled` removida pode ser reutilizado pelo próximo item.
- `list_videos` filtra por extensão; arquivos com extensão de vídeo mas inválidos falham individualmente.
- Nomes muito longos (>~250 bytes) podem falhar conforme o sistema de arquivos.
- **Instagram:** só conteúdo público acessível sem login; o Instagram muda com frequência e pode
  bloquear acesso anônimo (rate-limit) ou responder vazio, então mantenha o yt-dlp atualizado. Em alguns
  posts o acesso anônimo só oferece vídeo **sem áudio**: nesse caso `audio.mp3` não é gerado (`no_audio`).
  Carrossel limitado a 20 itens. Formatos com vídeo e áudio separados são unidos pelo yt-dlp com o ffmpeg.
- Testes de rede real dependem de conexão e do comportamento atual do Instagram; não fazem parte da
  suíte automática.
