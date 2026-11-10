"""Ingere fontes públicas e exporta os quatro conjuntos da Fábrica CitizenTech."""

import argparse
import hashlib
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "dados"
MODELO = "Qwen/Qwen2.5-0.5B-Instruct"
SISTEMA = (
    "Você orienta moradores sobre enchentes e deslizamentos no Brasil. "
    "Escreva em português simples, use o histórico e dê uma ação de cada vez. "
    "Use os documentos consultados para fatos e indique a fonte. "
    "Se faltarem dados atuais, encaminhe ao órgão responsável. "
    "Em risco imediato, indique o canal de emergência de acordo com o caso. "
    "Não solicite dados pessoais, não diagnostique e não dê laudos. "
    "Recuse com educação pedidos fora do tema."
)
EXTENSOES = (".pdf", ".txt", ".docx", ".html", ".htm")
ASPAS = str.maketrans("“”‘’«»", "\"\"''\"\"")
PII = {
    "CPF": re.compile(r"(?<!\d)\d{3}\s*\.?\s*\d{3}\s*\.?\s*\d{3}\s*-?\s*\d{2}(?!\d)"),
    "EMAIL": re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.I),
    "TELEFONE": re.compile(
        r"(?<![\w\d])(?:\+?55[ .-]?)?(?:\(\d{2}\)|\d{2})[ .-]?"
        r"\d{4,5}[ .-]?\d{4}(?!\d)|(?<![\w\d])\d{4,5}[- ]\d{4}(?!\d)"
    ),
}
NOME_ROTULADO = re.compile(
    r"(?im)^(?:nome(?: completo)?|atendente|solicitante|responsável)\s*:\s*([^\n;]+)"
)
MARCADORES = re.compile(r"\[(?:CPF|EMAIL|TELEFONE|NOME)\]")


def ler_json(nome):
    return (DADOS / nome).read_bytes()


def exigir(condicao, mensagem):
    if not condicao:
        raise ValueError(mensagem)


def chave(texto):
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto.casefold())
                         if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", sem_acento))


def limpar(bruto, ignorar=()):
    texto = unicodedata.normalize("NFC", bruto).translate(ASPAS)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"\u00ad[ \t]*\n[ \t]*", "", texto).replace("\u00ad", "")
    texto = "".join(c for c in texto if c in "\n\t" or unicodedata.category(c)[0] != "C")
    texto = re.sub(r"(?m)^y[ \t]+(?=\S)", "", texto)  # Marcador da fonte gráfica da cartilha do MS.
    texto = re.sub(r"(?<=[^\W\d_])-\s*\n\s*(?=[a-zà-ÿ])", "", texto)
    linhas = []
    for linha in texto.splitlines():
        linha = re.sub(r"[^\S\n]+", " ", linha).strip()
        linha = linha.lstrip("•▪●◦ ").rstrip()
        if (linha in ignorar or re.fullmatch(r"(?:p[áa]g(?:ina)?\.?\s*)?\d+(?:\s*/\s*\d+)?", linha, re.I)
                or re.fullmatch(r"(?:https?://|www\.)\S+", linha, re.I)
                or (linha and linha in linhas)):
            continue
        linhas.append(linha)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()


def agrupar(blocos):
    secoes = []
    secao, partes = "Documento", []
    for titulo, texto in blocos:
        if titulo:
            if partes:
                secoes.append((secao, None, "\n\n".join(partes)))
            secao, partes = titulo, []
        elif texto.strip():
            partes.append(texto)
    if partes:
        secoes.append((secao, None, "\n\n".join(partes)))
    return secoes


def extrair(caminho, metadados=None):
    metadados = metadados or {}
    extensao = caminho.suffix.lower()
    if extensao == ".pdf":
        import pymupdf

        with pymupdf.open(caminho) as pdf:
            secoes = metadados.get("secoes", [[1, len(pdf), "Documento"]])
            return [(titulo, n, pdf[n - 1].get_text())
                    for inicio, fim, titulo in secoes for n in range(inicio, fim + 1)]
    if extensao in {".html", ".htm"}:
        from bs4 import BeautifulSoup

        html = BeautifulSoup(caminho.read_bytes(), "html.parser", from_encoding="utf-8")
        corpo = html.select_one("#content-core") or html.select_one("article, main") or html.body or html
        for tag in corpo.select("script, style, nav, footer, header, aside, noscript, form"):
            tag.decompose()
        blocos = [(tag.get_text(" ", strip=True), "") if tag.name.startswith("h")
                  else ("", tag.get_text(" ", strip=True))
                  for tag in corpo.find_all(["h1", "h2", "h3", "h4", "p", "li"])
                  if not tag.find_parent("li")]
        secoes = agrupar(blocos) or [("Documento", None, corpo.get_text("\n", strip=True))]
        return [(metadados.get("titulo", s) if s == "Documento" else s, p, t) for s, p, t in secoes]
    if extensao == ".docx":
        from docx import Document
        from docx.text.paragraph import Paragraph

        blocos = []
        for bloco in Document(caminho).iter_inner_content():
            if isinstance(bloco, Paragraph):
                titulo = bloco.style and bloco.style.name.startswith(("Heading", "Título"))
                blocos.append((bloco.text, "") if titulo else ("", bloco.text))
            else:
                blocos.extend(("", " | ".join(c.text for c in linha.cells)) for linha in bloco.rows)
        return agrupar(blocos)
    if extensao == ".txt":
        return [("Documento", None, caminho.read_text(encoding="utf-8-sig"))]
    raise ValueError("Formato inválido. Use PDF, TXT, DOCX ou HTML.")


def anonimizar(texto, ner, excecoes=()):
    texto = PII["EMAIL"].sub("[EMAIL]", texto)
    texto = PII["CPF"].sub("[CPF]", texto)
    texto = PII["TELEFONE"].sub("[TELEFONE]", texto)
    protegidos = []
    for termo in excecoes:
        expressao = r"\s+".join(map(re.escape, termo.split()))
        protegidos.extend((m.start(), m.end())
                          for m in re.finditer(rf"(?<!\w){expressao}(?!\w)", texto, re.I))
    nomes = [(m.start(1), m.end(1)) for m in NOME_ROTULADO.finditer(texto)]
    entrada_ner = MARCADORES.sub(lambda m: " " * len(m[0]), texto)
    nomes.extend((ent.start_char, ent.end_char) for ent in ner(entrada_ner).ents if ent.label_ == "PER")
    fim_mascara = len(texto) + 1
    for inicio, fim in sorted(set(nomes), reverse=True):
        if any(a <= inicio and fim <= b for a, b in protegidos):
            continue
        if inicio < fim_mascara:
            texto = texto[:inicio] + "[NOME]" + texto[min(fim, fim_mascara):]
            fim_mascara = inicio
    return re.sub(r"(?:\[NOME\]\s*){2,}", "[NOME] ", texto)


def higienizar(blocos, ner, excecoes, ruídos=()):
    bordas = Counter(l.strip() for _, p, t in blocos if p is not None
                     for l in set(t.strip().splitlines()[:2] + t.strip().splitlines()[-2:]))
    ignorar = set(ruídos) | {l for l, freq in bordas.items() if freq >= 3}
    return [(s, p, anonimizar(limpar(t, ignorar), ner, excecoes)) for s, p, t in blocos]


def segmentar(paginas, contar):
    unidades = []
    for pagina, texto in paginas:
        for bloco in re.split(r"\n\s*\n", texto):
            plano = " ".join(bloco.split())
            for frase in re.split(r'(?<=[.!?;:])\s+(?=[A-ZÀ-Ü0-9“"(\[])', plano):
                if frase:
                    unidades.append((pagina, frase))
    trechos, buffer, tokens, descartados = [], [], 0, 0
    for pagina, frase in unidades:
        tamanho = contar(frase)
        if tamanho > 512:
            descartados += 1
            continue
        candidato = " ".join(t for _, t in buffer + [(pagina, frase)])
        if buffer and (contar(candidato) > 512 or tokens >= 265):
            if tokens >= 256:
                trechos.append(buffer)
                buffer = []
            else:
                descartados += len(buffer)
                buffer = []
        buffer.append((pagina, frase))
        tokens = contar(" ".join(t for _, t in buffer))
    if buffer and tokens < 256 and trechos:
        anterior = trechos[-1]
        conjunto = anterior + buffer
        for corte in range(len(anterior), 0, -1):
            esquerdo = contar(" ".join(t for _, t in conjunto[:corte]))
            direito = contar(" ".join(t for _, t in conjunto[corte:]))
            if 256 <= esquerdo <= 512 and 256 <= direito <= 512:
                trechos[-1], buffer, tokens = conjunto[:corte], conjunto[corte:], direito
                break
        else:
            unido = contar(" ".join(t for _, t in conjunto))
            if unido <= 512:
                trechos.pop()
                buffer, tokens = conjunto, unido
            else:
                for unidade in reversed(anterior):
                    buffer.insert(0, unidade)
                    tokens = contar(" ".join(t for _, t in buffer))
                    if tokens >= 256:
                        break
    if 256 <= tokens <= 512:
        trechos.append(buffer)
    else:
        descartados += len(buffer)
    return [(" ".join(t for _, t in grupo), grupo[0][0], grupo[-1][0]) for grupo in trechos], descartados


def modelo_ner():
    import spacy

    return spacy.load("pt_core_news_lg", exclude=["tagger", "morphologizer", "parser",
                                                 "lemmatizer", "attribute_ruler", "senter"])


def tokenizador(arquivo=None):
    from tokenizers import Tokenizer

    if arquivo:
        return Tokenizer.from_file(str(arquivo))
    return Tokenizer.from_pretrained(MODELO)


def unicos(registros, identificar):
    saida, vistos = [], set()
    for registro in registros:
        marca = identificar(registro)
        if marca not in vistos:
            saida.append(registro)
            vistos.add(marca)
    return saida, len(registros) - len(saida)


def escrever_jsonl(caminho, registros):
    with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
        for registro in registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def jsonl_em_memoria(registros):
    return "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in registros)


def gerar(destino, tokenizer_path=None, fontes_dir=None):
    ner, tok = modelo_ner(), tokenizador(tokenizer_path)

    def contar(texto):
        return len(tok.encode(texto, add_special_tokens=False).ids)

    manifesto = json.loads(ler_json("fontes.json"))
    fontes_dir = fontes_dir or RAIZ / "entradas"
    excecoes = manifesto["excecoes"]
    paginas = {}
    corpus_texto, descartes = [], {}
    for meta in manifesto["fontes"]:
        fonte = meta["arquivo"]
        caminho = fontes_dir / fonte
        exigir(hashlib.sha256(caminho.read_bytes()).hexdigest() == meta["sha256"],
               f"Arquivo de origem diferente da versão conferida: {fonte}")
        blocos_brutos = extrair(caminho, meta)
        for padrao in meta.get("remover", []):
            blocos_brutos = [(s, p, re.sub(padrao, "", t)) for s, p, t in blocos_brutos]
        blocos = higienizar(blocos_brutos, ner, excecoes + meta.get("preservar", []),
                            meta.get("ignorar", []))
        paginas[fonte] = blocos
        trechos, descartes[fonte] = segmentar([(p, t) for _, p, t in blocos if t], contar)
        for texto, inicio, fim in trechos:
            rotulos = list(dict.fromkeys(s for s, p, _ in blocos
                                        if p is None or inicio <= p <= fim))
            corpus_texto.append({"text": texto, "fonte": fonte, "secao": " / ".join(rotulos),
                                 "paginas": [inicio, fim] if inicio is not None else None,
                                 "data": meta["data"], "titulo": meta["titulo"],
                                 "orgao": meta["orgao"], "url": meta["url"], "tokens": contar(texto)})

    ficha = RAIZ / "entradas" / "ficha_ficticia.txt"
    antes = ficha.read_text(encoding="utf-8").strip()
    depois = anonimizar(limpar(antes), ner, excecoes)
    exigir(all(f"[{campo}]" in depois for campo in (*PII, "NOME")),
           "O documento fictício não demonstrou todos os quatro marcadores.")

    def apoio(fonte, pagina, ancora):
        candidatos = [(s, p, " ".join(t.split())) for s, p, t in paginas[fonte]
                      if p == pagina and ancora in " ".join(t.split())]
        exigir(len(candidatos) == 1, f"Âncora ausente ou ambígua em {fonte} p. {pagina}: {ancora}")
        secao, pagina, texto = candidatos[0]
        return {"fonte": fonte, "secao": secao, "pagina": pagina,
                "trecho": texto[texto.index(ancora):texto.index(ancora) + len(ancora)]}

    teste_bruto = ler_json("teste.json")
    exigir(hashlib.sha256(teste_bruto).hexdigest() == ler_json("teste.sha256").decode().strip(),
           "O conjunto de teste congelado foi alterado.")
    teste = []
    for pergunta, resposta, tipo, alias, pagina, trecho, informal in json.loads(teste_bruto):
        item = {"pergunta": pergunta, "resposta_esperada": resposta, "tipo": tipo,
                "fonte": None, "lingua_real": informal}
        if alias:
            item.update(apoio(manifesto["aliases"][alias], pagina, trecho))
        teste.append(item)

    qa = []
    for alias, pagina, trecho, resposta, perguntas in json.loads(ler_json("qa.json")):
        evid = apoio(manifesto["aliases"][alias], pagina, trecho)
        for pergunta, informal in perguntas:
            qa.append({"instruction": pergunta, "input": trecho, "output": resposta,
                       **evid, "lingua_real": informal})

    chat = []
    for tipo, perguntas, respostas, evidencias in json.loads(ler_json("chat.json")):
        citacoes = [apoio(manifesto["aliases"][alias], pagina, trecho)
                    for alias, pagina, trecho in evidencias]
        origens = list(dict.fromkeys(c["fonte"] for c in citacoes))
        sistema = SISTEMA
        if citacoes:
            sistema += "\n\nDocumentos consultados:\n" + "\n".join(
                f'{c["fonte"]} ({c["secao"]}): {c["trecho"]}' for c in citacoes)
        mensagens = [{"role": "system", "content": sistema}]
        for (pergunta, _), resposta in zip(perguntas, respostas, strict=True):
            mensagens.extend([{"role": "user", "content": pergunta},
                              {"role": "assistant", "content": resposta}])
        chat.append({"messages": mensagens, "fonte": origens[0] if len(origens) == 1 else origens or None,
                     "tipo": tipo, "evidencias": citacoes, "lingua_real": [q[1] for q in perguntas]})

    arquivos = {
        "corpus_texto.jsonl": unicos(corpus_texto, lambda r: r["text"]),
        "corpus_qa.jsonl": unicos(qa, lambda r: chave(r["instruction"])),
        "corpus_chat.jsonl": unicos(chat, lambda r: tuple(chave(m["content"]) for m in r["messages"]
                                                         if m["role"] == "user")),
        "corpus_teste.jsonl": unicos(teste, lambda r: chave(r["pergunta"])),
    }
    treinos = {chave(r["instruction"]) for r in arquivos["corpus_qa.jsonl"][0]}
    treinos.update(chave(m["content"]) for r in arquivos["corpus_chat.jsonl"][0]
                   for m in r["messages"] if m["role"] == "user")
    chaves_teste = {chave(r["pergunta"]) for r in teste}
    exigir(not treinos & chaves_teste, "Há uma pergunta de teste nos corpus de treino.")
    exigir(len(teste) == len(chaves_teste), "O teste congelado contém perguntas duplicadas.")
    exigir(len({r["fonte"] for r in qa}) >= 3, "QA exige pelo menos três fontes.")
    tipos_teste = Counter(r["tipo"] for r in teste)
    exigir(tipos_teste["fora_do_tema"] >= 3 and tipos_teste["urgencia"] >= 2
           and tipos_teste["direta"] and tipos_teste["pegadinha"], "Distribuição do teste inválida.")
    exigir(all(len(r["messages"]) >= 5 for r in chat), "Cada diálogo precisa de pelo menos duas trocas.")
    exigir(all(256 <= r["tokens"] <= 512 for r in corpus_texto), "Trecho fora do intervalo de tokens.")
    texto_treino = "\n".join(chave(r["text"]) for r in corpus_texto)
    exigir(not any(q in texto_treino for q in chaves_teste), "Há uma pergunta de teste no texto puro.")

    stats = {}
    rng = random.Random(2026)
    for (nome, (linhas, duplicatas)), minimo in zip(arquivos.items(), (50, 100, 30, 20), strict=True):
        exigir(len(linhas) >= minimo, f"{nome}: {len(linhas)} exemplos; mínimo {minimo}.")
        payload = jsonl_em_memoria(linhas)
        exigir(not any(p.search(payload) for p in PII.values()), f"Possível dado pessoal em {nome}.")
        informais = []
        for linha in linhas:
            valor = linha.get("lingua_real", [])
            informais.extend(valor if isinstance(valor, list) else [valor])
        if informais:
            exigir(sum(informais) / len(informais) >= 0.30, f"Língua real abaixo de 30% em {nome}.")
        if nome.startswith("corpus_chat"):
            exigir(sum(r["tipo"] != "orientacao" for r in linhas) >= 10, "Faltam casos de limites.")
        textos = []
        for r in linhas:
            if "text" in r:
                textos.append(r["text"])
            elif "messages" in r:
                textos.append("\n".join(m["content"] for m in r["messages"]))
            elif "instruction" in r:
                textos.append("\n".join(r[c] for c in ("instruction", "input", "output")))
            else:
                textos.append(r["pergunta"] + "\n" + r["resposta_esperada"])
        stats[nome] = {
            "exemplos": len(linhas), "media_tokens": round(sum(map(contar, textos)) / len(linhas), 1),
            "duplicatas_removidas": duplicatas,
            "tipos": dict(Counter(r.get("tipo", "orientacao") for r in linhas)),
            "perguntas_informais": sum(informais), "perguntas": len(informais),
            "amostras": [{"linha": n + 1, "exemplo": linhas[n]}
                         for n in sorted(rng.sample(range(len(linhas)), 5))],
        }

    destino.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destino) as pasta:
        temporario = Path(pasta)
        for nome, (linhas, _) in arquivos.items():
            escrever_jsonl(temporario / nome, linhas)
        qualidade = {"tokenizador": MODELO, "teste_sha256": hashlib.sha256(teste_bruto).hexdigest(),
                     "sobreposicao_treino_teste": 0, "unidades_sem_trecho": descartes,
                     "ficha_ficticia": {"antes": antes, "depois": depois}, "corpus": stats}
        (temporario / "qualidade.json").write_text(
            json.dumps(qualidade, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for arquivo in temporario.iterdir():
            arquivo.replace(destino / arquivo.name)
    return qualidade


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    build = sub.add_parser("gerar", help="Gera os quatro JSONL com as fontes oficiais fornecidas.")
    build.add_argument("--saida", type=Path, default=RAIZ / "corpus")
    build.add_argument("--tokenizer", type=Path, default=RAIZ / "tokenizador" / "tokenizer.json",
                       help="Arquivo tokenizer.json oficial, para uso offline.")
    build.add_argument("--fontes", type=Path, help="Pasta com cópias verificadas dos documentos.")
    inspect = sub.add_parser("inspecionar", help="Importa, extrai, limpa e mascara arquivos ou texto colado.")
    inspect.add_argument("arquivos", nargs="*", type=Path)
    inspect.add_argument("--colar", action="store_true", help="Lê texto da entrada padrão.")
    args = parser.parse_args()
    if args.comando == "gerar":
        qualidade = gerar(args.saida, args.tokenizer, args.fontes)
        for nome, info in qualidade["corpus"].items():
            print(f'{nome}  {info["exemplos"]} exemplos  |  {info["media_tokens"]} tokens em média')
        print("Perguntas em comum entre treino e teste: 0")
        print(f"Corpus e qualidade: {args.saida.resolve()}")
    else:
        exigir(args.arquivos or args.colar, "Informe um arquivo ou use --colar.")
        ner = modelo_ner()
        excecoes = json.loads(ler_json("fontes.json"))["excecoes"]
        documentos = [(arq.name, extrair(arq)) for arq in args.arquivos]
        if args.colar:
            documentos.append(("Texto colado", [("Documento", None, sys.stdin.read())]))
        for fonte, blocos in documentos:
            for secao, pagina, texto in higienizar(blocos, ner, excecoes):
                print(f"\n[{fonte} | {secao} | página {pagina or '—'}]\n{texto}")


if __name__ == "__main__":
    main()
