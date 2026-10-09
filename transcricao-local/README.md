# transcricao-local

Transcreve arquivos de áudio e a fala de vídeos na própria máquina (ffmpeg + whisper.cpp),
com timestamps, e entrega transcrição, síntese ou resumo de reunião/aula conforme o pedido.
A mídia não é enviada a nenhuma API.

## Escopo

**Faz**

- Transcrição com timestamps de mensagens de voz, áudios do WhatsApp, gravações de
  reuniões e aulas, em um ou vários arquivos.
- Entrega adaptada ao pedido: texto completo, síntese dos pontos principais, resumo de
  reunião (assuntos, decisões, tarefas, questões em aberto) ou de aula (temas e
  explicações).
- Preserva incertezas: trechos incompreensíveis ficam marcados, grafias prováveis de nomes
  aparecem como hipótese, números e prazos não são "corrigidos".
- Salva TXT, blocos e SRT quando pedido ou quando o texto é longo demais para o terminal.

**Não faz**

- Analisar imagens, slides ou gestos do vídeo: só a fala.
- Identificar quem fala: nome do remetente e identidade de quem fala são coisas diferentes.
- Resumir texto que já está transcrito (isso dispensa a skill).

## Requisitos

Python 3.9+, `ffmpeg`, `ffprobe`, `whisper-cli` e um modelo Whisper GGML.

```bash
brew install ffmpeg whisper-cpp
```

O script procura modelos em `~/.cache/whisper-models/`, `~/.cache/whisper-cpp/` e em
`share/whisper-cpp` do Homebrew. Na primeira vez, baixe o modelo padrão
(`ggml-large-v3-turbo-q5_0.bin`, cerca de 574 MB, uma vez só) testando com o áudio
sintético de exemplo:

```bash
cd ~/.claude/skills/transcricao-local
python3 scripts/transcrever.py --baixar-modelo "exemplo/WhatsApp Ptt 2026-10-02 at 09.12.44.ogg"
```

Esse download usa a rede; o reconhecimento em si é local. O texto transcrito entra no
contexto do assistente.

## Instalação

```bash
cp -r transcricao-local ~/.claude/skills/   # ou: ln -s "$PWD/transcricao-local" ~/.claude/skills/transcricao-local
```

## Uso

Mande o caminho de um áudio ou vídeo e diga a entrega:

- **"Transcreve"**: texto completo com timestamps e trechos incertos.
- **"O que diz esse áudio?"**: síntese dos pontos principais e pedidos explícitos.
- **"Resume a reunião"**: assuntos, decisões, tarefas e questões em aberto.
- **"Resume a aula"**: temas e explicações principais.

Opções úteis do script: `--salvar` guarda TXT e SRT ao lado da mídia, `--saida PASTA`
escolhe o destino, `--idioma en|es|auto` (padrão `pt`), `--termos "nomes, siglas"` dá
vocabulário ao modelo, `--sem-contexto` corta repetições em laço.

Veja o [exemplo de resumo](exemplo/resumo.md): os timestamps localizam o trecho original
e as correções incertas ficam sinalizadas como hipóteses.

## Arquivos

| Arquivo | Para quê |
|---|---|
| `SKILL.md` | O método: escolha da entrega pelo pedido, execução, fidelidade na interpretação, formato de entrega. |
| `scripts/transcrever.py` | Extrai o áudio com ffmpeg, roda o whisper.cpp e formata a saída (texto, blocos, SRT). |
| `exemplo/` | Áudio sintético de 40 s e o resumo correspondente, para testar a instalação e ver o formato. |
| `agents/openai.yaml` | Metadados de exibição para agentes que leem esse formato. |
