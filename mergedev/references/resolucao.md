# Roteiro de resolução por tipo de conflito

Vocabulário: **base** é o ancestral comum; **aqui** (HEAD, "ours") é a sua branch com as
PRs já integradas; **PR** (MERGE_HEAD, "theirs") é a PR sendo mergeada. Com `zdiff3`, cada
trecho marcado traz as três versões:

```
<<<<<<< HEAD
(versão aqui)
||||||| base
(versão base)
=======
(versão da PR)
>>>>>>> refs/mergedev/pr-N
```

Compare cada lado **com a base**, não um com o outro: "o que aqui mudou desde a base" e "o
que a PR mudou desde a base" são as duas intenções. A resolução é a base com as duas
intenções aplicadas.

## 1. Mesma região editada pelos dois (UU)

| O que você vê | Resolução |
|---|---|
| Cada lado **adicionou** algo no mesmo ponto (item de lista, membro de enum/union, case, rota, import, método) | Mantenha os dois, na ordem/convenção do arquivo. Veja se os dois adicionaram a *mesma* coisa com nomes diferentes; se sim, uma só, e ajuste quem usa a outra. |
| Um lado **reescreveu** o trecho, o outro fez um **ajuste pontual** dentro dele | Fique com a reescrita e reaplique o ajuste nela (procure o equivalente do que o ajuste tocava). Se o ajuste não faz mais sentido na reescrita, diga isso na nota. |
| Os dois **corrigiram o mesmo bug** de jeitos diferentes | Uma correção só. Prefira a mais completa, a com teste, ou a do autor da área. Nota obrigatória dizendo qual ficou e por quê. |
| Um lado **moveu** o trecho para outro lugar/arquivo e o outro o **editou** | Aplique a edição no destino novo. `git log -p -S'trecho' MERGE_HEAD` ou `grep` encontram para onde foi. |
| Só **formatação** difere (indentação, aspas, ordem de imports) | Repita o merge ignorando espaços para confirmar: `git merge --abort` e `git merge -X ignore-space-change ...` manualmente só para ver; se ainda conflitar, é conteúdo. Resolva e rode o formatador do projeto no arquivo. |
| Mudanças **incompatíveis por decisão** (dois comportamentos diferentes para a mesma regra) | Não decida sozinho. Mostre ao usuário os dois trechos, a intenção de cada PR e uma proposta. |

Para ver a intenção de um lado com mais contexto que o diff do arquivo:
`git log --format='%h %an · %s%n%b' BASE..HEAD -- ARQUIVO` (e `BASE..MERGE_HEAD`).

## 2. Apagado de um lado, modificado do outro (UD / DU)

Quase sempre é um **rename ou move** que o git não detectou por causa da edição do outro
lado. Antes de aceitar a exclusão:

1. Descubra para onde o conteúdo foi: `git log --diff-filter=A --name-only --format= BASE..LADO_QUE_APAGOU`
   lista arquivos criados por esse lado; `git grep -n 'função ou trecho' LADO_QUE_APAGOU` acha o destino.
2. Encontrou o destino: aplique ali a modificação do outro lado (`git diff BASE LADO_QUE_EDITOU -- ARQUIVO`
   mostra exatamente o que reaplicar) e confirme a exclusão (`git rm ARQUIVO`).
3. Não encontrou e a exclusão é intencional (recurso removido): confirme que a modificação
   do outro lado não é um fix necessário em outro ponto. Se for parte de um recurso vivo,
   a exclusão provavelmente está errada para esta integração; pergunte.
4. Para manter o arquivo: `git checkout --ours -- ARQUIVO` (aqui) ou `--theirs` (PR), depois `git add`.

## 3. Criado dos dois lados (AA)

Dois autores criaram o mesmo caminho. Compare os conteúdos (`git diff :2:ARQUIVO :3:ARQUIVO`):

- **Mesmo propósito** (o mesmo helper, o mesmo componente): una em um só, sem duplicar
  funções; se os nomes internos diferem, escolha um e ajuste os usos do outro lado.
- **Propósitos diferentes com o mesmo nome**: um deles precisa de outro nome. Renomeie o
  do lado da PR (é o que ainda não está integrado) e ajuste os imports dela.
- Arquivos de **configuração/dados** criados dos dois lados: una as chaves; chave igual com
  valor diferente é decisão de produto, pergunte.

## 4. Lockfiles (package-lock.json, pnpm-lock.yaml, yarn.lock, Cargo.lock, poetry.lock, Gemfile.lock, go.sum...)

Nunca edite à mão. O lockfile é derivado do manifesto:

1. Resolva o manifesto primeiro (`package.json`, `pyproject.toml`, `Cargo.toml`...): união
   das dependências; versão diferente da mesma dependência → a mais nova, salvo pino
   intencional comentado.
2. Descarte o lockfile em conflito e regenere **sem instalar nada novo**:

   | Gerenciador | Comando |
   |---|---|
   | npm | `git checkout --theirs package-lock.json && npm install --package-lock-only` |
   | pnpm | `git checkout --theirs pnpm-lock.yaml && pnpm install --lockfile-only` |
   | yarn (berry) | `git checkout --theirs yarn.lock && yarn install --mode update-lockfile` |
   | yarn (classic) | `git checkout --theirs yarn.lock && yarn install --frozen-lockfile` falha se precisar mudar; use `yarn install` |
   | bun | `bun install --lockfile-only` (ou apenas `bun install`) |
   | poetry | `poetry lock --no-update` |
   | uv | `uv lock` |
   | cargo | `cargo update --workspace` (só re-resolve; não atualiza versões) |
   | go | `go mod tidy` |
   | composer | `composer update --lock` |
   | bundler | `bundle lock` |

3. Confira que o diff do lockfile só contém as dependências esperadas
   (`git diff --cached --stat -- lockfile` e uma olhada nos pacotes novos). Um lockfile
   que mudou 3 mil linhas por causa de uma dependência nova merece suspeita (gerenciador
   ou versão diferente da do time).
4. Sem rede ou sem o gerenciador: fique com o lado que inclui as dependências novas da PR
   e **diga no relatório** que o lockfile precisa ser regenerado.

## 5. Arquivos gerados (dist/, build/, snapshots, openapi.json, schema.graphql, *.pb.go, *.g.dart, CHANGELOG gerado)

Não mescle texto gerado. Resolva as fontes e regenere com o comando do projeto (build,
`--update-snapshot`, gerador de schema). Snapshot de teste: regenere e **leia** o novo
snapshot; snapshot que muda de forma inesperada é um conflito semântico, não um gerado a
ser aceito.

## 6. Migrações de banco

Conflito raro no arquivo, comum na numeração: duas PRs criaram `0042_*.py`, dois
timestamps Prisma na mesma pasta, dois `V12__*.sql`. O merge passa limpo e o deploy quebra.

- Depois de cada merge que traz migração, liste a pasta e procure número/timestamp
  duplicado ou fora de ordem. Ferramentas: Django `makemigrations --check` /
  `showmigrations`, Alembic `heads` (deve haver uma só; se duas, `alembic merge`), Rails
  `db:migrate:status`, Prisma a ordem é o nome da pasta, Flyway/Knex/TypeORM a numeração.
- Renumere a migração da PR (a que ainda não foi aplicada em nenhum ambiente), não a que já
  está na branch. Ajuste dependências explícitas (`dependencies = [...]`, `down_revision`).
- Duas migrações mexendo na mesma tabela de jeitos incompatíveis: pergunte.

## 7. Binários (imagens, fontes, PDFs, .xlsx)

Não há merge. `git checkout --ours -- ARQUIVO` ou `--theirs`, depois `git add`. Se os dois
lados trouxeram versões diferentes do mesmo asset, pergunte qual vale ou mantenha os dois
com nomes diferentes se o código referencia os dois. Anote.

## 8. Listas de registro

Imports, rotas, providers, `index.ts` que reexporta, enums, union types, tabelas de
tradução (i18n), fixtures, listas de permissões, `CODEOWNERS`. Padrão: **união**,
respeitando a ordem/alfabetização do arquivo e sem duplicar. Chave igual com valor
diferente (duas traduções para a mesma chave, dois handlers para a mesma rota) é conflito
de intenção: resolva pela descrição das PRs ou pergunte.

## 9. Versões e changelogs

`version` em manifesto: a maior (se os dois subiram) ou a da branch (se só a PR subiu e o
projeto versiona no release). `CHANGELOG.md` escrito à mão: una as entradas sob a seção
certa (em geral "Unreleased"), uma linha por PR, sem perder nenhuma.

## 10. Depois de resolver: o que o git não marca

Rode a verificação mais rápida do projeto. Sintomas típicos de conflito semântico e onde
olhar:

| Sintoma | Causa provável |
|---|---|
| "X is not defined" / import quebrado | A PR usa algo que outra PR renomeou ou moveu. `git log -p -S'X' HEAD` acha o rename. |
| Assinatura/tipo não bate | Uma PR mudou parâmetros; a outra chama do jeito antigo. Adapte a chamada. |
| Teste que passava quebrou | Expectativa de um lado contra comportamento do outro. Decida pelo que as duas PRs pretendiam; não "ajuste o teste para passar". |
| Duas definições do mesmo símbolo | AA ou adições duplicadas em listas. Remova uma e unifique usos. |
| Migração falha | Numeração duplicada ou ordem (ver 6). |

Correções entram em commit separado logo após o merge (`fix: integra PR #N com ...`) e
são registradas com `nota N "..."` para aparecerem no relatório.

## Nota de resolução: como escrever

Uma linha por arquivo, no formato `arquivo: o que ficou de cada lado e por quê`:

- `src/models/Notification.ts: os dois lados adicionaram um tipo ao union NotificationType (generation_provider_unavailable da #7, starboost_platform_confirmed da #9); mantidos os dois e os dois no enum do schema`
- `apps/web/src/pages/Login.tsx: a #9 reescreveu o formulário; reaplicada nela a validação de e-mail que a #8 tinha adicionado`
- `docs/guia.md: a PR moveu o conteúdo para docs/manual.md; a seção "Atalhos" criada na dev foi reaplicada no manual.md`
- `pnpm-lock.yaml: regenerado com pnpm install --lockfile-only após unir o package.json`
- `assets/logo.png: mantida a versão da PR #10 (mais recente, confirmada pelo usuário)`

O que evitar: "resolvido mantendo ours", "aceitei theirs", "juntei os dois" sem dizer o quê.
