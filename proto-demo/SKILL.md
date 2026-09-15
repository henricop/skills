---
name: proto-demo
description: Constrói um protótipo de página web scroll-story (estilo página de produto) e entrega o vídeo demo gravado, com pôster e contact sheet. Use quando pedir "protótipo da home/página + vídeo", "grava a página rodando", "demo do site", "mostra o protótipo gravado", ou quando uma decisão de design precisar de evidência em vídeo antes de escrever o código de verdade. Inclui validação programática da página e do vídeo sem depender de visão.
---

# proto-demo — página scroll-story + vídeo demo

Pipeline completo, zero → evidência: um protótipo HTML navegável (história em capítulos ao rolar, objeto 3D que reage ao mouse, final que entra numa tela) e um MP4 gravado dele, com pôster e contact sheet. Serve para validar direção de design com stakeholders antes de construir o site real.

Arquivos desta skill (use-os como ponto de partida):
- `template.html` — esqueleto genérico da página (troque capítulos, objetos e manchete)
- `rec.mjs` — gravador Playwright com GPU (WebGL funciona) e DSL de ações
- `probe.mjs` — validação programática da página em posições de scroll

## Passo 0 — Requisitos

- Node 18+ e ffmpeg no PATH
- Playwright, instalado **na pasta da skill** (o `import('playwright')` resolve a partir do
  script, não do diretório atual): `npm i playwright && npx playwright install chromium`.
  Ou aponte `PLAYWRIGHT_IMPORT` para um `playwright/index.mjs` já instalado
- GPU: no macOS o gravador usa `--use-angle=metal`. Sem as flags de GPU o Chromium headless
  **não cria contexto WebGL** (páginas Three.js ficam em branco). O `rec.mjs` já leva as flags.

## Passo 1 — A gramática da página (regras de design)

Antes de escrever HTML, fixe as regras. Elas valem para qualquer página-story:

1. **Um argumento por rolagem.** Cada capítulo tem: número/ano gigante, etiqueta curta, uma frase.
   Se a frase explica duas coisas, são dois capítulos.
2. **Legível primeiro.** Corpo ≥ 18px, títulos grandes, zero jargão na tela.
3. **Zonas separadas.** Texto à esquerda, objeto à direita (sticky). Objeto no centro colide
   com o texto gigante — sempre verifique no probe (passo 3).
4. **Uma cor de destaque** sobre fundo liso. Tom claro/escuro automático
   (`prefers-color-scheme`), escuro como padrão de gravação.
5. **Animação útil.** Cada movimento revela algo, mostra progresso ou liga causa e efeito.
   Micro ≤ 600ms. Objeto entra girando, reage ao mouse, sai girando — não decoração paralela.
6. **Reconhecível em 3s.** Objetos icônicos com legenda, não abstrações.

## Passo 2 — A página

Comece de `template.html`. Arquitetura (mantida de projeto em projeto):

- `canvas` Three.js **fixo** ao fundo; seções DOM por cima: hero `100vh`, capítulos `220vh`,
  finale `260vh`
- Texto em `position: sticky` dentro da seção (fica na tela enquanto a seção rola)
- **Progresso por seção** (a fórmula que importa):
  `t = (scrollY - el.offsetTop) / (el.offsetHeight - innerHeight)`
  → `t=0` quando o topo da seção encosta no topo da viewport, `t=1` quando o fundo encosta
  no fundo. Janela errada = objeto já saiu quando o texto ainda está na tela (bug clássico).
- Objeto: janelas enter `t -0.3→0.2`, hold `0.2→0.8`, exit `0.8→1.3` (o overlap encadeia um
  capítulo no seguinte). Hold em `x ≈ 1.7` (direita), enter de `4.6`, exit para `-3.6`.
- Último objeto: **não sai**. O finale recentra ele (`x → 0`) e a câmera voa até a tela dele
  (`lerp` posição da câmera por `finT`). Quando chega, um overlay DOM aparece por cima —
  é o momento "entrou dentro".
- Texturas de tela desenhadas em canvas 2D (`CanvasTexture`) — zero assets externos.
- `renderer.toneMapping = ACESFilmicToneMapping` + exposição ~1.1, senão a luz estoura
  os materiais para branco puro.

## Passo 3 — Validação sem olhos (probe)

Mesmo quem enxerga deve validar programaticamente: é rápido e pega erro de layout que
screenshot único não mostra.

```bash
node probe.mjs file://$PWD/template.html '[["hero",0],["ch1",1280],["ch2",3040],["ch3",4800],["fin",7360]]'
```

Posições de hold: `el.offsetTop + 0.5 × (el.offsetHeight - innerHeight)`. O probe solta
`/tmp/probe-<tag>.png` + opacidade dos blocos por posição (o bloco certo deve dar 100).

Sobre os PNGs, estatística de pixels (PIL):

```python
from PIL import Image
im = Image.open('/tmp/probe-ch1.png').convert('RGB')
px = list(im.getdata()); n = len(px)
claro = sum(1 for r,g,b in px if 0.299*r+0.587*g+0.114*b > 140) / n      # texto gigante
bege  = sum(1 for r,g,b in px if r>175 and g>150 and b>95 and r>b+30) / n # cor do objeto
```

- Cor do objeto ≈ 0% → objeto sumiu (visibilidade, luz, ou colidiu com o texto)
- Mapa ASCII de densidade (grid 16×10 de claro/escuro) mostra **onde** cada coisa caiu —
  use para conferir separação texto|objeto e o recentralizar do finale
- Diff de frames antes/depois de uma ação (`ImageChops.difference` + `getbbox` + %
  de pixels mudados) prova que a ação funcionou (ex.: janela abriu = ~10% da tela mudou)

## Passo 4 — Gravação

```bash
node rec.mjs slug "file://$PWD/template.html" '<ações>'
```

DSL de ações (JSON): `["wait",ms]`, `["wheel",distPx,ms]`, `["click",x,y]`,
`["move",x,y]`, `["clickframe","url-do-frame","texto-do-link"]`, `["clicksel","sel"]`,
`["keys",["ArrowUp"],ms]`, `["type","txt"]`, `["press","Enter"]`, `["eval","js"]`,
`["shot","nome"]`, `["mark","nome"]`.

Como montar o script:

1. **Total de scroll** = `scrollHeight - innerHeight` (o probe imprime). Some os `wheel`
   até esse valor + ~5% de folga.
2. Espere o carregamento (CDN de Three.js: 3-5s) antes do primeiro movimento.
3. Uma rolagem por capítulo até a posição de hold, `wait` 1-1.5s para leitura.
4. Um `move` no meio mostra a reação ao mouse no vídeo.
5. Termine com a rolagem até o fundo + `wait` 3-4s (finale + overlay + stagger).

**O wheel real roda ~1,3-1,6× mais lento que o nominal** (passo de 50ms + overhead).
Um script de ~30s nominais vira ~40s de webm — normal, corte no passo 6.

Regras de interação que economizam regravação:

- **Coordenada fixa só em UI estável.** UI que sorteia posição/tamanho por sessão
  (ex.: janela de "SO" fake) precisa de `clickframe`/`clicksel` — locator no frame,
  com `hover` antes. Um clique por coordenada de uma sessão anterior erra na próxima.
- Página em iframe: `wheel`/`click` no documento principal não mexem no iframe. Ache o
  frame pelo trecho da URL e clique dentro dele.
- `colorScheme` do contexto: o gravador força **dark** (headless default é light — gravaria
  a versão clara sem avisar). `REC_LIGHT=1` inverte.

## Passo 5 — Validação do vídeo (scene scores)

Antes de cortar, confira o perfil de movimento do webm:

```bash
ffmpeg -y -v error -i vid/raw/slug.webm -vf "fps=2,select='gte(scene,0)',metadata=print:file=/tmp/sc.txt" -an -f null -
```

Parse `pts_time:` + `lavfi.scene_score` e olhe por janela (load / hold de cada capítulo /
transições): hold com média ~0 e nenhuma mudança = página morta naquele trecho; transição
com `scene ≥ 0.3` = o beat aconteceu. `scene=1.0` = corte de tela cheia (troca de estado).
Compare com o esperado pelo script de ações antes de aceitar o vídeo.

## Passo 6 — Corte e formatos

### Vídeo demo (MP4)

```bash
ffmpeg -nostdin -v error -y -ss INICIO -i vid/raw/slug.webm -t DURACAO \
  -vf "fps=30,scale=960:-2" -c:v libx264 -pix_fmt yuv420p -crf 26 \
  -movflags +faststart -an vid/slug.mp4
```

| Flag | Por quê |
|---|---|
| `-ss` antes de `-i` | seek rápido no container webm |
| `-t` | duração do corte, independente do resto do webm |
| `fps=30` | 30fps suaviza o scroll; 60 dobra o tamanho sem ganho visível |
| `scale=960:-2` | 960px é o padrão de painéis e docs; `-2` garante altura **par** (exigência do yuv420p) |
| `libx264` | player universal (QuickTime, Chrome, Preview) |
| `pix_fmt yuv420p` | compatibilidade máxima; sem isso alguns players mostram tela verde |
| `crf 26` | qualidade/tamanho equilibrado (~20-30 KB por segundo de página escura) |
| `-movflags +faststart` | moov atom no início: começa a tocar antes de baixar tudo (web/embed) |
| `-an` | demo mudo; garantir que não leva áudio de sistema |

- **Duração alvo**: 15-30s para clipe de referência; até ~40s para demo de home completa.
- **Margens**: comece ~1-2s depois do `ready_at` (deixe o primeiro beat assentar) e termine
  ~1s antes do fim do webm (o último meio segundo congela quando o navegador fecha).
- Webm de origem: Playwright grava VP8/VP9 1280×800 — **sempre arquive o raw** (recorte
  diferente sai de graça dele depois).

### Pôster (JPG) — para `poster=` do `<video>`

```bash
ffmpeg -nostdin -v error -y -ss TEMPO -i vid/slug.mp4 -frames:v 1 -q:v 3 vid/slug.jpg
```

Frame representativo (o beat mais identidade da página, ex.: o finale). `q:v 3` = JPG
alta qualidade, ~20-40KB, mesma largura 960 (altura par automática).

### Contact sheet (PNG) — arquivo/comparação

```bash
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 vid/slug.mp4)
ffmpeg -nostdin -v error -y -i vid/slug.mp4 -vf "fps=12/$DUR,scale=400:-2,tile=4x3" -frames:v 1 vid/slug-sheet.png
```

12 frames uniformes em grade 4×3: a página inteira num olhar, ideal para arquivar
variantes lado a lado (v1, v2, v3...) e para comparar antes/depois de um ajuste.

### Nomenclatura e layout de pastas

```
vid/
├── slug.mp4        demo final (o artefato que se mostra)
├── slug.jpg        pôster
├── slug-sheet.png  contact sheet
├── slug.log        log do gravador (ready_at, end_at, gl, cliques)
└── raw/slug.webm   gravação bruta (fonte para qualquer recorte futuro)
```

Um slug por variante (`home-v1`, `home-v2`): comparar é olhar os sheets lado a lado.

## Armadilhas conhecidas

- **WebGL em branco**: sem as flags de GPU o headless não cria contexto
  (`THREE.WebGLRenderer: Error creating WebGL context`). Navegador de QA sem GPU não
  serve para diagnosticar página WebGL — diagnostique dentro do gravador.
- **Headless grava claro**: `colorScheme` default é light. Force dark no contexto.
- **`readPixels` retorna zero** sem `preserveDrawingBuffer` — não é bug de render; valide
  por screenshot, não por readPixels.
- **`du` no APFS** pode reportar menos que a soma dos `ls` (blocos compartilhados) —
  confira existência e tamanho por `ls`, não por `du`, antes de declarar perda de arquivo.
- **`/tmp` some** (reboot / limpeza de 3 dias): copie mp4/jpg/sheet/log/raw para a pasta
  final do projeto no mesmo passo que produz.
- **Objeto some no capítulo**: quase sempre janela de progresso errada (passo 2) ou
  colisão de zonas texto/objeto (passo 3).
- **Clique não faz nada**: coordenada de sessão anterior em UI que sorteia posição; ou o
  alvo está num iframe; ou a UI exige hover antes do clique.

## Checklist de pronto

- [ ] Página: probe sem erros de console; bloco certo a 100 em cada hold; objeto presente
      pela cor no stats; zonas texto/objeto separadas no mapa ASCII
- [ ] Vídeo: scene score mostra movimento em todos os beats; sem trecho morto > 3s
- [ ] `vid/slug.mp4` (960, 30fps, h264, faststart) + `slug.jpg` + `slug-sheet.png` + log
- [ ] Raw webm arquivado fora de `/tmp`
- [ ] Gravação assistida ponta a ponta antes de mostrar a alguém
