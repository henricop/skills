---
name: mergedev
description: Integra as pull requests abertas do repositório GitHub do projeto atual na branch em que o usuário está (normalmente a dev), uma PR por vez e na ordem certa (PR empilhada só depois da PR-mãe), resolvendo os conflitos de cada merge sem perder alteração de nenhum lado e registrando cada decisão na mensagem do commit. Use sempre que pedirem para "mergear as PRs do time", "puxar/integrar as PRs na dev", "fechar o lote", "juntar o trabalho do pessoal", "resolver os conflitos das PRs" ou quando houver várias PRs abertas para integrar antes de testar ou publicar, mesmo sem a palavra "merge". Não serve para revisar o código de uma PR nem para rebase interativo.
---

# mergedev — integrar as PRs do time na branch atual

Você está juntando o trabalho de várias pessoas de uma vez. Cada merge é um ponto em que
uma alteração pode sumir sem ninguém notar: um trecho descartado "porque parecia igual", um
lockfile em que se escolheu um lado, um arquivo apagado por uma PR que outra acabara de
mexer. O objetivo aqui é que **nada se perca em silêncio**: cada PR entra como um merge
separado, cada conflito é entendido pelos dois lados antes de ser resolvido, e cada decisão
fica escrita no commit.

Ferramenta: `scripts/mergedev.py` (Python 3.9+, `git`, `gh` autenticado). Chame pelo caminho
absoluto da skill, de dentro do repositório do projeto. O script só lê o GitHub e faz fetch;
não faz push, não fecha PR, não apaga branch. Enviar o resultado é decisão do usuário.

Regras que valem o tempo todo:

- **Uma PR por vez, com `--no-ff`.** Cada PR vira um commit de merge próprio, auditável e
  reversível sozinho (`git revert -m 1`). Quando a branch for enviada, o GitHub reconhece
  esses merges e marca as PRs como mergeadas (squash não faria isso).
- **"Aqui" (HEAD) é a sua branch mais as PRs já integradas.** Aceitar o lado da PR em bloco
  apaga o trabalho da PR anterior; aceitar o seu lado em bloco descarta a PR atual. Resolva
  por trecho, nunca por arquivo inteiro sem ler os dois lados.
- **Dúvida real sobre intenção não se resolve no chute.** Quando as duas mudanças não cabem
  juntas e nada na PR, nos commits ou no código diz qual vale, pare e pergunte ao usuário
  com uma proposta concreta (o que ficaria, o que sairia, por quê).
- **Tudo local até o fim.** Push, fechar PR, apagar branch e mudar base de PR só com o
  usuário pedindo.

## Passo 0 — Ponto de partida seguro

1. `gh auth status` funciona e você está dentro do repositório certo (`gh repo view`).
2. A branch atual é a de integração. Se for `main`/`master`, confirme com o usuário antes:
   integrar um lote em produção é outra decisão.
3. Árvore limpa (`git status --porcelain` vazio). Se houver alterações, peça para commitar
   ou guardar; não faça stash por conta própria, porque o `stash pop` depois pode conflitar
   com o que você mergeou.
4. Branch no mesmo ponto do remoto: `git pull --ff-only`. Se divergiu, pare e mostre ao
   usuário; mergear PRs por cima de uma divergência só piora o problema.

## Passo 1 — Plano

```bash
python3 /caminho/da/skill/scripts/mergedev.py plano
```

O que ele faz: lista as PRs abertas (`gh pr list`), baixa o head de cada uma em
`refs/mergedev/pr-N` (funciona também para PR de fork), descarta as que já estão na branch,
descobre PRs empilhadas (a base de uma é o head de outra), define a ordem e cria um backup
da branch em `refs/mergedev/backup/...` antes de qualquer merge.

Ordem padrão (`cadeia`): PRs-mãe por número crescente, cada uma seguida das suas filhas. A
filha vem logo depois da mãe porque, com a mãe já dentro, o diff dela é só o que ela mesma
fez; mergear a filha sem a mãe traz a mãe inteira junto, sem controle. `--ordem numero`
segue o número, mantendo mãe antes de filha.

Ficam fora por padrão, listadas com o motivo: rascunhos (`--rascunhos` inclui), PRs com
label de bloqueio (`wip`, `hold`, `do-not-merge`...), PRs cuja base não é a branch atual
(`--todas` ou `--base outra`) e filhas de PRs excluídas. `--pr 12 15` restringe a essas e
ignora os filtros.

Mostre a tabela ao usuário antes de começar e aponte os avisos: `GitHub: conflita com a
base`, `CI falhou`, `revisão pediu mudanças`, `grande`. Esses avisos vêm do estado da PR
no GitHub; conflito ali é relativo à base remota, não à sua branch com as outras PRs já
dentro, portanto espere mais conflitos do que o GitHub mostra. Se o usuário quiser tirar
ou reordenar algo, refaça o plano com `--pr` na ordem desejada.

Antes de mergear, leia o que cada PR se propõe a fazer. É a referência que você vai usar
para julgar conflitos depois:

```bash
gh pr view N --json title,body,commits --jq '.title, .body, (.commits[] | .messageHeadline)'
```

Guarde uma linha por PR (o que muda, onde). Descrições longas: leia inteiras, mas anote só
o essencial.

## Passo 2 — Uma PR por vez

```bash
python3 /caminho/da/skill/scripts/mergedev.py mergear N
```

Ele confere árvore limpa, branch certa e dependência mergeada, e faz
`git merge --no-ff` com `merge.conflictStyle=zdiff3` (os marcadores mostram também a
versão-base, o que torna a intenção de cada lado muito mais legível).

- **Saiu limpo**: rode a verificação rápida do projeto antes da próxima PR (`checar` lista
  as candidatas; tipos ou lint em geral são as mais baratas). Merge limpo não quer dizer
  compatível: a PR A renomeou uma função e a PR B chama o nome antigo; o git não vê isso.
  Se a verificação quebrar, veja o Passo 4.
- **Conflito** (código de saída 2): vá para o Passo 3.
- Se a PR não deve entrar agora (CI quebrada, revisão pendente, decisão do usuário):
  `pular N --motivo "..."` tira do plano e aborta o merge se ele estiver aberto. Se houver
  filhas, elas precisam ser puladas também ou a mãe mergeada depois.

Registre o andamento: o script grava `plano.json` e `log.md` em `.git/mergedev/`. Se o
contexto for resumido ou a sessão cair, `plano` de novo recompõe o estado (as PRs já
mergeadas são detectadas pela ancestralidade e saem da lista).

## Passo 3 — Resolver conflitos sem perder nada

```bash
python3 /caminho/da/skill/scripts/mergedev.py conflitos            # resumo: tipo, classe, hunks, tamanho de cada lado
python3 /caminho/da/skill/scripts/mergedev.py conflitos ARQUIVO    # commits de cada lado, diff base→aqui, diff base→PR, trechos marcados
```

Trabalhe arquivo a arquivo, nesta sequência:

1. **Entenda os dois lados antes de tocar no arquivo.** O detalhe mostra quais commits de
   cada lado mexeram ali e o que cada um mudou desde a base. Junte isso com a descrição da
   PR. A pergunta não é "qual versão escolher", é "o que cada pessoa quis fazer e como as
   duas intenções cabem no mesmo arquivo".
2. **Classifique o conflito** e siga o roteiro de
   [`references/resolucao.md`](references/resolucao.md), que cobre: mesma região editada
   pelos dois, arquivo apagado de um lado e editado do outro (quase sempre um rename),
   criado dos dois lados, lockfiles, arquivos gerados, migrações, binários, listas de
   registro (imports, rotas, enums, union types), versões e changelogs. Leia o arquivo de
   referência na primeira vez que aparecer um conflito nesta sessão.
3. **Escreva a resolução no arquivo**, trecho por trecho. Os casos comuns:
   - As duas mudanças são independentes na mesma região (cada lado adicionou um item, uma
     função, um case): mantenha as duas, na ordem que o arquivo já segue.
   - Um lado reescreveu o trecho e o outro fez um ajuste pequeno dentro dele: pegue a
     reescrita e reaplique o ajuste nela.
   - Os dois corrigiram o mesmo problema de jeitos diferentes: fique com uma correção
     (a mais completa ou a mais alinhada com o resto do código) e diga isso na nota.
   - As duas são incompatíveis por decisão de produto, não por texto: pergunte.
4. **`git add` no arquivo resolvido** e confira que não ficou marcador com `checar`.
   Para lockfile e arquivo gerado, não edite à mão: resolva o manifesto e regenere.
5. **Feche o merge documentando cada decisão:**

   ```bash
   python3 /caminho/da/skill/scripts/mergedev.py concluir \
     --nota "src/models/Notification.ts: os dois lados adicionaram um tipo ao union; mantidos os dois" \
     --nota "package-lock.json: regenerado com pnpm install --lockfile-only após unir o package.json"
   ```

   Uma nota por arquivo, dizendo o que ficou de cada lado e por quê. Isso vai para a
   mensagem do commit de merge; é o que permite a quem revisar depois entender uma escolha
   sem refazer a análise. O comando recusa concluir sem nota, com marcador sobrando ou com
   arquivo não resolvido.

Depois do `concluir`, rode a verificação rápida como num merge limpo.

Cuidado com arquivos grandes: não leia um diff de milhares de linhas inteiro. O detalhe do
`conflitos` limita os diffs e mostra os trechos marcados com contexto; abra regiões
específicas do arquivo quando precisar de mais.

## Passo 4 — Conflitos que o git não marca

Quando a verificação quebra depois de um merge (limpo ou resolvido), a causa quase sempre
está na interseção entre esta PR e as anteriores: símbolo renomeado, assinatura alterada,
arquivo movido, export removido, dois arquivos de migração com o mesmo número, teste de
snapshot desatualizado. Encontre pelo erro e por `git log -p` dos dois lados no símbolo.

Corrija num commit separado logo após o merge, por exemplo
`fix: integra PR #12 com a renomeação da PR #7`, e registre com
`nota 12 "..."`. Separado porque fica claro no histórico o que foi merge e o que foi
adaptação; quem for revisar a PR mergeada entende cada passo. Não reescreva a PR
inteira para "melhorar" nada: só o necessário para as duas conviverem.

## Passo 5 — Fechamento

1. Rode a verificação completa do projeto (build, testes) ao menos uma vez no fim, mesmo
   que tenha rodado as rápidas no meio.
2. `python3 /caminho/da/skill/scripts/mergedev.py relatorio` gera o resumo em Markdown
   (ordem, resultado de cada PR, conflitos e notas, PRs fora do plano, backup para
   desfazer, próximos passos). Entregue esse resumo ao usuário.
3. Deixe claro que **nada foi enviado** e o que acontece ao enviar: `git push origin dev`
   faz o GitHub marcar como mergeadas as PRs cuja base é a branch enviada; PRs empilhadas
   (base em outra PR) continuam abertas até a branch-mãe ser apagada ou a base da PR ser
   trocada (`gh pr edit N --base dev`, só se o usuário pedir).
4. `limpar` remove as refs temporárias `refs/mergedev/pr-*`; o backup fica.

## Se algo der errado

- Abortar o merge atual: `pular N --motivo ...` (faz `git merge --abort`).
- Desfazer uma PR já mergeada: `git revert -m 1 <commit do merge>`.
- Voltar ao ponto antes de tudo: `git reset --hard <ref de backup>` (está no plano e no
  relatório). Nunca `push --force`.

## Armadilhas conhecidas

- **`=======` em Markdown/RST não é marcador**: é título. O `checar` só falha com
  `<<<<<<<`, `>>>>>>>` e `|||||||`; linhas de `=======` aparecem como aviso.
- **Lockfile "resolvido" escolhendo um lado** instala dependências faltando. Regenere.
- **Duas migrações com o mesmo número/timestamp** passam no merge e quebram no deploy.
- **A branch da PR tem merges da dev dentro** (o autor atualizou a branch): normal; os
  conflitos aparecem só no que a PR mudou de fato.
- **PR filha mergeada sem a mãe** traz a mãe inteira junto, sem o nome dela no histórico.
  O `mergear` recusa; se precisar mesmo, mergeie a mãe primeiro ou pule as duas.
- **Autor fez `--force` na branch da PR** depois do plano: o `mergear` avisa que o head mudou
  e usa o atual. Se a mudança for grande, releia a descrição da PR.

## Checklist de pronto

- [ ] Plano mostrado ao usuário; PRs fora dele listadas com motivo
- [ ] Cada PR em um commit de merge `--no-ff`; cada conflito com nota no commit
- [ ] Nenhum marcador sobrando (`checar` limpo); lockfiles e gerados regenerados, não editados
- [ ] Verificação rápida após cada merge; completa no fim; ajustes semânticos em commits separados
- [ ] Relatório entregue; backup informado; push deixado para o usuário
