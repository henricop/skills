#!/usr/bin/env python3
"""mergedev — integra as PRs abertas do GitHub na branch atual, uma por vez.

Uso:
  python3 mergedev.py plano [--base BRANCH] [--todas] [--rascunhos] [--ordem cadeia|numero]
                            [--pr N ...] [--sem-fetch]
  python3 mergedev.py mergear N
  python3 mergedev.py conflitos [ARQUIVO] [--completo]
  python3 mergedev.py checar
  python3 mergedev.py concluir --nota "arquivo: o que foi mantido e por quê" [--nota ...]
  python3 mergedev.py pular N --motivo "..."
  python3 mergedev.py nota N "texto"
  python3 mergedev.py relatorio
  python3 mergedev.py limpar [--tudo]

O estado fica em <git-dir>/mergedev/ (plano.json, log.md, relatorio.md), fora da árvore
de trabalho. O script só lê o GitHub (gh pr list/view) e faz fetch; nunca faz push,
não fecha PR e não apaga branch. Enviar o resultado é decisão de quem usa.
"""
import argparse
import datetime as dt
import heapq
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

CAMPOS_PR = (
    "number,title,headRefName,baseRefName,headRefOid,author,isDraft,labels,createdAt,"
    "updatedAt,mergeable,mergeStateStatus,reviewDecision,isCrossRepository,url,"
    "additions,deletions,changedFiles,statusCheckRollup"
)
LABELS_BLOQUEIO = {
    "do-not-merge", "do not merge", "dont-merge", "wip", "hold", "on hold", "on-hold",
    "blocked", "bloqueada", "bloqueado", "nao-mergear", "não mergear", "nao mergear",
}
NOMES_LOCK = {
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "bun.lock", "composer.lock", "Cargo.lock", "poetry.lock", "Pipfile.lock", "uv.lock",
    "pdm.lock", "Gemfile.lock", "go.sum", "mix.lock", "pubspec.lock", "packages.lock.json",
    "Podfile.lock", "flake.lock", "gradle.lockfile",
}
RE_GERADO = re.compile(
    r"(\.snap$|(^|/)__snapshots__/|(^|/)(dist|build|coverage|out|\.next|target)/"
    r"|\.min\.(js|css)$|openapi\.(json|ya?ml)$|schema\.graphql$|\.generated\.|\.g\.dart$"
    r"|\.pb\.go$|_pb2\.py$|(^|/)CHANGELOG\.md$)"
)
RE_MIGRACAO = re.compile(r"(^|/)(migrations?|migrate|alembic/versions|db/migrate|prisma/migrations)/")
RE_MARCADOR = re.compile(r"^(<{7}|>{7}|\|{7})( |$)")
RE_RESIDUO = re.compile(r"\.(orig|rej)$|\.(BACKUP|BASE|LOCAL|REMOTE)\.")

TIPOS_CONFLITO = {
    (1, 2, 3): ("UU", "ambos modificaram"),
    (1, 2): ("UD", "modificado aqui, apagado pela PR"),
    (1, 3): ("DU", "apagado aqui, modificado pela PR"),
    (2, 3): ("AA", "criado dos dois lados"),
    (2,): ("AU", "criado aqui (rename/add do outro lado)"),
    (3,): ("UA", "criado pela PR (rename/add deste lado)"),
}

DICAS = {
    "lockfile": "não edite à mão: resolva o manifesto (package.json etc.) e regenere o lockfile",
    "gerado": "arquivo gerado: regenere com o comando do projeto em vez de mesclar texto",
    "migração": "migração: confira numeração/timestamp duplicado e a ordem de aplicação",
    "binário": "binário: não há merge; escolha um lado com git checkout --ours/--theirs -- ARQUIVO e anote",
    "UD": "a PR apagou o arquivo: veja se o conteúdo foi movido/renomeado antes de aceitar a exclusão",
    "DU": "este lado apagou o arquivo: veja onde o conteúdo foi parar e aplique a mudança da PR lá",
    "AA": "os dois lados criaram o arquivo: una o conteúdo e remova duplicatas",
}


# ---------- utilidades ----------

def falha(msg: str, codigo: int = 1):
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(codigo)


def aviso(msg: str):
    print(f"AVISO: {msg}", file=sys.stderr)


def agora() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def rodar(args: List[str], entrada: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, input=entrada, capture_output=True, text=True)


def git(*args: str, check: bool = True) -> str:
    r = rodar(["git", *args])
    if check and r.returncode != 0:
        falha(f"git {' '.join(args)}\n{(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def git_ok(*args: str) -> bool:
    return rodar(["git", *args]).returncode == 0


def gh(*args: str) -> str:
    if not shutil.which("gh"):
        falha("gh (GitHub CLI) não encontrado. Instale com `brew install gh` e rode `gh auth login`.")
    r = rodar(["gh", *args])
    if r.returncode != 0:
        falha(f"gh {' '.join(args[:3])}\n{r.stderr.strip()}")
    return r.stdout


def git_dir() -> Path:
    return Path(git("rev-parse", "--absolute-git-dir"))


def pasta_estado() -> Path:
    p = git_dir() / "mergedev"
    p.mkdir(exist_ok=True)
    return p


def caminho_plano() -> Path:
    return pasta_estado() / "plano.json"


def carregar_plano(obrigatorio: bool = True) -> Optional[dict]:
    p = caminho_plano()
    if not p.exists():
        if obrigatorio:
            falha("não há plano. Rode `mergedev.py plano` primeiro.")
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def salvar_plano(plano: dict):
    caminho_plano().write_text(json.dumps(plano, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def registrar(texto: str):
    with open(pasta_estado() / "log.md", "a", encoding="utf-8") as f:
        f.write(f"- {agora()} {texto}\n")


def branch_atual() -> str:
    b = git("rev-parse", "--abbrev-ref", "HEAD")
    if b == "HEAD":
        falha("HEAD solto (detached). Faça checkout da branch de destino antes.")
    return b


def merge_em_andamento() -> Optional[str]:
    r = rodar(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"])
    return r.stdout.strip() if r.returncode == 0 else None


def arvore_limpa() -> bool:
    return git("status", "--porcelain", "--untracked-files=no") == ""


def passo_por_numero(plano: dict, n: int) -> Optional[dict]:
    return next((p for p in plano["passos"] if p["numero"] == n), None)


def script_nome() -> str:
    return os.path.basename(sys.argv[0]) or "mergedev.py"


def truncar(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def tabela(linhas: List[List[str]], cabecalho: List[str]):
    larguras = [len(c) for c in cabecalho]
    for l in linhas:
        for i, c in enumerate(l):
            larguras[i] = max(larguras[i], len(c))
    fmt = "  ".join("{:<" + str(w) + "}" for w in larguras)
    print(fmt.format(*cabecalho).rstrip())
    print("  ".join("-" * w for w in larguras))
    for l in linhas:
        print(fmt.format(*l).rstrip())


def resumo_ci(itens) -> str:
    if not itens:
        return "—"
    ruins = {"FAILURE", "ERROR", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE", "CANCELLED"}
    pend = {"PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "WAITING", ""}
    estados = [(i.get("conclusion") or i.get("state") or i.get("status") or "").upper() for i in itens]
    if any(e in ruins for e in estados):
        return "falhou"
    if any(e in pend for e in estados):
        return "pendente"
    return "ok"


# ---------- plano ----------

def ordenar(numeros: List[int], pai_de: Dict[int, Optional[int]], modo: str) -> List[int]:
    conjunto = set(numeros)
    filhos = {n: [] for n in numeros}
    raizes = []
    for n in numeros:
        pai = pai_de.get(n)
        if pai in conjunto:
            filhos[pai].append(n)
        else:
            raizes.append(n)
    for lst in filhos.values():
        lst.sort()
    raizes.sort()
    resultado: List[int] = []
    if modo == "cadeia":
        pilha = list(reversed(raizes))
        while pilha:
            n = pilha.pop()
            if n in resultado:
                continue
            resultado.append(n)
            pilha.extend(reversed(filhos[n]))
    else:
        pendentes = {n: (1 if pai_de.get(n) in conjunto else 0) for n in numeros}
        heap = [n for n in numeros if pendentes[n] == 0]
        heapq.heapify(heap)
        while heap:
            n = heapq.heappop(heap)
            resultado.append(n)
            for f in filhos[n]:
                pendentes[f] -= 1
                if pendentes[f] == 0:
                    heapq.heappush(heap, f)
    faltando = sorted(conjunto - set(resultado))
    if faltando:
        aviso(f"dependência circular entre as PRs {faltando}; anexadas no fim por número")
        resultado += faltando
    return resultado


def cmd_plano(a):
    if merge_em_andamento():
        falha("há um merge em andamento. Conclua (`concluir`) ou aborte (`pular N`) antes de replanejar.")
    branch = branch_atual()
    alvo = a.base or branch
    if a.de_json:
        prs = json.loads(Path(a.de_json).read_text(encoding="utf-8"))
        repo = a.repo or "(local)"
    else:
        repo = a.repo or json.loads(gh("repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]
        prs = json.loads(gh("pr", "list", "--repo", repo, "--state", "open", "--limit", "200", "--json", CAMPOS_PR))
    prs.sort(key=lambda p: p["number"])

    if prs and not a.sem_fetch:
        refspecs = [f"+refs/pull/{p['number']}/head:refs/mergedev/pr-{p['number']}" for p in prs]
        r = rodar(["git", "fetch", "--quiet", "origin", *refspecs])
        if r.returncode != 0:
            aviso("fetch dos heads das PRs falhou; usando os SHAs informados pelo GitHub\n" + r.stderr.strip())

    por_head: Dict[str, dict] = {}
    for p in prs:
        p["ref"] = f"refs/mergedev/pr-{p['number']}"
        r = rodar(["git", "rev-parse", "-q", "--verify", p["ref"]])
        p["sha"] = r.stdout.strip() if r.returncode == 0 else p.get("headRefOid", "")
        if not p.get("isCrossRepository"):
            por_head.setdefault(p["headRefName"], p)

    mergeadas = {p["number"] for p in prs if p["sha"] and git_ok("merge-base", "--is-ancestor", p["sha"], "HEAD")}
    explicitas = set(a.pr or [])
    motivos: Dict[int, str] = {}
    for p in prs:
        n = p["number"]
        labels = {l["name"].lower() for l in (p.get("labels") or [])}
        bloqueio = sorted(labels & LABELS_BLOQUEIO)
        if n in mergeadas:
            motivos[n] = "já está na branch"
        elif explicitas and n not in explicitas:
            motivos[n] = "fora da seleção --pr"
        elif p.get("isDraft") and not a.rascunhos and n not in explicitas:
            motivos[n] = "rascunho (inclua com --rascunhos ou --pr)"
        elif bloqueio and n not in explicitas:
            motivos[n] = f"label '{bloqueio[0]}' (inclua com --pr)"

    # pai = PR cujo head é a base desta (PR empilhada)
    pai_de: Dict[int, Optional[int]] = {}
    for p in prs:
        pai = por_head.get(p["baseRefName"])
        pai_de[p["number"]] = pai["number"] if pai and pai["number"] != p["number"] else None

    if not a.todas and not explicitas:
        incluidas = set()
        mudou = True
        while mudou:
            mudou = False
            heads_incluidos = {p["headRefName"] for p in prs if p["number"] in incluidas}
            for p in prs:
                n = p["number"]
                if n in motivos or n in incluidas:
                    continue
                pai = pai_de[n]
                if p["baseRefName"] == alvo or p["baseRefName"] in heads_incluidos or (pai in mergeadas):
                    incluidas.add(n)
                    mudou = True
        for p in prs:
            if p["number"] not in motivos and p["number"] not in incluidas:
                motivos[p["number"]] = f"base '{p['baseRefName']}' não é '{alvo}' (inclua com --todas, --base ou --pr)"

    mudou = True
    while mudou:
        mudou = False
        for p in prs:
            n, pai = p["number"], pai_de[p["number"]]
            if n not in motivos and pai is not None and pai in motivos and pai not in mergeadas:
                motivos[n] = f"depende da PR #{pai}, que ficou de fora ({motivos[pai]})"
                mudou = True

    candidatos = [p["number"] for p in prs if p["number"] not in motivos]
    pai_efetivo = {n: (None if pai_de[n] in mergeadas else pai_de[n]) for n in candidatos}
    ordem = ordenar(candidatos, pai_efetivo, a.ordem)
    por_num = {p["number"]: p for p in prs}

    anterior = carregar_plano(obrigatorio=False)
    concluidos: List[dict] = []
    backup = None
    if anterior and anterior.get("branch") == branch:
        # mantém o histórico das PRs já tratadas; uma PR pulada que voltou ao plano vira pendente de novo
        concluidos = [s for s in anterior["passos"] if s["status"] in ("mergeada", "pulada") and s["numero"] not in ordem]
        if anterior.get("backup") and git_ok("rev-parse", "-q", "--verify", anterior["backup"]):
            backup = anterior["backup"]
    if not backup:
        backup = f"refs/mergedev/backup/{branch.replace('/', '-')}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        git("update-ref", backup, "HEAD")

    passos = list(concluidos)
    base_ordem = len(passos)
    for i, n in enumerate(ordem, 1):
        p = por_num[n]
        avisos = []
        if p.get("mergeable") == "CONFLICTING":
            avisos.append("GitHub: conflita com a base")
        if p.get("reviewDecision") == "CHANGES_REQUESTED":
            avisos.append("revisão pediu mudanças")
        ci = resumo_ci(p.get("statusCheckRollup") or [])
        if ci == "falhou":
            avisos.append("CI falhou")
        if p.get("isCrossRepository"):
            avisos.append("vem de fork")
        if pai_efetivo.get(n):
            avisos.append(f"empilhada sobre #{pai_efetivo[n]}")
        if (p.get("changedFiles") or 0) > 80:
            avisos.append(f"grande: {p['changedFiles']} arquivos")
        passos.append({
            "ordem": base_ordem + i,
            "numero": n,
            "titulo": p["title"],
            "autor": (p.get("author") or {}).get("login", "?"),
            "url": p.get("url", ""),
            "head": p["headRefName"],
            "base": p["baseRefName"],
            "ref": p["ref"],
            "sha": p["sha"],
            "depende_de": pai_efetivo.get(n),
            "github": {"mergeable": p.get("mergeable"), "estado": p.get("mergeStateStatus"),
                       "revisao": p.get("reviewDecision") or "", "ci": ci},
            "tamanho": {"adicoes": p.get("additions", 0), "remocoes": p.get("deletions", 0),
                        "arquivos": p.get("changedFiles", 0)},
            "avisos": avisos,
            "status": "pendente",
            "conflitos": [],
            "notas": [],
            "commit": None,
        })

    plano = {
        "repo": repo,
        "branch": branch,
        "base_alvo": alvo,
        "ordem": a.ordem,
        "criado_em": agora(),
        "backup": backup,
        "fetch": not (a.sem_fetch or a.de_json),
        "passos": passos,
        "pulados": [{"numero": n, "titulo": por_num[n]["title"], "base": por_num[n]["baseRefName"],
                     "head": por_num[n]["headRefName"], "motivo": m} for n, m in sorted(motivos.items())
                    if n not in {s["numero"] for s in concluidos}],
    }
    salvar_plano(plano)
    registrar(f"plano: {len(ordem)} PR(s) para mergear em {branch} ({repo}); backup {backup}")

    print(f"Repositório: {repo}   Branch atual: {branch}   Alvo das PRs: {alvo}")
    print(f"Backup da branch antes de qualquer merge: {backup}")
    print(f"  (voltar tudo: git reset --hard {backup})\n")
    if not prs:
        print("Nenhuma PR aberta.")
        return
    pendentes = [s for s in passos if s["status"] == "pendente"]
    if pendentes:
        print(f"Ordem de merge ({a.ordem}: pai antes da filha; empates por número):")
        linhas = []
        for s in pendentes:
            g = s["github"]
            gh_txt = f"{(g['mergeable'] or '?').lower()}/{(g['revisao'] or '-').lower()}/ci:{g['ci']}"
            t = s["tamanho"]
            linhas.append([
                str(s["ordem"]), f"#{s['numero']}", truncar(s["titulo"], 58), s["autor"],
                f"{truncar(s['base'], 28)} ← {truncar(s['head'], 40)}", f"+{t['adicoes']}/-{t['remocoes']} ({t['arquivos']} arq)",
                gh_txt, "; ".join(s["avisos"]),
            ])
        tabela(linhas, ["ord", "PR", "título", "autor", "base ← head", "tamanho", "github", "avisos"])
    else:
        print("Nenhuma PR pendente para mergear.")
    if concluidos:
        print(f"\nJá tratadas neste plano (mantidas para o relatório): "
              + ", ".join(f"#{s['numero']} ({s['status']})" for s in concluidos))
    if plano["pulados"]:
        print("\nFora do plano:")
        for x in plano["pulados"]:
            print(f"  #{x['numero']} {truncar(x['titulo'], 60)} — {x['motivo']}")
    if pendentes:
        print(f"\nPróximo passo: python3 {script_nome()} mergear {pendentes[0]['numero']}")
    print(f"Plano salvo em {caminho_plano()}")


# ---------- conflitos ----------

def base_do_merge() -> str:
    mh = merge_em_andamento()
    if not mh:
        falha("nenhum merge em andamento (MERGE_HEAD não existe).")
    saida = git("merge-base", "HEAD", mh)
    return saida.splitlines()[0]


def entradas_nao_mescladas() -> Dict[str, Dict[int, str]]:
    saida = rodar(["git", "ls-files", "-u", "-z"]).stdout
    por_arquivo: Dict[str, Dict[int, str]] = {}
    for item in saida.split("\0"):
        if not item:
            continue
        meta, caminho = item.split("\t", 1)
        _modo, sha, estagio = meta.split()
        por_arquivo.setdefault(caminho, {})[int(estagio)] = sha
    return por_arquivo


def blob_binario(sha: str) -> bool:
    r = subprocess.run(["git", "cat-file", "-p", sha], capture_output=True)
    return b"\0" in r.stdout[:8000]


def classe_arquivo(caminho: str, binario: bool) -> str:
    if os.path.basename(caminho) in NOMES_LOCK:
        return "lockfile"
    if binario:
        return "binário"
    if RE_MIGRACAO.search(caminho):
        return "migração"
    if RE_GERADO.search(caminho):
        return "gerado"
    return "texto"


def numstat(de: str, ate: str, caminho: str) -> str:
    saida = rodar(["git", "diff", "--numstat", de, ate, "--", caminho]).stdout.strip()
    if not saida:
        return "igual"
    add, rem = saida.split("\t")[:2]
    return "binário" if add == "-" else f"+{add}/-{rem}"


def contar_hunks(caminho: str) -> int:
    p = Path(caminho)
    if not p.is_file():
        return 0
    return sum(1 for l in p.read_bytes().splitlines() if l.startswith(b"<<<<<<< "))


def descrever_conflitos() -> List[dict]:
    base = base_do_merge()
    mh = merge_em_andamento()
    itens = []
    for caminho, estagios in sorted(entradas_nao_mescladas().items()):
        chave = tuple(sorted(estagios))
        codigo, descricao = TIPOS_CONFLITO.get(chave, ("??", f"estágios {chave}"))
        sha_amostra = estagios.get(2) or estagios.get(3) or estagios.get(1)
        binario = blob_binario(sha_amostra) if sha_amostra else False
        classe = classe_arquivo(caminho, binario)
        itens.append({
            "arquivo": caminho, "codigo": codigo, "descricao": descricao, "classe": classe,
            "hunks": contar_hunks(caminho),
            "aqui": numstat(base, "HEAD", caminho), "pr": numstat(base, mh, caminho),
            "dica": DICAS.get(classe) or DICAS.get(codigo) or "",
        })
    return itens


def imprimir_resumo_conflitos():
    itens = descrever_conflitos()
    if not itens:
        print("Nenhum arquivo em conflito (tudo resolvido ou o merge foi limpo).")
        return
    print(f"{len(itens)} arquivo(s) em conflito. Lado 'aqui' = HEAD (sua branch + PRs já mergeadas); 'PR' = MERGE_HEAD.\n")
    linhas = [[i["arquivo"], i["codigo"], i["descricao"], i["classe"], str(i["hunks"]), i["aqui"], i["pr"]] for i in itens]
    tabela(linhas, ["arquivo", "tipo", "significado", "classe", "hunks", "aqui", "PR"])
    dicas = [(i["arquivo"], i["dica"]) for i in itens if i["dica"]]
    if dicas:
        print("\nAtenção:")
        for arq, d in dicas:
            print(f"  {arq}: {d}")
    print(f"\nDetalhe de um arquivo: python3 {script_nome()} conflitos ARQUIVO")


def imprimir_limitado(texto: str, limite: int, completo: bool):
    linhas = texto.splitlines()
    if completo or len(linhas) <= limite:
        print(texto)
        return
    print("\n".join(linhas[:limite]))
    print(f"(… {len(linhas) - limite} linhas omitidas; use --completo para ver tudo)")


def trechos_conflito(caminho: str, contexto: int = 3):
    p = Path(caminho)
    if not p.is_file():
        print("(arquivo não existe na árvore de trabalho)")
        return
    linhas = p.read_text(encoding="utf-8", errors="replace").splitlines()
    blocos = []
    i = 0
    while i < len(linhas):
        if linhas[i].startswith("<<<<<<< "):
            j = i
            while j < len(linhas) and not linhas[j].startswith(">>>>>>> "):
                j += 1
            blocos.append((i, min(j, len(linhas) - 1)))
            i = j + 1
        else:
            i += 1
    if not blocos:
        print("(sem marcadores de conflito no arquivo)")
        return
    for k, (ini, fim) in enumerate(blocos, 1):
        print(f"--- trecho {k}/{len(blocos)} (linhas {ini + 1}-{fim + 1}) ---")
        for idx in range(max(0, ini - contexto), min(len(linhas), fim + 1 + contexto)):
            marca = ">>" if RE_MARCADOR.match(linhas[idx]) or linhas[idx].startswith("=======") else "  "
            print(f"{idx + 1:5d} {marca} {linhas[idx]}")


def cmd_conflitos(a):
    if not a.arquivo:
        imprimir_resumo_conflitos()
        return
    caminho = a.arquivo
    estagios = entradas_nao_mescladas().get(caminho)
    base = base_do_merge()
    mh = merge_em_andamento()
    if estagios is None:
        falha(f"{caminho} não está em conflito (ou já foi resolvido com git add).")
    chave = tuple(sorted(estagios))
    codigo, descricao = TIPOS_CONFLITO.get(chave, ("??", f"estágios {chave}"))
    sha_amostra = estagios.get(2) or estagios.get(3) or estagios.get(1)
    binario = blob_binario(sha_amostra) if sha_amostra else False
    classe = classe_arquivo(caminho, binario)
    print(f"Arquivo: {caminho}\nTipo: {codigo} — {descricao}\nClasse: {classe}")
    dica = DICAS.get(classe) or DICAS.get(codigo)
    if dica:
        print(f"Atenção: {dica}")
    print(f"Versões: base={'sim' if 1 in estagios else 'não'}  aqui={'sim' if 2 in estagios else 'não'}  PR={'sim' if 3 in estagios else 'não'}")
    print(f"  ver uma versão: git show :1:{caminho} (base) | :2:{caminho} (aqui) | :3:{caminho} (PR)")

    print("\n== Commits deste lado (aqui) que tocaram o arquivo ==")
    print(git("log", "--format=%h %an · %s", f"{base}..HEAD", "--", caminho) or "(nenhum)")
    print("\n== Commits da PR que tocaram o arquivo ==")
    print(git("log", "--format=%h %an · %s", f"{base}..{mh}", "--", caminho) or "(nenhum)")

    if binario:
        print("\nArquivo binário: sem diff de texto. Escolha um lado e anote o motivo na nota do merge.")
        return

    limite = 250
    print("\n== O que este lado (aqui) mudou desde a base ==")
    imprimir_limitado(rodar(["git", "diff", base, "HEAD", "--", caminho]).stdout or "(nada)", limite, a.completo)
    print("\n== O que a PR mudou desde a base ==")
    imprimir_limitado(rodar(["git", "diff", base, mh, "--", caminho]).stdout or "(nada)", limite, a.completo)
    print("\n== Trechos em conflito na árvore de trabalho (zdiff3: entre ||||||| e ======= está a base) ==")
    trechos_conflito(caminho)


# ---------- checar ----------

def problemas_do_merge():
    problemas: List[str] = []
    avisos: List[str] = []
    for f in git("diff", "--name-only", "--diff-filter=U").splitlines():
        problemas.append(f"não resolvido (conflito aberto ou `git add` pendente): {f}")
    alterados = set(git("diff", "--cached", "--name-only").splitlines()) | set(git("diff", "--name-only").splitlines())
    for f in sorted(alterados):
        p = Path(f)
        if not p.is_file():
            continue
        dados = p.read_bytes()
        if b"\0" in dados[:8000]:
            continue
        for i, linha in enumerate(dados.decode("utf-8", "replace").splitlines(), 1):
            if RE_MARCADOR.match(linha):
                problemas.append(f"marcador de conflito em {f}:{i}: {linha[:50]}")
    for f in git("ls-files", "--others", "--exclude-standard").splitlines():
        if RE_RESIDUO.search(f):
            avisos.append(f"resíduo de mergetool não rastreado (apague ou ignore): {f}")
    r = rodar(["git", "diff", "--check", "--cached"])
    if r.returncode != 0 and r.stdout.strip():
        for linha in r.stdout.strip().splitlines():
            if "conflict marker" in linha:
                avisos.append(f"git diff --check: possível marcador (ou '=======' legítimo, ex. título Markdown): {linha}")
            else:
                avisos.append(f"git diff --check: {linha}")
    return problemas, avisos


def sugestoes_verificacao() -> List[str]:
    s: List[str] = []
    if Path("package.json").exists():
        try:
            scripts = json.loads(Path("package.json").read_text(encoding="utf-8")).get("scripts", {}) or {}
        except Exception:
            scripts = {}
        gerente = "npm"
        if Path("pnpm-lock.yaml").exists():
            gerente = "pnpm"
        elif Path("yarn.lock").exists():
            gerente = "yarn"
        elif Path("bun.lockb").exists() or Path("bun.lock").exists():
            gerente = "bun"
        achou_tipos = False
        for nome in ("typecheck", "type-check", "check-types", "tsc", "lint", "check", "build", "test"):
            if nome in scripts:
                s.append(f"{gerente} run {nome}")
                achou_tipos = achou_tipos or nome in ("typecheck", "type-check", "check-types", "tsc")
        if Path("tsconfig.json").exists() and not achou_tipos:
            s.append("npx tsc --noEmit -p tsconfig.json")
    if any(Path(x).exists() for x in ("pyproject.toml", "setup.py", "setup.cfg", "pytest.ini", "requirements.txt")):
        s.append("python3 -m compileall -q .   # sintaxe")
        texto = Path("pyproject.toml").read_text(encoding="utf-8", errors="replace") if Path("pyproject.toml").exists() else ""
        if "ruff" in texto or Path("ruff.toml").exists():
            s.append("ruff check .")
        if "mypy" in texto or Path("mypy.ini").exists():
            s.append("mypy .")
        if "pytest" in texto or Path("pytest.ini").exists() or Path("tests").is_dir():
            s.append("python3 -m pytest -q")
    if Path("go.mod").exists():
        s += ["go build ./...", "go vet ./...", "go test ./..."]
    if Path("Cargo.toml").exists():
        s += ["cargo check --all-targets", "cargo test"]
    if Path("composer.json").exists():
        s.append("composer validate --no-check-publish")
        s.append("git diff --name-only --diff-filter=AM HEAD~1 -- '*.php' | xargs -n1 php -l   # sintaxe PHP")
        if Path("vendor/bin/phpunit").exists():
            s.append("vendor/bin/phpunit")
    if Path("Gemfile").exists():
        s.append("bundle exec rspec" if Path("spec").is_dir() else "bundle exec rake test")
    if Path("mix.exs").exists():
        s += ["mix compile --warnings-as-errors", "mix test"]
    if Path("pubspec.yaml").exists():
        s += ["flutter analyze", "flutter test"]
    if Path("Makefile").exists():
        alvos = set(re.findall(r"^([A-Za-z0-9_.-]+):", Path("Makefile").read_text(encoding="utf-8", errors="replace"), re.M))
        for t in ("check", "lint", "typecheck", "test", "build"):
            if t in alvos:
                s.append(f"make {t}")
    return s


def cmd_checar(a):
    mh = merge_em_andamento()
    if not mh:
        print("Nenhum merge em andamento.")
    problemas, avisos = problemas_do_merge()
    for p in problemas:
        print(f"PROBLEMA: {p}")
    for w in avisos:
        print(f"aviso: {w}")
    if mh and not problemas:
        n = len(git("diff", "--cached", "--name-only").splitlines())
        print(f"OK: nada pendente, sem marcadores; {n} arquivo(s) preparados para o commit do merge.")
    sug = sugestoes_verificacao()
    if sug:
        print("\nVerificações do projeto (rode a mais rápida após cada merge; todas no fim):")
        for c in sug:
            print(f"  {c}")
    sys.exit(1 if problemas else 0)


# ---------- mergear / concluir / pular / nota ----------

def mensagem_merge(passo: dict) -> str:
    return f"Merge PR #{passo['numero']}: {passo['titulo']}\n\n{passo['url']}\nAutor: @{passo['autor']}\n"


def cmd_mergear(a):
    plano = carregar_plano()
    n = a.numero
    passo = passo_por_numero(plano, n)
    if not passo:
        falha(f"PR #{n} não está no plano. Rode `plano` de novo (com --pr {n} se ela ficou de fora).")
    if passo["status"] == "mergeada":
        print(f"PR #{n} já foi mergeada ({passo['commit']}).")
        return
    if merge_em_andamento():
        falha("há um merge em andamento. Conclua (`concluir`) ou aborte (`pular N`) antes.")
    branch = branch_atual()
    if branch != plano["branch"]:
        falha(f"o plano foi feito na branch '{plano['branch']}' e você está em '{branch}'.")
    if not arvore_limpa():
        falha("árvore de trabalho com alterações não commitadas. Commite ou guarde (stash) antes.")
    dep = passo.get("depende_de")
    if dep:
        pdep = passo_por_numero(plano, dep)
        if not (pdep and pdep["status"] == "mergeada") and not (pdep and pdep.get("sha") and git_ok("merge-base", "--is-ancestor", pdep["sha"], "HEAD")):
            falha(f"PR #{n} está empilhada sobre #{dep}, que ainda não foi mergeada. Mergeie #{dep} primeiro.")
    anteriores = [s for s in plano["passos"] if s["status"] == "pendente" and s["ordem"] < passo["ordem"]]
    if anteriores:
        aviso("o plano colocava antes de #%d as PRs %s; seguindo mesmo assim." % (n, ", ".join(f"#{s['numero']}" for s in anteriores)))
    if plano.get("fetch", True):
        # busca o head de novo: o autor pode ter empurrado commits (ou um --force) depois do plano
        r = rodar(["git", "fetch", "--quiet", "origin", f"+refs/pull/{n}/head:{passo['ref']}"])
        if r.returncode != 0:
            aviso("não consegui atualizar o head da PR; usando o que foi baixado no plano\n" + r.stderr.strip())
    if not git_ok("rev-parse", "-q", "--verify", passo["ref"]):
        falha(f"a ref {passo['ref']} não existe; rode `plano` de novo.")
    sha_ref = git("rev-parse", passo["ref"])
    if sha_ref != passo["sha"]:
        aviso(f"o head da PR mudou desde o plano ({passo['sha'][:8]} → {sha_ref[:8]}); usando o atual.")
        passo["sha"] = sha_ref
    if git_ok("merge-base", "--is-ancestor", sha_ref, "HEAD"):
        passo["status"] = "mergeada"
        passo["commit"] = git("rev-parse", "HEAD")
        passo["notas"].append("já estava contida na branch")
        salvar_plano(plano)
        print(f"PR #{n} já está contida na branch; nada a fazer.")
        return

    r = rodar(["git", "-c", "merge.conflictStyle=zdiff3", "merge", "--no-ff", "--no-edit",
               "-m", mensagem_merge(passo), passo["ref"]])
    if r.returncode == 0:
        passo["status"] = "mergeada"
        passo["commit"] = git("rev-parse", "HEAD")
        passo["conflitos"] = []
        salvar_plano(plano)
        registrar(f"PR #{n} mergeada sem conflitos → {passo['commit'][:10]}")
        print(f"PR #{n} mergeada sem conflitos → commit {passo['commit'][:10]}")
        print(git("show", "--stat", "--format=", "HEAD").splitlines()[-1] if git("show", "--stat", "--format=", "HEAD") else "")
        proximo = next((s for s in plano["passos"] if s["status"] == "pendente"), None)
        if proximo:
            print(f"Próximo: python3 {script_nome()} mergear {proximo['numero']}")
        return
    if merge_em_andamento():
        passo["status"] = "em-conflito"
        passo["conflitos"] = sorted(entradas_nao_mescladas().keys())
        salvar_plano(plano)
        registrar(f"PR #{n}: conflito em {len(passo['conflitos'])} arquivo(s): {', '.join(passo['conflitos'])}")
        print(f"PR #{n}: merge com conflitos. Resolva arquivo a arquivo e feche com `concluir`.\n")
        imprimir_resumo_conflitos()
        sys.exit(2)
    falha(f"o merge da PR #{n} não iniciou:\n{(r.stderr or r.stdout).strip()}")


def cmd_concluir(a):
    plano = carregar_plano()
    mh = merge_em_andamento()
    if not mh:
        falha("nenhum merge em andamento.")
    passo = next((s for s in plano["passos"] if s["status"] == "em-conflito" and s.get("sha") == mh), None)
    if not passo:
        passo = next((s for s in plano["passos"] if s["status"] == "em-conflito"), None)
    if not passo:
        falha("o merge em andamento não corresponde a nenhuma PR do plano em conflito.")
    notas = list(a.nota or [])
    if a.notas_arquivo:
        notas += [l.strip("- ").strip() for l in Path(a.notas_arquivo).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not notas:
        falha("informe ao menos uma --nota \"arquivo: o que foi mantido de cada lado e por quê\". "
              "A nota vai para a mensagem do commit; é o que permite auditar o merge depois.")
    problemas, avisos = problemas_do_merge()
    for w in avisos:
        print(f"aviso: {w}")
    if problemas:
        for p in problemas:
            print(f"PROBLEMA: {p}")
        falha("resolva os problemas acima (git add nos arquivos resolvidos; remova marcadores) e rode `concluir` de novo.")
    msg = mensagem_merge(passo) + "\nConflitos resolvidos:\n" + "".join(f"- {n}\n" for n in notas)
    arq_msg = pasta_estado() / "msg.txt"
    arq_msg.write_text(msg, encoding="utf-8")
    r = rodar(["git", "commit", "--file", str(arq_msg)])
    if r.returncode != 0:
        falha(f"git commit falhou (hook?):\n{(r.stderr or r.stdout).strip()}")
    passo["status"] = "mergeada"
    passo["commit"] = git("rev-parse", "HEAD")
    passo["notas"] += notas
    salvar_plano(plano)
    registrar(f"PR #{passo['numero']} concluída com {len(passo['conflitos'])} conflito(s) → {passo['commit'][:10]}")
    print(f"PR #{passo['numero']} concluída → commit {passo['commit'][:10]}")
    print("Agora rode a verificação rápida do projeto (ver `checar`) antes da próxima PR.")
    proximo = next((s for s in plano["passos"] if s["status"] == "pendente"), None)
    if proximo:
        print(f"Próximo: python3 {script_nome()} mergear {proximo['numero']}")


def cmd_pular(a):
    plano = carregar_plano()
    passo = passo_por_numero(plano, a.numero)
    if not passo:
        falha(f"PR #{a.numero} não está no plano.")
    mh = merge_em_andamento()
    if mh:
        if passo["status"] != "em-conflito":
            falha("há um merge em andamento de outra PR; conclua ou aborte aquele primeiro.")
        git("merge", "--abort")
        print(f"Merge da PR #{a.numero} abortado; árvore voltou ao estado anterior.")
    passo["status"] = "pulada"
    passo["motivo"] = a.motivo
    salvar_plano(plano)
    registrar(f"PR #{a.numero} pulada: {a.motivo}")
    dependentes = [s for s in plano["passos"] if s.get("depende_de") == a.numero and s["status"] == "pendente"]
    if dependentes:
        aviso("dependem de #%d e trariam o conteúdo dela junto: %s. Pule-as também ou mergeie #%d depois."
              % (a.numero, ", ".join(f"#{s['numero']}" for s in dependentes), a.numero))
    print(f"PR #{a.numero} marcada como pulada ({a.motivo}).")


def cmd_nota(a):
    plano = carregar_plano()
    passo = passo_por_numero(plano, a.numero)
    if not passo:
        falha(f"PR #{a.numero} não está no plano.")
    passo["notas"].append(a.texto)
    salvar_plano(plano)
    registrar(f"PR #{a.numero} nota: {a.texto}")
    print("Nota registrada.")


# ---------- relatório / limpar ----------

def cmd_relatorio(a):
    plano = carregar_plano()
    branch = plano["branch"]
    linhas = [f"# mergedev — {plano['repo']} → `{branch}` ({agora()})", ""]
    novos = git("rev-list", "--count", f"{plano['backup']}..HEAD", check=False) or "?"
    linhas += [f"Backup antes do primeiro merge: `{plano['backup']}` — {novos} commit(s) novos desde então.",
               f"Desfazer tudo: `git reset --hard {plano['backup']}`. Desfazer uma PR: `git revert -m 1 <commit do merge>`.", ""]
    linhas += ["| ord | PR | título | autor | resultado |", "|---|---|---|---|---|"]
    for s in plano["passos"]:
        if s["status"] == "mergeada":
            res = f"mergeada `{(s['commit'] or '')[:10]}`" + (f", {len(s['conflitos'])} arquivo(s) em conflito resolvidos" if s["conflitos"] else ", sem conflitos")
        elif s["status"] == "pulada":
            res = f"pulada — {s.get('motivo', '')}"
        elif s["status"] == "em-conflito":
            res = "EM CONFLITO (merge aberto)"
        else:
            res = "pendente"
        linhas.append(f"| {s['ordem']} | [#{s['numero']}]({s['url']}) | {truncar(s['titulo'], 70)} | @{s['autor']} | {res} |")
    com_notas = [s for s in plano["passos"] if s["notas"] or s["conflitos"]]
    if com_notas:
        linhas += ["", "## Conflitos e ajustes"]
        for s in com_notas:
            linhas.append(f"\n### PR #{s['numero']} — {truncar(s['titulo'], 80)}")
            if s["conflitos"]:
                linhas.append("Arquivos em conflito: " + ", ".join(f"`{c}`" for c in s["conflitos"]))
            for n in s["notas"]:
                linhas.append(f"- {n}")
    if plano["pulados"]:
        linhas += ["", "## Fora do plano"]
        for x in plano["pulados"]:
            linhas.append(f"- #{x['numero']} {truncar(x['titulo'], 70)} — {x['motivo']}")
    mergeadas = [s for s in plano["passos"] if s["status"] == "mergeada"]
    fecham = [s for s in mergeadas if s["base"] == branch]
    nao_fecham = [s for s in mergeadas if s["base"] != branch]
    linhas += ["", "## Próximos passos"]
    sug = sugestoes_verificacao()
    if sug:
        linhas.append("- Verificação completa: " + "; ".join(f"`{c}`" for c in sug))
    linhas.append(f"- Enviar: `git push origin {branch}` (decisão de quem usa; nada foi enviado).")
    if fecham:
        linhas.append("- Ao enviar, o GitHub marca como mergeadas (base = `%s`): %s." % (branch, ", ".join(f"#{s['numero']}" for s in fecham)))
    if nao_fecham:
        linhas.append("- Continuam abertas por terem outra base: %s. O GitHub re-aponta a base sozinho quando a branch-mãe é apagada depois do merge; senão, `gh pr edit N --base %s` faz a PR constar como mergeada."
                      % (", ".join(f"#{s['numero']} (base `{s['base']}`)" for s in nao_fecham), branch))
    linhas.append(f"- Limpar refs temporárias: `python3 {script_nome()} limpar`")
    texto = "\n".join(linhas) + "\n"
    (pasta_estado() / "relatorio.md").write_text(texto, encoding="utf-8")
    print(texto)
    print(f"(salvo em {pasta_estado() / 'relatorio.md'})")


def cmd_limpar(a):
    refs = git("for-each-ref", "--format=%(refname)", "refs/mergedev/pr-*").splitlines()
    for r in refs:
        git("update-ref", "-d", r)
    print(f"{len(refs)} ref(s) refs/mergedev/pr-* removida(s).")
    if a.tudo:
        for r in git("for-each-ref", "--format=%(refname)", "refs/mergedev/backup/").splitlines():
            git("update-ref", "-d", r)
        shutil.rmtree(pasta_estado(), ignore_errors=True)
        print("Backups e estado (plano, log, relatório) removidos.")
    else:
        print("Backups em refs/mergedev/backup/ e o estado em .git/mergedev/ foram mantidos (use --tudo para apagar).")


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(prog="mergedev.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plano", help="lista as PRs abertas, define a ordem e baixa os heads")
    p.add_argument("--base", help="branch alvo das PRs (padrão: a branch atual)")
    p.add_argument("--todas", action="store_true", help="inclui PRs com outra base")
    p.add_argument("--rascunhos", action="store_true", help="inclui PRs em rascunho")
    p.add_argument("--ordem", choices=["cadeia", "numero"], default="cadeia",
                   help="cadeia: cada pai seguido das filhas; numero: por número respeitando dependências")
    p.add_argument("--pr", type=int, nargs="+", help="só estas PRs (ignora filtros de base/rascunho/label)")
    p.add_argument("--sem-fetch", action="store_true", help="não baixa os heads (usa refs já existentes)")
    p.add_argument("--repo", help="DONO/NOME (padrão: o repositório do diretório atual)")
    p.add_argument("--de-json", help=argparse.SUPPRESS)  # testes: lista de PRs no formato do gh
    p.set_defaults(fn=cmd_plano)

    p = sub.add_parser("mergear", help="faz o merge --no-ff da PR N")
    p.add_argument("numero", type=int)
    p.set_defaults(fn=cmd_mergear)

    p = sub.add_parser("conflitos", help="resumo dos arquivos em conflito; com ARQUIVO, detalhe")
    p.add_argument("arquivo", nargs="?")
    p.add_argument("--completo", action="store_true", help="não limita o tamanho dos diffs")
    p.set_defaults(fn=cmd_conflitos)

    p = sub.add_parser("checar", help="confere se o merge pode ser concluído e lista verificações do projeto")
    p.set_defaults(fn=cmd_checar)

    p = sub.add_parser("concluir", help="commita o merge em conflito com as notas de resolução")
    p.add_argument("--nota", action="append", help="'arquivo: o que foi mantido e por quê' (repetível)")
    p.add_argument("--notas-arquivo", help="arquivo com uma nota por linha")
    p.set_defaults(fn=cmd_concluir)

    p = sub.add_parser("pular", help="tira a PR N do plano (aborta o merge dela se estiver aberto)")
    p.add_argument("numero", type=int)
    p.add_argument("--motivo", required=True)
    p.set_defaults(fn=cmd_pular)

    p = sub.add_parser("nota", help="anexa uma observação à PR N (ex.: commit de ajuste)")
    p.add_argument("numero", type=int)
    p.add_argument("texto")
    p.set_defaults(fn=cmd_nota)

    p = sub.add_parser("relatorio", help="relatório final em Markdown")
    p.set_defaults(fn=cmd_relatorio)

    p = sub.add_parser("limpar", help="remove refs temporárias (mantém backup, salvo --tudo)")
    p.add_argument("--tudo", action="store_true")
    p.set_defaults(fn=cmd_limpar)

    a = ap.parse_args()
    if not git_ok("rev-parse", "--is-inside-work-tree"):
        falha("rode dentro de um repositório git.")
    os.chdir(git("rev-parse", "--show-toplevel"))
    a.fn(a)


if __name__ == "__main__":
    main()
