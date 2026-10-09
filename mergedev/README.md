# mergedev

Integra as pull requests abertas do GitHub na branch em que você está (normalmente a
`dev`), uma PR por vez, na ordem certa, resolvendo conflitos sem perder alteração de
nenhum lado e deixando cada decisão escrita no commit de merge.

## Escopo

**Faz**

- Lista as PRs abertas do repositório atual (`gh`), descarta as que já estão na branch e
  descobre PRs empilhadas (a base de uma é o head de outra): a filha só entra depois da mãe.
- Faz um merge `--no-ff` por PR, cada um reversível sozinho. Cria um backup da branch antes
  do primeiro merge.
- Em conflito, mostra o que cada lado mudou desde a base e quais commits mexeram no
  arquivo, para a resolução ser por intenção, não por "ours/theirs".
- Exige uma nota por arquivo resolvido; a nota vai para a mensagem do commit.
- Gera um relatório final: ordem, resultado de cada PR, conflitos e notas, PRs fora do
  plano, como desfazer.

**Não faz**

- Push, fechar PR, apagar branch ou trocar base de PR. Tudo fica local até você decidir.
- Revisão de código, rebase interativo ou squash.
- Resolver sozinha um conflito de decisão de produto: nesse caso ela pergunta.

## Requisitos

`git`, Python 3.9+ e o [GitHub CLI](https://cli.github.com) autenticado:

```bash
brew install gh && gh auth login
```

## Instalação

```bash
cp -r mergedev ~/.claude/skills/        # ou: ln -s "$PWD/mergedev" ~/.claude/skills/mergedev
```

## Uso

Entre no projeto, na branch de integração, com a árvore limpa, e peça ao agente
"mergeia as PRs do time na dev" (ou `/mergedev`). Por baixo, o fluxo é:

```bash
S=~/.claude/skills/mergedev/scripts/mergedev.py
python3 $S plano                    # ordem das PRs, avisos do GitHub, backup da branch
python3 $S mergear 7                # merge --no-ff; sai com código 2 se houver conflito
python3 $S conflitos                # resumo: tipo, classe (lockfile, gerado...), hunks
python3 $S conflitos src/x.ts       # commits e diff de cada lado desde a base, trechos marcados
python3 $S checar                   # nada pendente, sem marcador; lista as verificações do projeto
python3 $S concluir --nota "src/x.ts: mantidos os dois membros do union; ..."
python3 $S pular 9 --motivo "CI quebrada"   # tira do plano (aborta o merge se aberto)
python3 $S relatorio                # Markdown final; também salvo em .git/mergedev/
python3 $S limpar                   # remove refs temporárias; o backup fica
```

Opções do `plano`: `--rascunhos` inclui drafts, `--todas` inclui PRs com outra base,
`--base main` muda o alvo, `--pr 12 15` restringe a essas, `--ordem numero` segue o número
em vez de cadeia mãe→filha.

O estado (`plano.json`, `log.md`, `relatorio.md`) fica em `.git/mergedev/`, fora da árvore
de trabalho. Se a sessão cair, `plano` de novo recompõe tudo.

## Arquivos

| Arquivo | Para quê |
|---|---|
| `SKILL.md` | O método que o agente segue: ponto de partida seguro, plano, loop por PR, resolução, conflitos semânticos, fechamento. |
| `scripts/mergedev.py` | Os subcomandos acima. Só lê o GitHub e faz fetch. |
| `references/resolucao.md` | Roteiro por tipo de conflito: mesma região, apagado de um lado, criado dos dois, lockfiles, gerados, migrações, binários, listas, versões. |
| `agents/openai.yaml` | Metadados de exibição para agentes que leem esse formato. |
