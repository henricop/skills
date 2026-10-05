---
name: transcricao-local
description: Transcreve arquivos locais de áudio e a fala de vídeos com ffmpeg e whisper.cpp, sem enviar a mídia a uma API. Use para transcrever mensagens de voz, entender áudios do WhatsApp ou resumir gravações de reuniões e aulas com timestamps. Adapta a entrega ao pedido, preservando incertezas, decisões e tarefas quando houver. Não use para analisar imagens do vídeo ou apenas resumir texto já transcrito.
---

# Transcrição local

Transforme a fala de arquivos de áudio ou vídeo em texto consultável com timestamps.
A transcrição é a base; entregue um resumo ou uma análise quando isso atender ao pedido.
O reconhecimento roda localmente; o texto resultante entra no contexto do assistente.

## Escolha a entrega pelo pedido

| Pedido | Entrega |
|---|---|
| “Transcreve”, “transcrição” ou “só transcreve” | Transcrição com timestamps e indicação dos trechos incertos. |
| “O que diz esse áudio?” ou “resume” | Síntese breve, pontos principais com timestamps e pedidos explícitos, se houver. |
| Resumir reunião | Assuntos, decisões, tarefas com responsáveis e prazos informados, e questões em aberto. |
| Resumir aula | Temas e explicações principais com timestamps. Use decisões e tarefas apenas se existirem. |
| Áudio como insumo de outra tarefa | Extraia o conteúdo necessário e execute a tarefa pedida. |

Respeite o formato solicitado. Sem preferência explícita, use Markdown simples e omita
seções vazias. Não imponha quantidade de pontos, emojis ou tabelas a áudios curtos.
Uma resposta sugerida ao remetente só entra quando solicitada.

## Executar

Use [`scripts/transcrever.py`](scripts/transcrever.py) pelo caminho absoluto da skill,
sem depender do diretório atual. Ele recebe arquivos locais; uma URL precisa primeiro
ser obtida com uma ferramenta disponível e dentro do acesso autorizado pelo usuário.

Requisitos: Python 3.9+, `ffmpeg`, `ffprobe`, `whisper-cli` e um modelo Whisper GGML.
No macOS com Homebrew: `brew install ffmpeg whisper-cpp`. O script não instala pacotes.
Procura modelos em `~/.cache/whisper-models/`, `~/.cache/whisper-cpp/` e nos diretórios
`share/whisper-cpp` de `/opt/homebrew` e `/usr/local`. O padrão preferido é
`ggml-large-v3-turbo-q5_0.bin`; `--baixar-modelo` baixa cerca de 574 MB se faltar um modelo.
Esse download usa a rede; a mídia continua sendo processada localmente.

```bash
python3 /caminho/da/skill/scripts/transcrever.py "/caminho/áudio.ogg"
python3 /caminho/da/skill/scripts/transcrever.py "/caminho/reunião.mp4" --salvar
```

| Opção | Uso |
|---|---|
| Vários caminhos | Transcreve na ordem fornecida. Una o resumo apenas se forem parte da mesma conversa. |
| `--salvar` | Grava os arquivos de transcrição numa nova pasta ao lado da primeira mídia. |
| `--saida PASTA` | Escolhe a pasta e implica salvar; recusa sobrescrever transcrições existentes. |
| `--idioma en`, `es` ou `auto` | Padrão `pt`; escolha pelo contexto da gravação. |
| `--termos "nomes, siglas"` | Vocabulário conhecido e relevante à fala. É uma pista para o modelo, não evidência de que foi dito. |
| `--modelo CAMINHO` | Seleciona um modelo explicitamente. |
| `--baixar-modelo` | Baixa o modelo padrão se nenhum for encontrado. |
| `--sem-contexto` | Reduz repetição do reconhecimento; use se o resultado mostrar um laço. |

Ao salvar, o script gera `transcricao.txt`, `transcricao-blocos.txt` e `transcricao.srt`.
Com vários arquivos, as legendas são `transcricao-1.srt`, `transcricao-2.srt` etc.
Os timestamps são estimativas do modelo: os blocos indicam o início de cada segmento;
o SRT também inclui seu fim, em milissegundos.

Acima de 12 mil caracteres, o script salva automaticamente e mostra o caminho em vez
do texto completo. Use `--salvar` quando a transcrição completa precisar ser entregue
como arquivo. Para gravações demoradas, mantenha a execução em uma sessão que permita
acompanhar seu término; o tempo varia com hardware, modelo e duração.

## Interpretar com fidelidade

- **Incerteza:** não complete fala incompreensível. Preserve o trecho e sinalize a dúvida
  com seu timestamp. Uma grafia provável de nome, sigla ou produto deve aparecer como
  hipótese, salvo confirmação pelo usuário, contexto explícito ou escuta do trecho.
- **Texto espúrio:** frases como “Obrigado por assistir” podem ser fala real ou erro do
  reconhecimento. Não descarte só por constarem de uma lista. Se houver evidência de
  silêncio, ruído ou repetição espúria, explique a omissão na versão revisada. Preserve
  os arquivos brutos como saíram do script.
- **Números e prazos:** preserve valores, unidades, condições e negações. A transcrição
  automática não confirma o áudio; sinalize dúvidas relevantes sem inventar certeza.
- **Datas:** a data extraída do nome é uma pista de arquivo, não confirmação da gravação.
  Resolva “hoje”, “amanhã” ou “quinta” apenas quando a data da fala e a referência forem
  conhecidas. Se faltarem, mantenha a expressão original. Não use a data atual como base.
- **Falantes:** este script não identifica pessoas nem separa falantes. Nome do remetente
  e identidade de quem fala são informações diferentes. Atribua falas, tarefas e “você”
  ao usuário apenas com apoio no áudio ou no contexto fornecido.
- **Decisões:** distinga proposta, decisão e condição. Uma fala posterior só substitui
  um acordo anterior quando a conversa indica essa revisão. Sem responsável ou prazo
  declarado, escreva “não informado” quando o campo for relevante.
- **Vídeo:** o script extrai apenas a fala. Slides, gestos e conteúdo visual exigem
  análise separada quando solicitados.

Se houver erro relevante ou repetição, faça uma nova tentativa com a causa corrigida
(`--idioma`, vocabulário fundamentado ou `--sem-contexto`). Se persistir, entregue o que
foi recuperado e indique a limitação; não repita indefinidamente.

## Entregar

Para uma transcrição curta, apresente o texto completo com `[m:ss]`. Para uma longa,
entregue o arquivo completo e a localização dos trechos incertos. Não substitua uma
transcrição pedida por um resumo. Indique se o texto apresentado foi revisado.

Para um resumo, comece pela ideia principal e inclua timestamps nos pontos que o
sustentam. Extraia pedidos e compromissos explícitos, preservando responsáveis, prazos
e condições. Em vários arquivos, use referências como `[2 · 0:14]` e identifique qual
arquivo é o número 2. Acima de uma hora, use `[h:mm:ss]`.

Em gravações longas, salve a transcrição e leia todo o conteúdo em partes antes de
fazer um resumo completo. Organize por tema e confira decisões, tarefas e assuntos em
aberto antes de entregar. Para um pedido limitado a um trecho, analise esse trecho e
deixe o recorte explícito. Salve `resumo.md` junto da transcrição quando gerar um resumo
de gravação longa ou quando o usuário pedir um arquivo.

O [exemplo de resumo](exemplo/resumo.md) usa uma mensagem sintética de 40 segundos para
ilustrar a entrega. Não é um formato obrigatório nem um gabarito literal do modelo:
a grafia e a segmentação podem variar.

Antes de entregar, confira que os arquivos citados existem, os timestamps remetem à
mídia certa e que hipóteses não foram apresentadas como fatos. Se nenhuma fala for
reconhecida, informe isso e não produza um resumo inventado.
