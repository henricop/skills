# skills

Skills pessoais do Henrico Piubello Neves — [henricop](https://github.com/henricop).

Cada skill é uma pasta com:

- `SKILL.md`: o método que o agente segue (é o arquivo que o agente carrega);
- `README.md`: escopo, requisitos, instalação e uso, para quem está lendo este repositório;
- scripts, modelos e referências de apoio.

## Índice

| Skill | O que faz | Use quando | Fora do escopo |
|---|---|---|---|
| [mergedev](mergedev/) | Integra as PRs abertas do GitHub na branch atual, uma por vez e na ordem certa (PR empilhada depois da mãe), resolvendo conflitos sem perder alteração de nenhum lado e documentando cada decisão no commit. | "mergeia as PRs do time na dev", "fecha o lote", várias PRs abertas para integrar antes de testar ou publicar. | Push, fechar PR, apagar branch (ficam com você); revisão de código; rebase interativo. |
| [proto-demo](proto-demo/) | Protótipo de página scroll-story (capítulos ao rolar, objeto 3D, final que entra numa tela) e o vídeo demo gravado dele, com pôster e contact sheet, validados programaticamente. | "protótipo da home + vídeo", "grava a página rodando", decisão de design que precisa de evidência em vídeo antes do código real. | O site de produção; QA de site existente; edição de vídeo além do corte. |
| [transcricao-local](transcricao-local/) | Transcreve áudios e a fala de vídeos na própria máquina (ffmpeg + whisper.cpp), com timestamps, e entrega transcrição, síntese ou resumo de reunião/aula conforme o pedido. | "transcreve", "o que diz esse áudio?", "resume a reunião/aula", mensagens de voz do WhatsApp. | Imagens e slides do vídeo; identificar quem fala; resumir texto já transcrito. |

Os requisitos de cada uma (gh, Playwright, whisper.cpp...) estão no README da pasta.

## Instalação

Copie a pasta da skill para `~/.claude/skills/` (Claude Code) ou o equivalente do seu
agente. Um symlink mantém a cópia atualizada com o clone:

```bash
git clone https://github.com/henricop/skills.git
cd skills
for s in mergedev proto-demo transcricao-local; do ln -s "$PWD/$s" ~/.claude/skills/$s; done
```

Depois siga o "Requisitos" do README de cada skill:
[mergedev](mergedev/README.md) · [proto-demo](proto-demo/README.md) ·
[transcricao-local](transcricao-local/README.md).
