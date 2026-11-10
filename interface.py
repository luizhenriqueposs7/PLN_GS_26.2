"""Interface local para importar, inspecionar e gerar o corpus CitizenTech."""

import json
import re
from datetime import date
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

from flask import Flask, render_template, request, send_file, send_from_directory

from fabrica import EXTENSOES, RAIZ, anonimizar, exigir, extrair, gerar, higienizar, ler_json, modelo_ner

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
MANIFESTO = json.loads(ler_json("fontes.json"))
SAIDA = RAIZ / "corpus"
TOKENIZADOR = RAIZ / "tokenizador/tokenizer.json"
FONTES_OFICIAIS = {f["arquivo"] for f in MANIFESTO["fontes"]}
TEXTO_COLADO = "texto_colado.txt"


def documentos_recebidos(recebidos, texto_colado, pasta):
    documentos = {}
    for i, item in enumerate(recebidos):
        nome = item.filename
        extensao = Path(nome).suffix.lower()
        exigir(extensao in EXTENSOES, "Selecione arquivos PDF, TXT, DOCX ou HTML.")
        exigir(nome not in documentos and not (texto_colado and nome == TEXTO_COLADO),
               "Use nomes distintos para os arquivos e para o texto colado.")
        caminho = pasta / f"{i}{extensao}"
        item.save(caminho)
        documentos[nome] = caminho
    if texto_colado:
        caminho = pasta / TEXTO_COLADO
        caminho.write_text(texto_colado, encoding="utf-8")
        documentos[TEXTO_COLADO] = caminho
    return documentos


def novas_fontes(documentos, texto_metadados):
    exigir(documentos, "Selecione um documento ou cole texto.")
    exigir(texto_metadados.strip(), "Preencha os metadados das fontes novas antes de gerar.")
    try:
        dados = json.loads(texto_metadados)
    except json.JSONDecodeError as erro:
        raise ValueError("Os metadados devem ser uma lista JSON válida.") from erro
    exigir(isinstance(dados, list), "Os metadados devem ser uma lista JSON.")
    fontes = {}
    campos = ("arquivo", "titulo", "orgao", "url", "data")
    for item in dados:
        exigir(isinstance(item, dict) and all(isinstance(item.get(k), str) and item[k].strip()
                                             for k in campos), "Preencha arquivo, titulo, orgao, url e data.")
        meta = {k: item[k].strip() for k in campos}
        nome = meta["arquivo"]
        exigir(nome not in fontes and nome not in FONTES_OFICIAIS,
               "Use nomes distintos dos arquivos oficiais e das demais fontes novas.")
        link = urlsplit(meta["url"])
        exigir(link.scheme in ("https", "http") and link.hostname and not link.username and not link.password,
               "Use um link HTTP ou HTTPS público, sem credenciais.")
        data = meta["data"]
        exigir(re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", data), "Use data AAAA, AAAA-MM ou AAAA-MM-DD.")
        try:
            date.fromisoformat(data + {4: "-01-01", 7: "-01", 10: ""}[len(data)])
        except ValueError as erro:
            raise ValueError("Informe uma data válida para cada fonte.") from erro
        fontes[nome] = meta
    exigir(fontes.keys() == documentos.keys(),
           "Os nomes nos metadados precisam corresponder aos arquivos. Para o texto colado use texto_colado.txt.")
    return [(meta, extrair(documentos[nome], meta)) for nome, meta in fontes.items()]


@app.route("/", methods=["GET", "POST"])
def painel():
    previas, qualidade, erro = [], None, None
    if request.method == "POST":
        try:
            with TemporaryDirectory() as temporario:
                pasta = Path(temporario)
                recebidos = [item for item in request.files.getlist("documentos") if item.filename]
                texto_colado = request.form.get("texto", "").strip()
                metadados = request.form.get("metadados", "").strip()
                if len(recebidos) > 8:
                    raise ValueError("Selecione no máximo oito documentos.")
                if len(texto_colado) > 150_000:
                    raise ValueError("Cole até 150 mil caracteres por vez.")
                if request.form["acao"] == "gerar":
                    copia_oficial = ({item.filename for item in recebidos} == FONTES_OFICIAIS
                                      and len(recebidos) == len(FONTES_OFICIAIS))
                    if not metadados and not texto_colado and (not recebidos or copia_oficial):
                        for item in recebidos:
                            item.save(pasta / item.filename)
                        qualidade = gerar(SAIDA, TOKENIZADOR, pasta if recebidos else None)
                    else:
                        documentos = documentos_recebidos(recebidos, texto_colado, pasta)
                        saida = pasta / "saida"
                        gerar(saida, TOKENIZADOR, novas_fontes=novas_fontes(documentos, metadados))
                        buffer = BytesIO()
                        with ZipFile(buffer, "w", ZIP_DEFLATED) as zip_corpus:
                            for arquivo in sorted(saida.iterdir()):
                                zip_corpus.write(arquivo, arquivo.name)
                        buffer.seek(0)
                        return send_file(buffer, mimetype="application/zip", as_attachment=True,
                                         download_name="corpus_com_fontes_novas.zip")
                else:
                    documentos = documentos_recebidos(recebidos, texto_colado, pasta)
                    exigir(documentos, "Selecione um documento ou cole texto.")
                    ner, excecoes = ner_local(), MANIFESTO["excecoes"]
                    for nome, caminho in documentos.items():
                        limpos = higienizar(extrair(caminho), ner, excecoes)
                        amostra = "\n\n".join(f"{s}{f' · página {p}' if p else ''}\n{t}"
                                              for s, p, t in limpos if t)
                        previas.append((anonimizar(nome, ner, excecoes), amostra[:4500] or "Sem texto extraível."))
        except Exception as falha:
            erro = str(falha) if type(falha) is ValueError else "Não foi possível processar a entrada."
            if type(falha) is not ValueError:
                app.logger.exception("Falha no processamento local")
    return render_template("painel.html", fontes=MANIFESTO["fontes"], previas=previas,
                           qualidade=qualidade, erro=erro), 400 if erro else 200


@lru_cache(maxsize=1)
def ner_local():
    return modelo_ner()


@app.get("/corpus/<nome>")
def baixar(nome):
    return send_from_directory(SAIDA, nome, as_attachment=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8767, threaded=False)
