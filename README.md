# skills

Skills pessoais do Henrico Piubello Neves — [henricop](https://github.com/henricop).

Cada pasta é uma skill: `SKILL.md` (método) + scripts/modelos de apoio.

## Índice

| Skill | O que faz |
|---|---|
| [proto-demo](proto-demo/) | Protótipo de página scroll-story + vídeo demo gravado (MP4, pôster, contact sheet), com validação programática. |
| [transcricao-local](transcricao-local/) | Transcrição local de áudio e da fala de vídeos, com timestamps; resumos de mensagens, reuniões e aulas conforme o pedido. |

## Instalação

Copie (ou clone com sparse-checkout) a pasta da skill para `~/.claude/skills/` (Claude Code)
ou o equivalente do seu agente:

```bash
git clone https://github.com/henricop/skills.git
cp -r skills/proto-demo skills/transcricao-local ~/.claude/skills/
```

### proto-demo

Instale as dependências **dentro da pasta da skill**
(o `import('playwright')` dos scripts resolve a partir de onde eles estão):

```bash
cd ~/.claude/skills/proto-demo && npm i playwright && npx playwright install chromium
```

(ffmpeg e Node 18+ no PATH.)

### transcricao-local

```bash
brew install ffmpeg whisper-cpp
```

Requer Python 3.9+. Na primeira vez, baixe o modelo (cerca de 574 MB, uma vez só)
testando com o áudio sintético de exemplo:

```bash
cd ~/.claude/skills/transcricao-local
python3 scripts/transcrever.py --baixar-modelo "exemplo/WhatsApp Ptt 2026-10-02 at 09.12.44.ogg"
```

Mande o caminho de um áudio ou vídeo e indique a entrega:

- **“Transcreve”**: texto completo com timestamps e trechos incertos.
- **“O que diz esse áudio?”**: síntese dos pontos principais e pedidos explícitos.
- **“Resume a reunião”**: assuntos, decisões, tarefas e questões em aberto.
- **“Resume a aula”**: temas e explicações principais.

O reconhecimento roda na própria máquina com whisper.cpp; a mídia não é enviada a
uma API. O texto transcrito entra no contexto do assistente. O download inicial do
modelo usa a rede.

Veja o [exemplo de resumo](transcricao-local/exemplo/resumo.md). Os timestamps permitem
localizar o trecho original, e correções incertas ficam sinalizadas como hipóteses.
Use `--salvar` para guardar TXT e SRT ou `--saida PASTA` para escolher o destino.
