# Extrator de Vídeos

Aplicativo de desktop simples (Python + Tkinter + FFmpeg). Você escolhe **uma pasta de destino**
e, para cada vídeo da fila, o programa cria nela uma pasta numerada com:

```
<destino>/
├── 001/
│   ├── audio.mp3          áudio do vídeo
│   ├── video.mp4          o vídeo sem áudio
│   └── frames/
│       ├── frame_01.jpg   4 imagens de momentos aleatórios do vídeo
│       ├── frame_02.jpg
│       ├── frame_03.jpg
│       └── frame_04.jpg
├── 002/
│   └── …
```

Os vídeos podem vir do computador (arquivos ou uma pasta inteira) ou de um **link público do
Instagram** (post ou reel): o vídeo é baixado e extraído automaticamente.

Os vídeos originais **nunca são alterados** e nada existente é sobrescrito: a numeração continua
a partir da maior pasta numerada que já estiver no destino (se já houver `001` a `005`, o próximo
vídeo vai para `006`; números pulados não são reaproveitados).

> Versão 3 (destino único com pastas numeradas e frames). Não há instalador nem executável empacotado: o programa
> roda a partir do código-fonte com o Python instalado no computador.

## Requisitos

| Item | Versão | Observação |
|------|--------|------------|
| Python | 3.8+ para arquivos locais; **3.11+** para links do Instagram | O uso local só precisa da biblioteca padrão (nenhum `pip install`). |
| Tkinter | incluso no Python | Em algumas distribuições Linux vem em pacote separado. |
| FFmpeg e FFprobe | qualquer versão recente | Precisam estar no `PATH`. |
| yt-dlp | ≥ 2026.10.26 (opcional) | **Só para links do Instagram.** Arquivos locais funcionam sem ele. A versão atual do yt-dlp exige Python 3.11+. |

### Linux

```sh
# Debian / Ubuntu / Mint
sudo apt install python3 python3-tk ffmpeg
# Fedora (ffmpeg completo vem do RPM Fusion; ffmpeg-free também funciona)
sudo dnf install python3 python3-tkinter ffmpeg
# Arch / Manjaro
sudo pacman -S python tk ffmpeg
```

### Windows

1. Instale o Python em <https://www.python.org/downloads/> marcando **“Add python.exe to PATH”**
   e mantendo marcada a opção **“tcl/tk and IDLE”**.
2. Instale o FFmpeg (qualquer uma das opções), depois **feche e reabra** o terminal:
   ```bat
   winget install Gyan.FFmpeg
   :: ou
   choco install ffmpeg
   ```
   Alternativa manual: baixe um build em <https://www.gyan.dev/ffmpeg/builds/>, extraia e
   adicione a pasta `bin` ao `PATH` do sistema.

### macOS

```sh
brew install python python-tk ffmpeg
```

### yt-dlp (opcional, só para links do Instagram)

Não é preciso instalar nada disso para usar arquivos do computador. Para os links, o caminho
reproduzível é um ambiente virtual (venv) com o arquivo `requirements-instagram.txt`. Ele funciona
também nas distribuições Linux que bloqueiam `pip install` no Python do sistema (PEP 668,
erro *externally-managed-environment*). O venv usa o Tkinter do Python do sistema, então os
pacotes `python3-tk`/`tk` continuam necessários.

Linux / macOS (precisa de Python 3.11+; no Debian/Ubuntu instale também `python3-venv`):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-instagram.txt
.venv/bin/python main.py          # use sempre este comando para ter os links disponíveis
```

Windows:

```bat
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements-instagram.txt
.venv\Scripts\python main.py
```

Alternativas sem venv: `pipx install yt-dlp` (Linux/macOS), `brew install yt-dlp` (macOS) ou
`winget install yt-dlp.yt-dlp` (Windows) — o programa usa o `yt-dlp` encontrado no `PATH`.
Também é possível apontar um executável específico com a variável `VIDEO_EXTRACTOR_YTDLP`.

O Instagram muda com frequência e versões antigas do yt-dlp param de funcionar; atualize com
`.venv/bin/python -m pip install -U -r requirements-instagram.txt`. Se o yt-dlp for instalado com
o programa aberto, basta tentar o link de novo (ele verifica outra vez).

Confira se o FFmpeg está acessível:

```sh
ffmpeg -version
ffprobe -version
```

## Como executar

Na pasta do projeto:

```sh
python3 main.py        # Linux / macOS
./run.sh               # Linux / macOS (atalho equivalente)
```

```bat
py main.py             :: Windows
run.bat                :: Windows (duplo clique também funciona)
```

Se você instalou o yt-dlp num venv (veja acima), rode com o Python do venv:
`.venv/bin/python main.py` (Windows: `.venv\Scripts\python main.py`). Os atalhos `run.sh` e
`run.bat` usam automaticamente o `.venv` se ele existir na pasta do projeto.

## Como usar

A janela tem três passos, de cima para baixo:

1. **Adicionar vídeos**
   - **“Adicionar arquivos…”** escolhe um ou vários vídeos (seletor nativo do sistema).
   - **“Adicionar pasta…”** coloca na fila todos os vídeos de uma pasta (marque **“Incluir
     subpastas”** para buscar também nas subpastas). Vídeos repetidos são ignorados.
   - **Link do Instagram**: cole o endereço de um post ou reel público
     (ex.: `https://www.instagram.com/reel/XXXXXXXXX/`) e clique em **“Baixar e extrair”**
     (ou tecle *Enter*). Antes de baixar, o programa confere o link e a pasta de destino do
     passo 2. O link entra na fila e **começa sozinho**: baixa e gera as pastas numeradas — não
     é preciso clicar em “Iniciar fila”. Se outra coisa estiver rodando, o link espera a vez.
     Num carrossel, **cada vídeo ganha a sua própria pasta** (ex.: `007` e `008`).
2. **Pasta de destino** – clique em **“Escolher pasta…”** (seletor nativo). Se ela não existir,
   é criada. **“Abrir”** mostra a pasta no gerenciador de arquivos. Os três itens (áudio, vídeo
   sem áudio e frames) são sempre gerados. A pasta fica travada enquanto a fila roda.
3. **Fila e andamento** – clique em **“▶ Iniciar fila”** para processar os arquivos locais.
   Tudo é feito um item por vez; cada linha mostra a **pasta numerada** do vídeo (coluna
   PASTA), a etapa (Baixando / Analisando / Extraindo áudio / Gerando vídeo / Extraindo frames),
   o percentual e o resultado; a barra mostra o andamento. Selecione uma linha e clique em
   **“Abrir pasta do item”** para ver os arquivos dela (para um carrossel, abre o destino).
   Um link aparece como uma linha 🔗 com os vídeos baixados logo abaixo dela. A janela continua
   respondendo; dá para adicionar mais arquivos ou links enquanto a fila roda (clique em
   “Iniciar fila” de novo para incluir arquivos novos).
   - **Cancelar** interrompe o item atual (download ou extração) e desmarca o que estava
     esperando. A pasta numerada do vídeo interrompido é apagada inteira (estava incompleta);
     as pastas dos vídeos que já tinham terminado ficam intactas.
   - **Remover selecionados** (ou *Delete*) e **Limpar fila** ficam disponíveis quando nada
     está rodando.

Resultados possíveis por arquivo:

| Status | Significado |
|--------|-------------|
| Concluído | `audio.mp3`, `video.mp4` e os 4 frames foram gerados. |
| Concluído (sem áudio) | O vídeo não tem trilha de áudio: a pasta tem `video.mp4` e os frames, **sem** `audio.mp3`. |
| Parcial | Parte dos itens foi gerada; a pasta fica com o que deu certo e *Detalhes* diz o que falhou. |
| Falhou | Nada foi gerado (arquivo corrompido, não é vídeo, link privado, sem internet…); nenhuma pasta é criada nem numeração consumida. A fila continua. |
| Cancelado | Interrompido pelo usuário; a pasta incompleta é removida. |

Dê **dois cliques** em uma linha para ver os detalhes completos. Clicar de novo em
**“Iniciar fila”** reprocessa apenas os itens que não foram concluídos.

### Saídas

- `audio.mp3`: LAME VBR (~190 kbps), primeira trilha de áudio do vídeo.
- `video.mp4`: o vídeo sem áudio. Se já for H.264 a imagem é copiada sem perda (rápido); caso
  contrário é recodificada em H.264 (CRF 23), o que é mais lento.
- `frames/frame_01.jpg` … `frame_04.jpg`: JPG na resolução original, em ordem de tempo. O vídeo é
  dividido em 4 partes iguais e um instante aleatório é sorteado em cada parte (por isso cada
  execução gera imagens diferentes). Em vídeos muito curtos as imagens podem sair iguais.
- Vídeos do Instagram são baixados numa pasta temporária, apagada ao final (inclusive em falha
  ou cancelamento); o vídeo original baixado **não é guardado**, só a pasta numerada.

## FFmpeg não encontrado

Se o FFmpeg/FFprobe não estiver instalado (ou não estiver no `PATH`), a janela abre mesmo
assim, mostra um aviso em vermelho com o comando de instalação para o seu sistema e o botão
**“Iniciar fila”** recusa iniciar. Depois de instalar, clique em **“Verificar novamente”**
(no Windows pode ser preciso fechar e reabrir o programa para o novo `PATH` valer).

Para usar binários fora do `PATH`, defina as variáveis de ambiente
`VIDEO_EXTRACTOR_FFMPEG` e `VIDEO_EXTRACTOR_FFPROBE` com o caminho completo de cada um.

## Links do Instagram: o que funciona e o que não funciona

- Funciona com **posts e reels públicos** (`/p/…`, `/reel/…`, `/reels/…`, `/tv/…`), sem login.
  Em carrosséis, todos os vídeos (até 20) são processados e as imagens são ignoradas.
- **Não** funciona com perfis privados, stories, destaques, perfis inteiros, lives ou qualquer
  conteúdo que exija estar logado — o programa não pede nem usa senha/cookies.
- **Muitos vídeos chegam sem áudio**: sem login, o Instagram frequentemente oferece só a faixa de
  vídeo. Nesse caso o item fica como *Concluído (sem áudio)*: a pasta tem `video.mp4` e os
  frames, mas não `audio.mp3`.
  Isso é uma limitação do Instagram, não do programa.
- O Instagram limita acessos anônimos: às vezes ele pede login até para posts públicos ou
  bloqueia temporariamente após muitos downloads. Nesses casos a linha mostra o motivo; tente
  mais tarde ou atualize o yt-dlp.
- O download depende do yt-dlp e das mudanças do próprio Instagram; não há garantia de que um
  link específico funcione.
- Baixe apenas conteúdo que você tem direito de usar.
- Testado contra o Instagram real (yt-dlp 2026.10.26, sem login): um post público e um carrossel
  público foram baixados e extraídos (ambos chegaram sem áudio); um reel retornou "não encontrado".
  Não foram testados com o Instagram real: um vídeo com áudio, um post privado, o limite de
  requisições e a queda de rede (esses casos foram simulados nos testes automatizados).

## Estrutura

```
main.py              ponto de entrada (verifica Python/Tkinter e abre a janela)
run.sh / run.bat     atalhos de inicialização (usam .venv se existir)
requirements-instagram.txt  yt-dlp (opcional, só para links)
extractor/engine.py  motor: ffprobe/ffmpeg, fila, pastas numeradas, frames (sem Tkinter)
extractor/ui.py      interface Tkinter
tests/               testes automatizados (unittest)
```

Testes: `python3 -m unittest discover -s tests -v` (precisam do FFmpeg instalado).

## Limitações conhecidas

- Não há executável/instalador; é preciso ter Python e FFmpeg instalados (e yt-dlp para links).
- Processa um vídeo por vez (sem paralelismo).
- Só a primeira trilha de áudio vira `audio.mp3`; legendas e outras trilhas são descartadas.
- Sempre são gerados os três itens; não dá para escolher só um deles, nem a quantidade de
  frames, a qualidade ou o nome das pastas.
- A fila não é salva: fechar o programa limpa a lista.
- Só links do Instagram (outros sites não são aceitos) e só um link por vez no campo.
- O vídeo original baixado do Instagram não é guardado.
- Não há arrastar-e-soltar de arquivos (Tkinter puro não oferece isso de forma portátil).
- A interface só foi testada no Linux; Windows e macOS seguem as mesmas APIs padrão, mas não
  foram validados nesta versão.
