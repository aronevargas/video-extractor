# Visual da interface (v4) — referência e decisões

Refatoração **apenas visual** de `extractor/ui.py`, baseada no site <https://sharkbot.com.br>,
inspecionado em 2026-11-13. Nenhuma função mudou: o destino é único, cada vídeo continua indo
para uma pasta numerada (`NNN/audio.mp3`, `video.mp4` e 4 frames), e a fila local e do
Instagram, o cancelamento, o progresso, os erros e o "Abrir pasta do item" seguem iguais.

## Como a referência foi inspecionada

- **HTML e CSS reais:** baixados com `curl`. As variáveis de `:root` vêm do arquivo
  `/_next/static/chunks/258m6x_9gqp-m.css` e as classes dos botões e títulos, do HTML da página
  inicial.
- **Screenshot:** tirado com o Firefox headless em 1366×900 (o topo da página) e em 1366×4200
  (a página longa).

## O que a referência usa

| Elemento | Valor no site |
|---|---|
| Fundo | `--surface-base #050505` (corpo `bg-[#050505]`) |
| Superfícies | `--surface-100 #0a0a0a`, `--surface-200 #111`, `--surface-300 #1a1a1a` |
| Bordas | `--border #ffffff14` (branco 8%), `--border-hover #ffffff26` (15%) |
| Texto | `--text #fff`, `--text-secondary #e5e5e5`, `--text-muted #a1a1aa`, `--text-disabled #71717a` |
| Azul da marca | `--brand-400 #60a5fa`, `--brand-500 #3b82f6`, `--brand-600 #2563eb`, `--brand-700 #1d4ed8`, `--brand-900 #1e3a5f` |
| Estados | `--success-500 #10b981`, `--warning-500 #f59e0b`, `--danger-500 #ef4444` |
| Botão principal | `bg brand-500`, texto branco seminegrito 13–15px, `h-9`/`h-12`, `px-5`/`px-7`, raio 8–12px, brilho azul |
| Botão secundário | fundo transparente, `border-white/10`, texto branco; no hover, `bg-white/[0.04]` e `border-white/20` |
| Links do menu | texto `white/50` que fica branco no hover, sem borda |
| Rótulos de seção | pílula em maiúsculas, texto azul, fundo azul a 10% e borda azul a 20% (ex.: "RECURSOS", "COMO FUNCIONA") |
| Títulos | Space Grotesk/Inter em negrito, branco, com uma palavra destacada em azul |
| Ritmo | muito espaço em branco; seções separadas por uma linha `white/5`; cartões discretos (`border-white/8`) |

## Como foi adaptado ao Tkinter

| Site | App |
|---|---|
| Fundo `#050505` | `COLORS["bg"] = #050505` |
| Painéis `#0a0a0a` com borda de 8% | Só a lista da fila tem painel (`surface #0b0b0c`, borda `#27272a`). As seções **não** são cartões: são separadas por uma linha de 1px (`divider #161618`), como no site, o que tira as bordas extras da v3 |
| Botão principal azul | `Accent.TButton` em "Baixar e extrair" e "▶ Iniciar fila" |
| Botão secundário com contorno | `TButton` com fundo transparente e borda fina, que fica mais clara no hover, e borda azul no foco |
| Links do menu | `Ghost.TButton` (texto cinza que fica branco no hover) para ações de apoio: "Abrir", "Remover selecionados", "Limpar fila" |
| Pílulas de seção | `Step.TLabel`: "PASSO 1/2/3" em azul claro, com fundo e borda azuis |
| Título com destaque | "Extrator de **Vídeos**", com "Vídeos" em `brand_text #60a5fa` |
| Fontes | Inter e Space Grotesk quando instaladas; senão, as fontes do sistema (Segoe UI, SF, Noto Sans, Ubuntu…). Nada é baixado |
| Progresso | barra `brand #3b82f6` de 6px sobre `#1a1a1d` |
| Linha selecionada | `select #152a4a` (`brand-900` escurecido) |

### Onde o app não segue a referência (de propósito)

- **Contraste do botão principal:** branco sobre `#3b82f6` dá só 3,68:1. Por isso o fundo do
  botão usa `brand-600 #2563eb` (5,17:1); o hover e o clique escurecem para `#1d4ed8` (6,7:1) e
  `#1e40af` (8,7:1). O `#3b82f6` fica só na barra de progresso.
- **Cores dos status:** o texto usa os tons 400 (`#34d399`, `#fbbf24`, `#f87171`) em vez dos 500,
  para ter pelo menos 4,5:1 também sobre a linha selecionada. O menor contraste de texto do
  tema é 5,19:1.
- **Limitações do Tkinter:** não há cantos arredondados, sombras, brilho, gradientes nem
  espaçamento entre letras. Os cantos ficam retos e as pílulas são retangulares.
- **O que não foi copiado:** marca, logotipo e textos do site. Também não há menu nem seções de
  marketing: o app continua sendo uma janela de trabalho.

## Tamanho da janela e textos

- **Tamanho mínimo: 820×680.** Isso cabe na área útil de uma tela 1366×768, mesmo descontando a
  barra de título e o painel do sistema (o limite é de cerca de 689 px). Nesse tamanho a fila
  mostra 4 linhas, e o status, "Cancelar" e "Iniciar fila" ficam visíveis. Na v3 o mínimo era
  820×640 e cortava a fila e os botões; uma tentativa intermediária de 820×720 não cabia em
  1366×768.
- **Tamanho inicial dinâmico:** a largura é `min(1040, largura da tela − 80)` e a altura é
  `min(820, altura da tela − 100)`, nunca abaixo do mínimo. Numa tela 1920×1080 a janela abre
  em 1040×820; numa 1366×768, em 1040×680.
- As linhas da fila têm 26 px de altura. Os textos de apoio são curtos (uma linha a partir de
  820 px) e mesmo assim quebram conforme a largura da janela. A dica do campo de link aparece
  dentro do campo (é um rótulo sobreposto, então `url_var` continua vazio).
- Para saber se o campo de link está focado, a interface consulta o foco direto no Tcl
  (`tk.call("focus")`), e não via `focus_get()`, que levanta `KeyError` quando um diálogo nativo
  do Tk (por exemplo, o de escolher pasta) está com o foco.
- Caminhos longos no campo de destino mostram sempre o final, inclusive depois de redimensionar
  a janela.
- Textos sobre o conteúdo gerado: o MP3 só é prometido "se tiver som", e a dica do yt-dlp diz
  "ausente ou com erro", porque o yt-dlp pode existir e mesmo assim falhar.

## Evidências

- Screenshots, antes (v3) e depois (v4), no tamanho padrão e no mínimo: anexados ao relatório
  do frontend.
- `tests/test_ui_v4_visual.py` (do QA): contraste, foco, estados dos botões, nada cortado no
  tamanho padrão nem no mínimo, e linhas visíveis na fila.
