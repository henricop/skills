# skills

Skills pessoais do Henrico Piubello Neves — [henricop](https://github.com/henricop).

Cada pasta é uma skill: `SKILL.md` (método) + scripts/modelos de apoio.

## Índice

| Skill | O que faz |
|---|---|
| [proto-demo](proto-demo/) | Protótipo de página scroll-story + vídeo demo gravado (MP4, pôster, contact sheet), com validação programática. |

## Instalação

Copie (ou clone com sparse-checkout) a pasta da skill para `~/.claude/skills/` (Claude Code)
ou o equivalente do seu agente:

```bash
git clone https://github.com/henricop/skills.git
cp -r skills/proto-demo ~/.claude/skills/
```

Depois de instalar `proto-demo`, instale as dependências **dentro da pasta da skill**
(o `import('playwright')` dos scripts resolve a partir de onde eles estão):

```bash
cd ~/.claude/skills/proto-demo && npm i playwright && npx playwright install chromium
```

(ffmpeg e Node 18+ no PATH.)
