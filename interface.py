"""Interface local para importar, inspecionar e gerar o corpus CitizenTech."""

import json
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Flask, render_template, request, send_from_directory

from fabrica import EXTENSOES, RAIZ, extrair, gerar, higienizar, ler_json, modelo_ner

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
MANIFESTO = json.loads(ler_json("fontes.json"))
SAIDA = RAIZ / "corpus"


@app.route("/", methods=["GET", "POST"])
def painel():
    previas, qualidade, erro = [], None, None
    if request.method == "POST":
        try:
            with TemporaryDirectory() as temporario:
                pasta = Path(temporario)
                recebidos = [item for item in request.files.getlist("documentos") if item.filename]
                texto_colado = request.form.get("texto", "").strip()
                if len(recebidos) > 8:
                    raise ValueError("Selecione no máximo oito documentos.")
                if len(texto_colado) > 150_000:
                    raise ValueError("Cole até 150 mil caracteres por vez.")
                if request.form["acao"] == "gerar":
                    if recebidos or texto_colado:
                        esperados = {f["arquivo"] for f in MANIFESTO["fontes"]}
                        nomes = {item.filename for item in recebidos}
                        if texto_colado or nomes != esperados or len(recebidos) != len(esperados):
                            raise ValueError("Para gerar o pacote desta edição, envie todas as fontes oficiais "
                                             "com os nomes originais ou deixe a seleção vazia.")
                        for item in recebidos:
                            item.save(pasta / item.filename)
                    qualidade = gerar(SAIDA, RAIZ / "tokenizador/tokenizer.json",
                                      pasta if recebidos else None)
                else:
                    documentos = []
                    for i, item in enumerate(recebidos):
                        extensao = Path(item.filename).suffix.lower()
                        if extensao not in EXTENSOES:
                            raise ValueError("Selecione arquivos PDF, TXT, DOCX ou HTML.")
                        caminho = pasta / f"{i}{extensao}"
                        item.save(caminho)
                        documentos.append((item.filename, extrair(caminho)))
                    if texto_colado:
                        documentos.append(("Texto colado", [("Documento", None, texto_colado)]))
                    if not documentos:
                        raise ValueError("Selecione um documento ou cole texto.")
                    for nome, blocos in documentos:
                        limpos = higienizar(blocos, ner_local(), MANIFESTO["excecoes"])
                        amostra = "\n\n".join(f"{s}{f' · página {p}' if p else ''}\n{t}"
                                              for s, p, t in limpos if t)
                        previas.append((nome, amostra[:4500] or "Sem texto extraível."))
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
