#!/usr/bin/env python3
"""Transcreve áudios e vídeos na própria máquina (ffmpeg + whisper.cpp).

Uso:
  python3 transcrever.py ARQUIVO [ARQUIVO ...] [--salvar] [--saida PASTA] [--idioma pt]
                         [--termos "nomes, siglas, produtos"] [--modelo CAMINHO]
                         [--baixar-modelo] [--sem-contexto]

Imprime a transcrição com o tempo de cada trecho. Com --salvar (ou quando o texto é longo
demais para o terminal) grava transcricao.txt, transcricao.srt e transcricao-blocos.txt
numa nova pasta ao lado do arquivo. A mídia é processada localmente; --baixar-modelo
usa a rede apenas para obter o modelo.
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MODELO_PADRAO = "ggml-large-v3-turbo-q5_0.bin"
URL_MODELO = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/" + MODELO_PADRAO
PASTAS_MODELO = [
    Path.home() / ".cache/whisper-models",
    Path.home() / ".cache/whisper-cpp",
    Path("/opt/homebrew/share/whisper-cpp"),
    Path("/usr/local/share/whisper-cpp"),
]
LIMITE_TERMINAL = 12000  # caracteres; acima disso a transcrição vai para arquivo
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def falha(msg):
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(1)


def roda(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def achar_whisper():
    for nome in ("whisper-cli", "whisper-cpp"):  # o brew renomeou whisper-cpp -> whisper-cli
        if shutil.which(nome):
            return nome
    falha("whisper.cpp não encontrado. Instale com: brew install whisper-cpp")


def achar_modelo(caminho, baixar):
    if caminho:
        p = Path(caminho).expanduser()
        return p if p.is_file() else falha(f"modelo não existe: {p}")
    achados = [m for pasta in PASTAS_MODELO if pasta.is_dir() for m in pasta.glob("ggml-*.bin")
               if "silero" not in m.name.lower() and "encoder" not in m.name.lower()]
    for preferido in (MODELO_PADRAO, "ggml-large-v3-turbo.bin"):
        for m in achados:
            if m.name == preferido:
                return m
    if achados:
        return max(achados, key=lambda m: m.stat().st_size)
    destino = PASTAS_MODELO[0] / MODELO_PADRAO
    if not baixar:
        falha(
            "nenhum modelo do whisper encontrado. Rode de novo com --baixar-modelo "
            f"(574 MB, uma vez só) ou baixe à mão:\n  curl -L --create-dirs -o '{destino}' {URL_MODELO}"
        )
    destino.parent.mkdir(parents=True, exist_ok=True)
    print(f"Baixando o modelo para {destino} (574 MB)...", file=sys.stderr, flush=True)
    parcial = destino.with_suffix(".parcial")
    if subprocess.run(["curl", "-L", "--fail", "-o", str(parcial), URL_MODELO]).returncode:
        falha("download do modelo falhou")
    parcial.rename(destino)
    return destino


def sonda(arquivo):
    """Duração e tipo (áudio ou vídeo) da mídia. Capa de álbum não conta como vídeo."""
    r = roda(["ffprobe", "-v", "error", "-show_entries",
              "format=duration:stream=codec_type:stream_disposition=attached_pic",
              "-of", "json", str(arquivo)])
    if r.returncode:
        falha(f"ffprobe não leu {arquivo.name}: {r.stderr.strip()}")
    d = json.loads(r.stdout)
    fluxos = d.get("streams", [])
    if not any(s.get("codec_type") == "audio" for s in fluxos):
        falha(f"{arquivo.name} não tem trilha de áudio")
    video = any(s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
                for s in fluxos)
    return float(d["format"].get("duration") or 0), "vídeo" if video else "áudio"


def data_no_nome(nome):
    """Data indicada no nome do arquivo; não confirma quando a fala foi gravada."""
    hora = ""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ _-]at[ _-](\d{2})\.(\d{2})\.\d{2}", nome)
    if m:
        hora = f" {m.group(4)}:{m.group(5)}"
    else:
        m = re.search(r"(?:PTT|AUD|VID)-(\d{4})(\d{2})(\d{2})-WA", nome) or re.search(r"(\d{4})-(\d{2})-(\d{2})", nome)
    try:
        dia = datetime.date(*(int(g) for g in m.groups()[:3]))
    except (AttributeError, ValueError):  # sem data no nome, ou dígitos que não formam uma data
        return None
    return f"{DIAS[dia.weekday()]}, {dia.isoformat()}{hora}"


def whisper(binario, wav, base, modelo, idioma, termos, sem_contexto):
    cmd = [binario, "-m", str(modelo), "-l", idioma, "-f", str(wav), "-oj", "-of", str(base), "-np"]
    if termos:
        cmd += ["--prompt", termos]
    if sem_contexto:
        cmd += ["-mc", "0"]
    r = roda(cmd)
    saida = Path(f"{base}.json")
    if r.returncode or not saida.is_file():
        falha(f"whisper falhou em {wav.name}:\n{r.stderr.strip()[-800:]}")
    bruto = json.loads(saida.read_text(encoding="utf-8", errors="replace"))
    segs = []
    for s in bruto.get("transcription", []):
        texto = s.get("text", "").strip()
        if texto and "BLANK_AUDIO" not in texto:
            segs.append({"ini": s["offsets"]["from"] / 1000, "fim": s["offsets"]["to"] / 1000, "texto": texto})
    return segs


def relogio(t):
    t = int(t)
    h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def tempo_srt(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def repeticao(segs):
    """Início do primeiro trecho com 4+ segmentos idênticos seguidos (laço do whisper), ou None."""
    seguidos = 1
    for i in range(1, len(segs)):
        seguidos = seguidos + 1 if segs[i]["texto"] == segs[i - 1]["texto"] else 1
        if seguidos >= 4:
            return segs[i - 3]["ini"]
    return None


def escolhe_pasta(saida, primeiro):
    if saida:
        pasta = saida.expanduser().resolve()
        if pasta.exists() and not pasta.is_dir():
            falha(f"a saída não é uma pasta: {pasta}")
        if any(pasta.glob("transcricao*")):
            falha(f"a pasta já contém transcrições: {pasta}. Escolha outra --saida.")
        return pasta
    base = primeiro.parent / f"{primeiro.stem} — transcrição"
    pasta, numero = base, 2
    while pasta.exists():
        pasta = base.with_name(f"{base.name} ({numero})")
        numero += 1
    return pasta


def grava(pasta, midias):
    pasta.mkdir(parents=True, exist_ok=True)
    varias = len(midias) > 1
    corrido, com_tempo = [], []
    for i, m in enumerate(midias, 1):
        if varias:
            corrido.append(f"== {i}. {m['arquivo']} ==")
            com_tempo.append(f"== {i}. {m['arquivo']} ==\n")
        corrido.append(" ".join(s["texto"] for s in m["segmentos"]) + "\n")
        com_tempo += [f"[{relogio(s['ini'])}] {s['texto']}\n" for s in m["segmentos"]]
        srt = "".join(f"{n}\n{tempo_srt(s['ini'])} --> {tempo_srt(s['fim'])}\n{s['texto']}\n\n"
                      for n, s in enumerate(m["segmentos"], 1))
        with (pasta / (f"transcricao-{i}.srt" if varias else "transcricao.srt")).open("x", encoding="utf-8") as f:
            f.write(srt)
    for nome, linhas in (("transcricao.txt", corrido), ("transcricao-blocos.txt", com_tempo)):
        with (pasta / nome).open("x", encoding="utf-8") as f:
            f.write("\n".join(linhas))


def main():
    ap = argparse.ArgumentParser(description="Transcreve áudios e vídeos localmente.")
    ap.add_argument("arquivos", nargs="+", type=Path)
    ap.add_argument("--salvar", action="store_true", help="grava os arquivos de transcrição numa pasta")
    ap.add_argument("--saida", type=Path, help="pasta de saída, sem sobrescrever transcrições (implica --salvar)")
    ap.add_argument("--idioma", default="pt", help="pt, en, es... ou auto")
    ap.add_argument("--termos", help="nomes próprios, siglas e produtos para o whisper grafar certo")
    ap.add_argument("--modelo", help="caminho de um ggml-*.bin")
    ap.add_argument("--baixar-modelo", action="store_true", help="baixa o modelo padrão se faltar")
    ap.add_argument("--sem-contexto", action="store_true", help="corta laços de repetição (-mc 0)")
    a = ap.parse_args()

    for nome in ("ffmpeg", "ffprobe"):
        if not shutil.which(nome):
            falha(f"{nome} não encontrado. Instale com: brew install ffmpeg")
    binario = achar_whisper()
    arquivos = [f.expanduser().resolve() for f in a.arquivos]
    for f in arquivos:
        if not f.is_file():
            falha(f"arquivo não existe: {f}")
    pasta = escolhe_pasta(a.saida, arquivos[0]) if a.salvar or a.saida else None
    modelo = achar_modelo(a.modelo, a.baixar_modelo)

    midias = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, f in enumerate(arquivos, 1):
            duracao, tipo = sonda(f)
            print(f"Transcrevendo {f.name} ({tipo}, {relogio(duracao)})...", file=sys.stderr, flush=True)
            wav = Path(tmp) / f"{i}.wav"
            r = roda(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(f),
                      "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
            if r.returncode:
                falha(f"ffmpeg não converteu {f.name}: {r.stderr.strip()}")
            segs = whisper(binario, wav, Path(tmp) / str(i), modelo, a.idioma, a.termos, a.sem_contexto)
            midias.append({
                "arquivo": f.name, "tipo": tipo, "duracao": duracao, "data_no_nome": data_no_nome(f.name),
                "segmentos": segs,
            })

    tamanho = sum(len(s["texto"]) for m in midias for s in m["segmentos"])
    longo = tamanho > LIMITE_TERMINAL
    if pasta or longo:
        pasta = pasta or escolhe_pasta(None, arquivos[0])
        grava(pasta, midias)
        print(f"Pasta: {pasta}")
    print(f"Modelo: {modelo.name}, idioma {a.idioma}")

    for i, m in enumerate(midias, 1):
        quando = f", data no nome: {m['data_no_nome']}" if m["data_no_nome"] else ""
        print(f"\n== {i}. {m['arquivo']} ({m['tipo']}, {relogio(m['duracao'])}{quando}) ==")
        if not m["segmentos"]:
            print("(nenhuma fala reconhecida)")
        elif not longo:
            for s in m["segmentos"]:
                print(f"[{relogio(s['ini'])}] {s['texto']}")
        laco = repeticao(m["segmentos"])
        if laco is not None:
            print(f"AVISO: o texto se repete a partir de [{relogio(laco)}]. Rode de novo com --sem-contexto.")
    if longo:
        print(f"\nTranscrição longa ({tamanho} caracteres): leia {pasta / 'transcricao-blocos.txt'}")


if __name__ == "__main__":
    main()
