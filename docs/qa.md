# QA — Extrator de Vídeos

> **Estado atual: v4** — reestilização visual inspirada em sharkbot.com.br **sem mudança de
> funcionalidade**. O comportamento validado na **v3** (destino único, uma pasta numerada por
> vídeo com `audio.mp3`, `video.mp4` sem áudio e `frames/` com 4 JPGs) continua valendo e foi
> revalidado sobre a UI v4. As seções **v2** e **v1** são histórico.

## v4 — reestilização visual (referência sharkbot.com.br)

Dono: testador (dispatch `ctx_9467e1fc07dc`). Data: 2026-11-13. Estado validado:
`extractor/ui.py` md5 `d41946db608a50201dcca507b86f3c76` (última alteração do frontend),
`extractor/engine.py` md5 `55f8ade14613f8088b6c3ea5ca1a01a5` (**intocado** desde a v3),
`extractor/__init__.py` `d33148457b6002f8e25fa5d068090713`. Hashes de `extractor/` e `tests/`
idênticos antes e depois da suíte final.

### Resultado final

```
$ python3 -W always::ResourceWarning -m unittest discover -s tests -v
Ran 117 tests in 372.550s
OK (skipped=1)
```

| Suíte | Tipo | Testes | OK | Falhas | Skips |
|-------|------|-------:|---:|-------:|------:|
| `tests/test_engine_real.py` | FFmpeg **real** | 44 | 44 | 0 | 0 |
| `tests/test_ui_integration.py` | UI na tela real + FFmpeg real | 12 | 12 | 0 | 0 |
| `tests/test_instagram_url.py` | validação de URL (pura) | 5 | 5 | 0 | 0 |
| `tests/test_instagram_download.py` | downloader **simulado** + FFmpeg real | 26 | 26 | 0 | 0 |
| `tests/test_ui_v2.py` | UI real + downloader simulado + FFmpeg real (inclui contraste WCAG) | 14 | 14 | 0 | 0 |
| `tests/test_ui_v4_visual.py` | **novo** — UI v4 na tela real (layout, estados, foco, tamanhos) | 15 | 15 | 0 | 0 |
| `tests/test_instagram_live.py` | yt-dlp e Instagram **reais** (opt-in) | 1 | — | — | 1 (pulado sem `VIDEO_EXTRACTOR_LIVE=1`) |
| **Total** | | **117** | **116** | **0** | **1** |

Nenhum teste existente foi alterado ou afrouxado: os 102 testes da v3 rodaram como estavam
(inclusive os de contraste WCAG ≥ 4,5:1 de `test_ui_v2`, que passaram com a paleta nova). Depois
da suíte: 0 `ResourceWarning`, 0 processos `ffmpeg`, 0 processos do yt-dlp falso, 0 pastas
`video-extractor-ig-*`, 0 arquivos `.part`.

**Regressão FFmpeg real fora da suíte** (`python3 tests/qa_evidence.py <pasta>` no estado final):
`01 Férias ação.mp4` → `001/` (`audio.mp3` 6,06 s mp3, `video.mp4` 6,00 s h264 sem áudio,
4 JPGs 160×120 em 0,36/2,36/3,19/5,75 s); `02 corrompido.mp4` → `failed`, sem pasta;
`03 sem áudio.mp4` → `002/` sem `audio.mp3` com aviso; `04 vp9 opus.webm` → `003/` completo;
originais intactos (sha256). Instagram simulado (carrossel → uma pasta por vídeo, numeração
contínua, erros sem pasta) coberto por `test_instagram_download` e `test_ui_v2` acima.

### Referência inspecionada (navegador real)

`https://sharkbot.com.br` aberto no navegador embutido do Orca (1280×900), screenshot
`docs/qa-screens/v4_referencia_sharkbot.png`; valores por `getComputedStyle` e amostragem de
pixels: fundo `#050505`/`#000`, cartões `#111111`, bordas branco 8 %, texto branco e
secundário branco 70 %/50 %, primário azul sólido `#3b82f6` (raio 8–12 px, texto 600),
secundário “ghost” (transparente + borda fina), pílulas com borda colorida, verde `#22c55e`,
roxo `#8b5cf6`. Não se copiou marca/conteúdo. Branco sobre `#3b82f6` dá só 3,68:1, por isso
o app usa `#2563eb` (5,17:1) no fundo do botão com texto e `#3b82f6` só na barra de progresso.

### Avaliação visual (screenshots reais, `ffmpeg -f x11grab -window_id`)

| Critério | Resultado |
|----------|-----------|
| Cores | fundo `#050505`, superfícies `#0b0b0c`/`#141416`, texto `#fff`, apoio `#a1a1aa`, azul `#2563eb`/`#60a5fa` — coerente com a referência |
| Hierarquia / botões | primário azul sólido só em **Baixar e extrair** e **▶ Iniciar fila**; secundários com contorno; ações de fila “ghost”; **Cancelar** com texto vermelho; seções sem cartão com divisória fina e pílula “PASSO N” (como as pílulas da referência) |
| Contraste | todos os pares texto/fundo ≥ 4,5:1 (menor 5,19:1); texto de botão ≥ 4,5:1 em normal/hover/pressionado/foco; status distintos e ≥ 4,5:1 também sobre a linha selecionada |
| Foco | contorno `#60a5fa` ≥ 3:1 sobre fundo e superfície (WCAG 1.4.11) em botões e campos |
| Desabilitado | visivelmente diferente do habilitado (`#71717a`; sobre o azul desabilitado 3,59:1 — WCAG isenta desabilitados) |
| Tamanho padrão | 1040×820 em tela 1920×1080: nenhum controle/texto cortado, fila com 9 linhas |
| Tamanho mínimo | 820×680: nenhum controle/texto cortado, fila com 4 linhas, Iniciar/Cancelar visíveis |
| Tela 1366×768 | Xwayland rootful 1366×768 **real**: janela abre 1040×680 e cabe inteira (sobram 88 px para título/barra do sistema) |
| Caminhos longos | janela não cresce; destino mostra o **final** do caminho, inclusive depois de redimensionar |
| Dependências | só biblioteca padrão/Tkinter (verificado por AST); sem imagens/fontes externas nem rede; fontes com fallback |

Arquivos em `docs/qa-screens/`:

- `v4_referencia_sharkbot.png` — referência real (topo da página).
- `v4_vazia.png` — janela padrão vazia (1040×820).
- `v4_rodando.png` — processando: “Extraindo frames 75 %”, coluna PASTA `001`, Cancelar ativo.
- `v4_concluida.png` — fila mista com caminhos longos: `001`, `002`, `003` sem áudio (âmbar), corrompido sem pasta (vermelho), `004`.
- `v4_minimo_820x680.png` — mesma fila no tamanho mínimo.
- `v4_tela_1366x768.png` — captura da **tela inteira** 1366×768 com a janela aberta (fila concluída).
- `v4_tela_1366x768_antes_correcao.png` — evidência do achado F2 (antes da correção).
- Os screenshots `v3_*` ficam como “antes”.

### Novo teste `tests/test_ui_v4_visual.py` (15)

Layout (7): nenhum botão/checkbutton/label/campo/árvore fora da janela, recortado pelo
contêiner ou com texto maior que o espaço, no tamanho padrão e no mínimo, com fila vazia e
com caminhos longos; fila ≥ 5 linhas no padrão e ≥ 4 no mínimo; `minsize` cabe em 1366×768
(≤ 689 px de altura útil); janela inicial cabe na tela; caminhos longos não aumentam a janela
e o destino mostra o fim do caminho, inclusive depois de redimensionar. Estados (5): contraste
do texto dos botões por estado, desabilitado distinguível, foco ≥ 3:1, cores de status,
hierarquia/coerência com a referência (fundo quase preto, primário azul saturado ≥ 3:1 sobre
fundo e cartão, diferente dos secundários). Placeholder do link (1): diálogo **real** de pasta
do Tk com o campo focado não gera exceção e a dica volta. Dependências (2): só stdlib, sem rede
nem assets pesados. Os testes não amarram nomes de estilo nem cores exatas.

### Achados v4

| # | Severidade | Dono | Descrição | Estado |
|---|-----------|------|-----------|--------|
| A1 | média | frontend | (já na v3) no mínimo 820×640 a fila sumia e Iniciar/Cancelar/status ficavam recortados embaixo | corrigido; teste de layout no mínimo passa |
| A2 | baixa | frontend | (já na v3) textos com `wraplength` fixo cortados na borda direita no mínimo | corrigido (`<Configure>` + textos menores) |
| A3 | baixa | frontend | (já na v3) destino deixava de mostrar o fim do caminho após redimensionar | corrigido |
| F1 | média | frontend | placeholder novo do link usava `focus_get()`: com o campo focado, abrir o diálogo real de pasta do Tk gerava `KeyError('__tk_choosedir')` em callback e a dica não voltava | corrigido (foco consultado pelo nome Tcl); teste dedicado passa |
| F2 | média | frontend | `minsize` 820×720 + título não cabia em 1366×768; janela abria 1040×820 com Iniciar/Cancelar abaixo da borda (evidência Xwayland) | corrigido: mínimo 820×680 e tamanho inicial limitado à tela (1040×680 em 1366×768) |
| B1/B2 | baixa | frontend (achado do backend) | dica do yt-dlp dizia sempre “não encontrado”; subtítulo prometia MP3 para todo vídeo | corrigidos; textos revisados nos screenshots |
| v4-1 | info | — | no tamanho mínimo a coluna ARQUIVO corta nomes longos sem reticências; nome completo no detalhe (duplo clique) e na barra de status durante o processamento | aceito (comportamento do Treeview) |

### Limitações v4

- A referência foi inspecionada só no topo da página (hero/cabeçalho): as seções de baixo usam
  animação ao rolar e não renderizaram na aba de fundo do navegador embutido (screenshots
  pretos); a paleta das demais seções foi lida do DOM (`getComputedStyle`).
- 1366×768 foi testado com Xwayland rootful **sem gerenciador de janelas** (sem barra de título
  real); a margem para título/barra do sistema (88 px) foi calculada, não medida com GNOME/Windows
  nessa resolução. Escala de DPI ≠ 100 % e Windows/macOS não testados.
- Contraste medido pelas constantes/estilos ttk e conferido visualmente; não foi feita medição
  automática por pixel de cada estado (hover/pressionado vistos só nos estilos).
- Diálogos nativos substituídos nos testes de fluxo (o teste F1 usa o diálogo real do Tk).
- Instagram real não reexecutado nesta rodada (sem mudança no engine); limitações da v3 valem.

### Como rodar (v4)

```sh
python3 -m unittest discover -s tests -v              # tudo (ffmpeg + tela)
python3 -m unittest -v tests.test_ui_v4_visual        # só o visual v4
python3 tests/qa_evidence.py /tmp/qa-evidencia         # árvore real + ffprobe + sha256
# tela 1366x768 simulada (abre uma janela Xwayland):
Xwayland :57 -geometry 1366x768 -decorate & DISPLAY=:57 python3 main.py
```

---

## v3 — destino único com pastas numeradas

Dono: testador (dispatch `ctx_2e1d192f7270`). Data: 2026-11-13. Estado validado:
`extractor/engine.py` 2026-11-13 15:27, `extractor/ui.py` 15:31 (última alteração integrada).

### Estrutura esperada (requisito)

```
<destino>/001/audio.mp3            MP3 do áudio (ausente se o vídeo não tem áudio; nunca vazio)
<destino>/001/video.mp4            MP4 só com vídeo (0 streams de áudio)
<destino>/001/frames/frame_01.jpg … frame_04.jpg   4 quadros de instantes aleatórios
<destino>/002/…                    próximo vídeo real (carrossel do Instagram: uma pasta por vídeo)
```

### Resultado final

```
$ python3 -W always::ResourceWarning -m unittest discover -s tests -v
Ran 102 tests in 271.268s
OK (skipped=1)
```

| Suíte | Tipo | Testes | OK | Falhas | Skips |
|-------|------|-------:|---:|-------:|------:|
| `tests/test_engine_real.py` | FFmpeg **real** | 44 | 44 | 0 | 0 |
| `tests/test_ui_integration.py` | UI na tela real + FFmpeg real | 12 | 12 | 0 | 0 |
| `tests/test_instagram_url.py` | validação de URL (pura) | 5 | 5 | 0 | 0 |
| `tests/test_instagram_download.py` | downloader **simulado** + FFmpeg real | 26 | 26 | 0 | 0 |
| `tests/test_ui_v2.py` | UI real + downloader simulado + FFmpeg real | 14 | 14 | 0 | 0 |
| `tests/test_instagram_live.py` | yt-dlp e Instagram **reais** (opt-in) | 1 | — | — | 1 (módulo pulado sem `VIDEO_EXTRACTOR_LIVE=1`) |
| **Total** | | **102** | **101** | **0** | **1** |

Depois da suíte: 0 `ResourceWarning`, 0 processos `ffmpeg`, 0 processos do yt-dlp falso,
0 pastas `video-extractor-ig-*` no temp, 0 arquivos `.part`.

**Rede real (opt-in, executado separadamente, passou):** yt-dlp 2026.10.26 instalado com
`python3 -m venv <venv> && <venv>/bin/python -m pip install -r requirements-instagram.txt`;
`VIDEO_EXTRACTOR_LIVE=1 VIDEO_EXTRACTOR_YTDLP=<venv>/bin/yt-dlp python3 -m unittest -v tests.test_instagram_live` → `OK`:

```
/tv/aye83DjauH/    pasta=001  no_audio  MP4 8.74s sem áudio, frames 1.83s 4.31s 4.40s 6.89s 640x640
/p/BQ0eAlwhDrw/    pasta=001  no_audio  MP4 4.00s  frames 0.03s 1.35s 2.16s 3.34s 640x640
 (carrossel)       pasta=002  no_audio  MP4 31.70s frames 4.17s 14.70s 16.82s 25.42s 640x640
                   pasta=003  no_audio  MP4 6.51s  frames 1.05s 2.52s 3.85s 5.82s 640x640
aviso: "O vídeo não possui trilha de áudio; audio.mp3 não foi gerado."  (os 4 JPGs decodificam limpo)
```

**Evidência de estrutura real** (`python3 tests/qa_evidence.py <pasta>`; fila carregada por `list_videos`):

```
[success]  01 Férias ação.mp4 -> 001   audio.mp3 6.060s [audio:mp3]   video.mp4 6.000s [video:h264]
           frames 160x120 mjpeg em 0.757s 2.408s 4.372s 5.134s
[failed]   02 corrompido.mp4  -> (sem pasta, não consome número) 'Arquivo inválido ou corrompido … moov atom not found'
[no_audio] 03 sem áudio.mp4   -> 002   (sem audio.mp3)  video.mp4 2.000s [video:h264]
           frames 160x120 em 0.386s 0.917s 0.994s 1.681s
[success]  04 vp9 opus.webm   -> 003   audio.mp3 2.040s  video.mp4 2.000s (recodificado)
           frames 320x240 em 0.363s 0.843s 1.304s 1.480s
árvore: 001/{audio.mp3,video.mp4,frames/frame_01..04.jpg} 002/{video.mp4,frames/…} 003/{…}
originais intactos (sha256 antes == depois): True
```

`docs/qa-screens/v3_frames_001.png` junta os 4 JPGs da pasta 001: o contador do `testsrc`
mostra **0, 2, 4, 5 s**, coerente com os instantes informados (0.76/2.41/4.37/5.13 s).

### O que é real e o que é simulado

| Camada | Como | Real? |
|--------|------|-------|
| MP3, MP4 sem áudio, frames JPG, numeração, limpeza | engine real + ffmpeg/ffprobe 7.1.1 sobre vídeos `ffmpeg -f lavfi`; saídas por ffprobe, decodificação completa (`ffmpeg -f null`), frames comparados pixel a pixel com o quadro de referência | **real** |
| Falha só na etapa de frames | ffmpeg **real** embrulhado por um script do teste que recusa só comandos que gravam `.jpg` (injeção de falha) | real, com falha injetada |
| Download do Instagram nos testes automáticos | `tests/fake_ytdlp.py` (gera vídeos reais com ffmpeg, mensagens reais de erro do yt-dlp) | **simulado** só na fronteira de rede |
| Instagram de verdade | `tests/test_instagram_live.py` opt-in | **real** (executado) |
| UI | Tk na tela real `:0` (XWayland), botões `.invoke()`, engine real | real (diálogos nativos substituídos) |

### Cobertura v3

**Estrutura/conteúdo** (`test_engine_real`): H.264+AAC, VP9+Opus, MPEG-4 AVI, MKV, 640×360,
7 s; conteúdo exato de `NNN/` (`audio.mp3`, `video.mp4`, `frames/`), MP3 1 stream mp3 com
duração ≈ original, MP4 0 áudio/1 vídeo, 4 JPGs `mjpeg` com as dimensões do vídeo e
decodificáveis; aliases `mp3_path/mp4_path/frames`; API sem `mp3_dir/mp4_dir`.

**Frames:** instantes crescentes, em `[0, duração)`, um por quarto do intervalo seguro e
distintos (vídeo de 8 s); **aleatoriedade testável sem flaky**: mesma `seed` → mesmos
instantes, `seed` diferente → instantes diferentes, `rng=random.Random(42)` ≡ `seed=42`,
sem seed (SystemRandom) duas execuções diferem; **cada JPG corresponde ao quadro de
referência no instante informado** (distância de pixels menor que a de qualquer outro
instante a > 0,5 s) e os 4 JPGs diferem entre si; vídeo de 0,3 s e de 1 quadro (0,04 s) →
sempre 4 JPGs válidos.

**Numeração/não sobrescrita:** fila → 001, 002, 003; nova execução continua (004…) sem
alterar nenhum arquivo anterior (sha256); existentes `001`, `005`, **arquivo** `007`, `abc`,
`01a` → próxima `008`, lacunas não reaproveitadas, nada existente tocado; `next_output_folder`
só consulta; `999` → `1000`; inválido não consome número; **duas filas simultâneas** no mesmo
destino → 001–006 sem colisão; destino = origem → pastas dentro da origem, originais
intactos, `list_videos` (inclusive recursivo) não pega as saídas e nova execução vira 003/004;
destino arquivo/sem permissão → `InvalidInputError`; destino aninhado inexistente é criado.

**Falhas e cancelamento:** fila mista `[success, failed, no_audio, success, success]` →
pastas `001, —, 002, 003, 004`, eventos com `folder` e etapa `frames`; mudo → `no_audio` sem
MP3; só áudio → `partial` só com `audio.mp3`; falha injetada nos frames → `partial` com
áudio+vídeo válidos e sem lixo em `frames/`, fila continua; cancelamento **na etapa frames**
e na etapa áudio (disparado de forma determinística pelo próprio evento de progresso) →
item atual e seguintes `cancelled`, pasta do item atual removida, item anterior intacto, sem
`.part`; `BatchProcessor` cancelado no meio de VP9 → destino vazio.

**Instagram (simulado + FFmpeg real):** link → `001/` completo; mesmo link de novo → `002`,
`003` sem tocar `001`; destino com espaço/acento/CJK; vídeo baixado mudo → `no_audio`;
carrossel → uma pasta por vídeo; carrossel depois de uma fila local continua a numeração
(002, 003); erros de download (privado, rede, só imagens, exit ≠ 0, `VXFILE` fora do temp)
não criam pasta nem consomem número; cancelamento no download, na extração e **nos frames
do 2º vídeo do carrossel** (fica só `001`); temp sempre limpo; validação de URL/argv seguro
como na v2.

**UI (tela real):** exatamente **um** `FolderPicker` (sem seletores MP3/MP4); fluxo por
botões: carregar pasta → escolher destino → Iniciar → coluna **PASTA** `001/—/002/003`,
detalhe `001/: audio.mp3, video.mp4, 4 frames`, mudo com aviso de áudio, falha sem pasta;
“Abrir pasta do item” abre `…/002` e fica desabilitado para item sem pasta; segunda execução
→ `003/004` sem sobrescrever; destino = origem; sem destino → aviso; destino arquivo → erro;
cancelar remove a pasta do item atual e a pasta aparece na coluna já durante o processamento;
link → `001`; carrossel → filhas `001`, `002` e pai `001–002`; link durante fila local →
`003`; tema escuro/contraste e FFmpeg/yt-dlp ausentes como na v2.

### Screenshots (tela real, `ffmpeg -f x11grab -window_id`)

- `docs/qa-screens/v3_vazia.png` — janela 1040×820: cartão 2 “Pasta de destino” com **um**
  seletor e a explicação da estrutura.
- `docs/qa-screens/v3_rodando.png` — durante o carrossel: coluna PASTA `001`, etapa “Gerando vídeo”.
- `docs/qa-screens/v3_concluida.png` — fila mista + link: `003` concluído, quebrado sem pasta,
  `004` sem áudio, link `001–002` com filhas `001` e `002`.
- `docs/qa-screens/v3_frames_001.png` — os 4 JPGs de uma pasta.

### Achados v3

Nenhum bug encontrado na integração final: as suítes migradas passaram contra o engine e a UI
v3 na primeira execução depois da integração. Observações (não bloqueantes):

| # | Tipo | Observação |
|---|------|------------|
| v3-1 | comportamento | Ao colar um link com a fila ociosa, o download começa na hora; vídeos locais adicionados depois recebem números seguintes (no screenshot o carrossel ficou com 001–002 e os locais com 003/004). A numeração segue a ordem de **processamento**, não a ordem das linhas. |
| v3-2 | comportamento | Vídeos muito curtos (< ~0,5 s) geram 4 JPGs válidos, mas alguns podem ser imagens iguais (contrato; o backend emite aviso “muito curto”). |
| v3-3 | teste | O scratchpad de testes foi limpo entre sessões (venv e screenshots v2 sumiram); venv reinstalado pelo `requirements-instagram.txt`; screenshots v2 substituídos pelos v3 em `docs/qa-screens/`. |

### Limitações v3

- Instagram real: os posts públicos disponíveis (da suíte de testes do próprio yt-dlp) só têm
  formatos sem áudio no acesso anônimo → `audio.mp3` a partir de link **real** não foi
  demonstrado (foi com o downloader simulado). Post real com áudio, só-imagens, privado e
  rate-limit não foram exercitados de verdade; nenhum login usado.
- Diálogos nativos substituídos; Windows/macOS e `run.bat` não testados.
- Vídeos de teste curtos e pequenos (até 640×480 / 20 s); arquivos longos/4K não medidos.
- Duração desconhecida (contrato: 4 frames em t=0 + aviso) não foi exercitada.

### Como rodar (v3)

```sh
python3 -m unittest discover -s tests -v                    # tudo (precisa de ffmpeg e de tela)
python3 -m unittest -v tests.test_engine_real               # engine v3, sem tela
python3 tests/qa_evidence.py /tmp/qa-evidencia              # árvore real + ffprobe + sha256
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-instagram.txt
VIDEO_EXTRACTOR_LIVE=1 .venv/bin/python -m unittest -v tests.test_instagram_live   # rede real
./run.sh        # abre o app (usa .venv se existir); sem venv: python3 main.py
```

---

## v2 — tema escuro e link do Instagram

Dono: testador (dispatch `ctx_f6f8d29e07cb`). Data: 2026-11-12.

### O que é real e o que é simulado

| Camada | Como foi testado | Real? |
|--------|------------------|-------|
| Extração FFmpeg (MP3, MP4 sem áudio, nomes, colisões, limpeza) | engine real + ffmpeg/ffprobe 7.1.1 sobre vídeos gerados por `ffmpeg -f lavfi`; saídas inspecionadas com ffprobe e decodificadas por inteiro | **real** em todos os testes |
| Validação de URL | função pura `validate_instagram_url` / `is_instagram_url` | **real** (sem rede) |
| Fronteira de rede (yt-dlp) nos testes automáticos | `tests/fake_ytdlp.py` via `VIDEO_EXTRACTOR_YTDLP`: imita o CLI do contrato (argv, `VXPROG`/`VXFILE`, mensagens `ERROR:` reais do yt-dlp) e **gera vídeos reais com ffmpeg**; modos ok, carrossel, sem áudio, privado, login, rede, 404, 429, unsupported, desconhecido, só imagens, lento (cancelamento), `.part`+exit 1, exit 0 sem arquivo, caminho fora do temp, processo que demora a sair | **simulado** (downloader); tudo depois do download é real |
| yt-dlp + Instagram de verdade | `tests/test_instagram_live.py` (opt-in), yt-dlp 2026.10.26 instalado num venv pelo `requirements-instagram.txt` | **real**, executado manualmente — ver resultados |
| UI | Tk na tela real `:0` (XWayland), botões reais `.invoke()`, engine real, downloader falso; screenshots com `ffmpeg -f x11grab -window_id` | **real** (diálogos nativos substituídos) |

### Como rodar (v2)

```sh
# suíte completa: v1 + v2 (precisa de ffmpeg/ffprobe e de uma tela; o teste de rede real é pulado)
python3 -m unittest discover -s tests -v

# só download/URL (sem tela)
python3 -m unittest -v tests.test_instagram_url tests.test_instagram_download

# só UI v2 (tela real)
python3 -m unittest -v tests.test_ui_v2

# rede REAL (opt-in): instala o yt-dlp opcional num venv e roda contra posts públicos
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-instagram.txt
VIDEO_EXTRACTOR_LIVE=1 .venv/bin/python -m unittest -v tests.test_instagram_live
#   opcional: VIDEO_EXTRACTOR_LIVE_URLS="https://www.instagram.com/p/<código>/ ..."

# lançar o app com suporte a links (run.sh usa .venv automaticamente se existir)
./run.sh            # ou .venv/bin/python main.py ; sem venv: python3 main.py (só arquivos locais)
```

### Resultados v2

Execução final sobre o estado integrado (engine.py 20:00, ui.py 20:01, depois das últimas correções):

```
$ python3 -W always::ResourceWarning -m unittest discover -s tests -v
Ran 92 tests in 180.849s
OK (skipped=1)
```

| Suíte | Tipo | Testes | OK | Falhas | Skips |
|-------|------|-------:|---:|-------:|------:|
| `tests/test_engine_real.py` (v1) | FFmpeg real | 37 | 37 | 0 | 0 |
| `tests/test_ui_integration.py` (v1) | UI real + FFmpeg real | 12 | 12 | 0 | 0 |
| `tests/test_instagram_url.py` | validação pura | 5 | 5 | 0 | 0 |
| `tests/test_instagram_download.py` | downloader simulado + FFmpeg real | 24 | 24 | 0 | 0 |
| `tests/test_ui_v2.py` | UI real + downloader simulado + FFmpeg real | 13 | 13 | 0 | 0 |
| `tests/test_instagram_live.py` | rede/yt-dlp reais (opt-in) | 1 | — | — | 1 (módulo pulado por padrão) |
| **Total** | | **92** | **91** | **0** | **1** |

- 0 `ResourceWarning`; após a suíte: 0 processos `ffmpeg`, 0 processos do yt-dlp falso, 0 pastas
  `video-extractor-ig-*` no temp.

**Rede real (opt-in, executado):**
`VIDEO_EXTRACTOR_LIVE=1 VIDEO_EXTRACTOR_YTDLP=<venv>/bin/yt-dlp python3 -m unittest -v tests.test_instagram_live`
→ `Ran 1 test … OK`, yt-dlp 2026.10.26 (instalado com
`python3 -m venv <venv> && <venv>/bin/python -m pip install -r requirements-instagram.txt`, Python 3.13):

```
https://www.instagram.com/tv/aye83DjauH/   -> instagram_aye83DjauH.mp4     no_audio  MP4 8.74s sem áudio
https://www.instagram.com/p/BQ0eAlwhDrw/   -> instagram_BQ0eAlwhDrw_1.mp4  no_audio  MP4 4.00s sem áudio
                                           -> instagram_BQ0eAlwhDrw_2.mp4  no_audio  MP4 31.70s sem áudio
                                           -> instagram_BQ0eAlwhDrw_3.mp4  no_audio  MP4 6.51s sem áudio
aviso: "O vídeo não possui trilha de áudio; o MP3 não foi gerado."   (nenhum MP3 vazio criado)
```

`yt-dlp -F -- https://www.instagram.com/tv/aye83DjauH/` sem login lista só formatos
`video only` — a falta de áudio vem do Instagram, não do app. Nenhuma pasta temporária restou.

**Launcher:** numa cópia do projeto com `.venv` → venv do yt-dlp, `./run.sh` usa
`.venv/bin/python` e `check_downloader()` retorna `ok=True, 2026.10.26`; `timeout 6 ./run.sh`
fica com a janela aberta (exit 124). `pip install --user` no Python do sistema falha aqui com
`externally-managed-environment` (PEP 668) — por isso a instrução documentada é o venv.

**Veredito v2: apta. Nenhum bug bloqueante aberto.**

### Cobertura v2

**`tests/test_instagram_url.py`** (5 testes, 12 URLs válidas e 31 inválidas em subTests):
aceita `/p/`, `/reel/`, `/reels/`, `/tv/`, `/<usuário>/p/`, sem `www`, `m.`, maiúsculas,
`http`, query/fragmento, espaços nas pontas → normaliza para `https://www.instagram.com/...`;
recusa hosts parecidos (`instagram.com.evil.com`, `evilinstagram.com`, `instagram.evil.com`,
`instagrarn.com`, punycode), `@`/userinfo, porta, `ftp:`/`file:`/`javascript:`, perfis,
stories, explore, `..`, espaços/quebras internas, args que parecem opções (`--exec`, `-o`),
metacaracteres de shell (`;`, `$( )`, crases), YouTube. `is_instagram_url` nunca levanta.

**`tests/test_instagram_download.py`** (24 testes, downloader controlado + FFmpeg real):
yt-dlp ausente/quebrado → `ok=False` sem exceção, local continua funcionando, link recusado
antes de criar thread/temp; argv em lista com `--` e só a URL normalizada depois dele,
`--ignore-config`/`--no-cookies`, `-P` = temp `video-extractor-ig-*`; metacaracteres não
chegam a nenhum processo; extração só depois do yt-dlp **sair** (marcador de tempo);
colisões `(1)`/`(2)` sem sobrescrever; pastas com espaço/acento/CJK; `keep_video_dir` mantém o
vídeo com áudio; vídeo baixado sem áudio → `no_audio` sem MP3; carrossel com 2 vídeos;
`download_instagram` publica com nome único; classificação de erros
(login/rede/404/429/unsupported/desconhecido/só imagens) sem temp restante; eventos
`download_failed` → `batch_finished` sem saídas; exit ≠ 0 com arquivo pronto → nada processado;
exit 0 sem arquivo → `no_video`; `VXFILE` fora do temp ignorado e não tocado; validação de URL,
pastas e ffmpeg antes de chamar o yt-dlp; cancelamento no download (< 2 s, processo morto,
sem temp), no download síncrono (`CancelledError`) e durante a extração.

**`tests/test_ui_v2.py`** (13 testes, tela real): fundo e Treeview escuros; contraste WCAG ≥ 4.5:1
de `text`, `muted` e todas as cores de status sobre `bg/surface/surface_2/field/select`, e
`accent_text` sobre `accent`; cores reais dos estilos ttk; botão “Baixar e extrair”
desabilitado sem texto → link colado com espaços/query → download → extração automática,
campo limpo, loop Tk < 0,5 s; Enter envia; links inválidos/maliciosos recusados com aviso e
sem linha; sem pastas de saída → recusa; link adicionado durante lote local roda depois e o
lote local continua correto (`success/failed/no_audio`); mesmo link 2× → `(1)`; link sem
áudio → “Concluído (sem áudio)” e nenhum MP3; privado/rede/só imagens → “Falhou” com
detalhe; cancelar download < 3 s; sem yt-dlp → aviso no card, link recusado, fila local ok.

**Regressão v1**: `tests/test_engine_real.py` (37) e `tests/test_ui_integration.py` (12) sem
alteração de comportamento. Ajuste de teste: o teste da tecla Delete agora faz `focus_force()`
e, se o compositor Wayland negar foco à janela de teste, chama o mesmo handler ligado ao
`<Delete>` (o bind é verificado).

### Layout (screenshots)

Capturados com `ffmpeg -f x11grab -window_id <id> -i :0 -frames:v 1` (a v1 não tinha
captura; `x11grab` por janela funciona no XWayland). Janela padrão 1040×820 (mín. 820×640):
título, subtítulo e três cartões numerados (1 Adicionar vídeos + campo de link, 2 Pastas de
saída, 3 Fila e andamento) sobre fundo `#121419`, cartões `#1b1e25`, ação primária azul
`#3366dd` com texto branco, status coloridos (verde/âmbar/vermelho claro). Arquivos:
`ui_vazia.png` e `ui_concluida.png` (substituídos pelos screenshots v3 em `docs/qa-screens/`).

### Achados v2

| # | Severidade | Dono | Descrição | Estado |
|---|-----------|------|-----------|--------|
| v2-1 | média | backend | dica de instalação do yt-dlp (mostrada na UI) mandava `python3 -m pip install --user -U yt-dlp`, que falha no Ubuntu/Python 3.13 do sistema (PEP 668) e contradizia o README | corrigido: agora indica venv + `requirements-instagram.txt` + `./run.sh` (ou pipx/brew/winget); revalidado |
| v2-2 | baixa | frontend | na geometria padrão a fila mostrava só ~3 linhas | corrigido: 1040×820, Treeview com 8 linhas, botões no cabeçalho do cartão 3; screenshot mostra 6 linhas usadas e sobra |
| v2-3 | baixa | frontend | campos de pasta mostravam o início de caminhos longos | corrigido (`xview_moveto(1)`); conferido via seletor com a janela visível: `xview()=(0.58, 1.0)`. No screenshot `ui_concluida.png` as pastas foram definidas por código logo após abrir a janela e aparecem pelo início — cosmético, não ocorre no fluxo normal |
| v2-4 | info | backend | mensagem real e ambígua do yt-dlp “rate-limit reached or login required” é classificada como `rate_limit` (“bloqueio temporário do acesso anônimo”) | aceito; teste admite `login` ou `rate_limit` |
| v2-5 | — (teste) | QA | teste da tecla Delete falhava quando o Wayland não dava foco à janela de teste | corrigido em `tests/` (focus_force + fallback ao handler do bind) |

### Limitações v2

- **Instagram real só sem áudio**: os posts públicos testados (`/tv/aye83DjauH/` e o carrossel
  `/p/BQ0eAlwhDrw/`, ambos da suíte de testes do próprio yt-dlp) só oferecem formatos
  *video only* no acesso anônimo (`yt-dlp -F` confirma). O caminho “MP3 a partir de link
  real” **não** foi demonstrado com rede real; foi demonstrado com o downloader controlado.
  Post público com áudio, post só de imagens, privado e rate-limit **reais** não foram
  exercitados (não há link público conhecido para isso; nenhum login foi usado).
- O Instagram muda com frequência; o teste de rede real pode passar a falhar sem mudança no app.
- yt-dlp atual exige Python 3.11+; o app local continua 3.8+.
- Diálogos nativos substituídos nos testes (como na v1). Windows/macOS não testados.

---

## v1 — fila local

Dono: testador (dispatch `ctx_394eefa739c6`). Os testes estão em `tests/` e usam apenas
`unittest` da biblioteca padrão. **Nenhuma extração é mockada**: cada teste gera vídeos
sintéticos com `ffmpeg -f lavfi` (testsrc + seno 440 Hz), roda o engine/UI reais e
inspeciona as saídas com `ffprobe` (e decodifica tudo com `ffmpeg -f null` para garantir
que o arquivo é legível de ponta a ponta).

### Ambiente da validação

| Item | Valor |
|------|-------|
| SO | Linux 6.17 (Ubuntu), sessão Wayland com XWayland (`DISPLAY=:0`) |
| Python / Tk | 3.13.7 / Tk 8.6 |
| FFmpeg / FFprobe | 7.1.1 (libx264, libmp3lame, libvpx-vp9, libopus) |
| Xvfb | não instalado — não foi necessário, a UI rodou na tela real `:0` |
| Data | 2026-11-12 |

### Como rodar

```sh
# suíte completa (engine + UI); precisa de ffmpeg/ffprobe e de uma tela ($DISPLAY)
python3 -m unittest discover -s tests -v

# só o engine (não precisa de tela)
python3 -m unittest -v tests.test_engine_real

# só a UI integrada (tela real; em servidor sem tela: xvfb-run -a python3 -m unittest -v tests.test_ui_integration)
python3 -m unittest -v tests.test_ui_integration

# evidência ffprobe de uma fila real (imprime streams/durações e confere sha256 dos originais)
python3 tests/qa_evidence.py /tmp/qa-evidencia

# lançar o app
python3 main.py        # ou ./run.sh   (Windows: py main.py / run.bat)
```

Sem DISPLAY, `tests/test_ui_integration.py` é pulado (skip) com mensagem explícita; sem
ffmpeg, as duas suítes são puladas — a contagem de skips no resultado mostra isso.

### Cobertura

#### `tests/test_engine_real.py` — engine real (`extractor`)

| Área | O que é verificado |
|------|--------------------|
| Dependências | `check_dependencies()` ok com binários reais; ffmpeg ausente via kwarg, ffprobe ausente via env `VIDEO_EXTRACTOR_FFPROBE`, PATH vazio → `ok=False` com mensagem, nunca exceção; `BatchProcessor.start()` levanta `DependencyMissingError` e não cria saídas; hierarquia de exceções |
| `list_videos` | só extensões de vídeo (case-insensitive), ignora ocultos/`.part`/txt/png, ordem casefold, caminhos absolutos, não-recursivo por padrão, `recursive=True`, pasta inexistente / arquivo → `InvalidInputError`, pasta vazia |
| Extração | H.264+AAC (MP4, MKV), MPEG-4+MP3 (AVI), VP9+Opus (WebM → recodificado): MP3 com exatamente 1 stream `mp3`, sem vídeo; MP4 com 0 streams de áudio e 1 de vídeo (h264/mpeg4), container mp4; duração ≈ original (±0,3 s) em 2 s e 7 s; decodificação completa sem erros |
| Nomes | espaços, acentos, `ñ`, CJK e `#` no nome e na pasta temporária; `<stem>.mp3` / `<stem>.mp4` |
| Sem áudio | status `no_audio`, MP4 válido, nenhum MP3, aviso preenchido |
| Só áudio | status `partial`, MP3 válido, sem MP4, erro explicando |
| Opções | só MP3 / só MP4 (a outra pasta nem é criada); ambos `None` → `InvalidInputError` |
| Pastas | criação de pastas aninhadas inexistentes; saída que é arquivo / sem permissão de escrita → `InvalidInputError` |
| Inválidos | arquivo não-mídia → `failed`, sem nada nas pastas de saída, original intacto; arquivo truncado → sem `.part`, o que for publicado é mídia legível; inexistente; sem permissão de leitura → `failed` |
| Sem sobrescrita | arquivos pré-existentes `clip.mp3/.mp4` intactos (sha256+mtime), novas saídas `clip (1)`, `clip (2)`; saída = pasta de origem → original intacto e ainda com áudio, MP4 vira `clip (1).mp4`; mesmo stem com extensões diferentes na fila |
| Fila | fila mista (ok / inválido / mudo / vp9 / mov) → `[success, failed, no_audio, success, success]`, ordem preservada, 3 MP3 + 4 MP4, pasta de origem idêntica (snapshot sha256+mtime), eventos `file_started`×5 / `file_finished`×5 / `batch_finished` por último, `message` sempre preenchida, `percent` em 0–100; pasta → `list_videos` → `run_batch`; `BatchProcessor` em thread (eventos vêm da thread de trabalho); validações de `start()`; cancelamento no meio → `cancelled`, `batch_finished` emitido, sem `.part` |
| Isolamento | `import extractor` não carrega `tkinter` |

#### `tests/test_ui_integration.py` — UI Tkinter + engine real, na tela

Os seletores nativos (`filedialog.askdirectory/askopenfilenames`) e as caixas
(`messagebox.*`) são substituídos por funções que devolvem caminhos/respostas — o próprio
diálogo nativo não pode ser automatizado — mas **os botões reais da janela são acionados
com `.invoke()`** e a extração roda de verdade.

| Teste | Verifica |
|-------|----------|
| janela | constrói, fica visível (`winfo_viewable`) na tela, título, FFmpeg detectado |
| fluxo completo | “Carregar pasta de entrada…” (4 vídeos + txt ignorado, recarregar não duplica) → “Escolher pasta…” MP3 e MP4 → “▶ Iniciar fila” (botão trava durante execução) → status `[success, failed, no_audio, success]`, saídas validadas por ffprobe, originais intactos, progresso 100 %, resumo exibido, detalhe da falha na linha |
| arquivos individuais | “Adicionar vídeos…” com 2 arquivos; segunda execução não sobrescreve (sufixo `(1)`) |
| validações | sem pastas de saída → aviso; saída que é arquivo → erro, nada iniciado; pasta vazia → aviso |
| só MP4 | MP3 desmarcado: pasta MP3 não criada, MP4 sem áudio |
| responsividade + cancelar | durante recodificação VP9, pior latência do loop Tk < 0,5 s; “Cancelar” → `cancelled`, sem `.part` |
| subpastas / Delete | “Incluir subpastas” muda a fila; tecla Delete remove o selecionado |
| reexecução | “Iniciar fila” de novo só reprocessa itens não concluídos (sem duplicar `bom.mp3`) |
| FFmpeg ausente | banner vermelho com instrução, “Iniciar” recusa com erro e nada é gerado; após “instalar”, “Verificar novamente” limpa o banner e a fila roda |

#### Launcher

`timeout 6 ./run.sh` → processo vivo após 6 s (exit 124 do `timeout`), sem saída de erro,
janela aberta na tela `:0`. `python3 main.py` é o mesmo ponto de entrada.

### Resultados

#### Validação final (2026-11-12, estado integrado após correções do backend)

```
$ python3 -W always::ResourceWarning -m unittest discover -s tests -v
Ran 49 tests in 105.182s
OK
```

| Suíte | Testes | Passaram | Falhas | Skips |
|-------|-------:|---------:|-------:|------:|
| `tests/test_engine_real.py` | 37 | 37 | 0 | 0 |
| `tests/test_ui_integration.py` (tela real `:0`) | 12 | 12 | 0 | 0 |
| **Total** | **49** | **49** | **0** | **0** |

- 0 `ResourceWarning`; 0 processos `ffmpeg` remanescentes depois da suíte (`pgrep -c ffmpeg` → 0).
- Contagens anteriores de “45” eram da suíte antes de eu acrescentar 4 testes de UI
  (janela visível, subpastas/Delete, reexecução só pendentes, FFmpeg ausente).
- Cancelamento (BatchProcessor, VP9 640×480 30 s): `cancel()` → `wait()` em ~0,00 s
  nas etapas audio e video, status `cancelled`, sem `.part`.
- Launcher: `timeout 6 ./run.sh` e `timeout 6 python3 main.py` → ambos exit 124
  (janela aberta e viva após 6 s), sem saída de erro.

Evidência ffprobe (`python3 tests/qa_evidence.py <pasta>`, fila de 4 itens carregada por `list_videos`):

```
[success]  01 Férias ação.mp4   video_mode=copy
  MP3: 01 Férias ação.mp3  dur=2.064s  streams=[audio:mp3]
  MP4: 01 Férias ação.mp4  dur=2.000s  streams=[video:h264]
[failed]   02 corrompido.mp4    erro='Arquivo inválido ou corrompido: ... moov atom not found ...'
  MP3: (não gerado)   MP4: (não gerado)
[no_audio] 03 sem áudio.mp4     video_mode=copy
  MP3: (não gerado)
  MP4: 03 sem áudio.mp4    dur=2.000s  streams=[video:h264]
[success]  04 vp9 opus.webm     video_mode=reencode
  MP3: 04 vp9 opus.mp3     dur=2.040s  streams=[audio:mp3]
  MP4: 04 vp9 opus.mp4     dur=2.000s  streams=[video:h264]
originais intactos (sha256 antes == depois): True
```

README conferido contra o comportamento: comandos de lançamento (`python3 main.py`,
`./run.sh`), comando de testes, nomes de saída, colisão `(1)`, status, banner de FFmpeg
ausente e “Verificar novamente” — sem divergências.

**Veredito: v1 apta. Nenhum bug bloqueante aberto.**

#### Recomendações (não bloqueantes, próximas versões)

- Validar em Windows (`run.bat`, `CREATE_NO_WINDOW`, caminhos com `\`) e macOS.
- Instalar `xvfb` em CI para rodar a suíte de UI sem tela (`xvfb-run -a ...`).
- Testar arquivos longos/grandes (1 h, 4K) para tempo de recodificação e progresso.
- Considerar opção de qualidade/bitrate na UI e persistência da fila.

### Limitações da validação

- **Captura de tela**: a sessão é Wayland; `PIL.ImageGrab` via XWayland falha
  (`X get_image failed: error 8`) e não há `xwd`/`import`/`gnome-screenshot`. Não há
  screenshot anexado; a presença visual da janela foi verificada por `winfo_viewable()`,
  geometria e pelo launcher vivo na tela real.
- **Diálogos nativos** (GTK/Tk file chooser) não foram clicados por automação; seus
  retornos foram substituídos. O caminho de código depois deles (botões reais) foi exercitado.
- **Xvfb** não está instalado; não foi necessário porque havia tela real.
- **Windows/macOS** não foram testados (só Linux). `run.bat` não foi executado.
- Os testes usam vídeos curtos sintéticos (2–20 s, até 640×480); arquivos longos/4K não
  foram medidos.

### Achados

| # | Severidade | Dono | Descrição | Estado |
|---|-----------|------|-----------|--------|
| 1 | baixa | backend | `_run_ffmpeg` não fechava `proc.stdout/stderr` (ResourceWarning `unclosed file`, vazamento de 2 FDs por chamada até o GC) | corrigido pelo backend; revalidado (0 warnings) |
| 3 | baixa | backend/frontend | cancelamento levava ~5 s (SIGTERM fazia o libx264 fazer flush); achado pelo frontend | corrigido (kill imediato); revalidado ~0,00 s |
| 2 | — (teste) | QA | criar várias `tk.Tk()` no mesmo processo fazia o GC das `Variable` antigas rodar na thread do engine → `Tcl_AsyncDelete: wrong thread`. Artefato da suíte (app real tem uma única Tk); corrigido no `tearDown` (cancela `after`, `gc.collect()` na thread principal) | corrigido em tests/ |
