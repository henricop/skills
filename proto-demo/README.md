# proto-demo

Constrói um protótipo de página web scroll-story (história em capítulos ao rolar, objeto
3D que reage ao mouse, final que "entra" numa tela) e entrega o vídeo demo gravado dele,
com pôster e contact sheet. Serve para validar uma direção de design com stakeholders
antes de escrever o site de verdade.

## Escopo

**Faz**

- Página HTML navegável a partir de `template.html`, seguindo uma gramática fixa: um
  argumento por rolagem, texto à esquerda e objeto à direita, uma cor de destaque,
  animação só quando revela algo.
- Validação programática da página em posições de scroll (`probe.mjs`): opacidade dos
  blocos, presença do objeto pela cor, mapa de densidade para conferir colisão
  texto/objeto. Funciona sem olhar a tela.
- Gravação com Playwright e GPU (`rec.mjs`), DSL de ações (scroll, clique, digitação,
  marcas), validação do vídeo por scene score, corte em MP4 960px/30fps, pôster JPG e
  contact sheet PNG.

**Não faz**

- O site final: é protótipo para decidir, não código de produção.
- QA de um site existente ou testes funcionais.
- Edição de vídeo além do corte e dos formatos descritos.

## Requisitos

Node 18+ e ffmpeg no PATH. Playwright instalado **dentro da pasta da skill**, porque o
`import('playwright')` dos scripts resolve a partir de onde eles estão:

```bash
cd ~/.claude/skills/proto-demo && npm i playwright && npx playwright install chromium
```

Ou aponte `PLAYWRIGHT_IMPORT` para um `playwright/index.mjs` já instalado. No macOS o
gravador usa `--use-angle=metal`; sem as flags de GPU o Chromium headless não cria
contexto WebGL e páginas Three.js ficam em branco.

## Instalação

```bash
cp -r proto-demo ~/.claude/skills/      # ou: ln -s "$PWD/proto-demo" ~/.claude/skills/proto-demo
```

## Uso

Peça "protótipo da home + vídeo", "grava a página rodando" ou "demo do site". O agente
monta a página a partir do template, valida com o probe, grava, confere o vídeo e corta:

```
vid/
├── slug.mp4        demo final
├── slug.jpg        pôster para o <video poster>
├── slug-sheet.png  contact sheet 4×3
├── slug.log        log do gravador
└── raw/slug.webm   gravação bruta (fonte de qualquer recorte futuro)
```

Um slug por variante (`home-v1`, `home-v2`) para comparar sheets lado a lado.
A pasta `vid/` está no `.gitignore` do repositório.

## Arquivos

| Arquivo | Para quê |
|---|---|
| `SKILL.md` | O método: regras de design, arquitetura da página, probe, gravação, validação do vídeo, corte e formatos, armadilhas. |
| `template.html` | Esqueleto genérico da página (troque capítulos, objetos e manchete). |
| `probe.mjs` | Validação programática da página em posições de scroll. |
| `rec.mjs` | Gravador Playwright com GPU e DSL de ações. |
