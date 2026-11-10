# Fábrica de Corpus CitizenTech

**FIAP · Global Solution · 2º semestre de 2026**

- Luiz Henrique Poss
- Luis Filipe Chaves Amorim
- Felipe Stefani Honorato

A ferramenta organiza documentos públicos para um futuro atendente sobre enchentes e deslizamentos. Os exemplos ensinam como orientar, pedir contexto, recusar e encaminhar. Os trechos datados guardam os fatos para consulta. O projeto entrega os dados, sem treinamento de modelo.

## Vídeo da demonstração

[Assistir à execução no YouTube](https://youtu.be/rtItMzbgg9Q) · 1min23s. A gravação mostra a execução original. As médias da versão revisada estão em `corpus/qualidade.json`.

## Executar

Use Python 3.11 a 3.13. Abra o terminal nesta pasta e instale as dependências. A primeira instalação baixa cerca de 600 MB, principalmente o reconhecedor de nomes em português. A geração usa os documentos e o tokenizador incluídos e roda offline, sem chave de API.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python fabrica.py gerar
.\.venv\Scripts\python -m unittest -v
```

No Linux ou macOS, substitua `.\.venv\Scripts\python` por `.venv/bin/python`.

Para abrir a interface, execute `python interface.py` com o Python do ambiente e acesse [127.0.0.1:8767](http://127.0.0.1:8767). Selecione `entradas/ficha_ficticia.txt` e clique em **Inspecionar e anonimizar** para conferir os quatro marcadores. Para gerar a edição oficial, deixe a seleção vazia ou envie as cinco cópias com os nomes originais. O SHA-256 valida as cópias. O upload é temporário e a interface escuta apenas no computador local.

### Gerar com documentos novos ou texto colado

1. Envie PDFs com texto, TXT em UTF-8, DOCX ou HTML, cole texto de uma fonte pública ou combine as duas entradas.
2. Abra **Metadados para gerar com fontes novas** e preencha uma entrada por fonte. Use o nome exato do arquivo e `texto_colado.txt` para o texto colado. Informe a URL oficial e a data de publicação ou vigência.
3. Clique em **Gerar os quatro corpus**. O navegador baixa um ZIP separado com os quatro JSONL e `qualidade.json`. Cada fonte nova precisa render pelo menos um trecho de 256 a 512 tokens e entra no corpus de texto para consulta. Os pares e os diálogos continuam ligados à curadoria oficial desta edição.

```json
[
  {
    "arquivo": "texto_colado.txt",
    "titulo": "Orientação de prevenção",
    "orgao": "Defesa Civil",
    "url": "https://example.invalid/orientacao",
    "data": "2026-01"
  }
]
```

Substitua o endereço ilustrativo pelo link oficial da fonte.

Os mesmos passos estão disponíveis no terminal. Com o ambiente ativado, use `python fabrica.py inspecionar entradas/ficha_ficticia.txt` ou envie texto pela entrada padrão com `python fabrica.py inspecionar --colar`. Para uma execução em outra pasta, use `python fabrica.py gerar --saida nova_saida`. A interface e o terminal geram o mesmo conjunto.

## Arquivos

| Caminho | Conteúdo |
| --- | --- |
| `fabrica.py`, `interface.py` | Pipeline e interface local de importação e exportação. |
| `entradas/` | Cinco fontes oficiais e a ficha de atendimento fictícia. |
| `dados/fontes.json` | Títulos, órgãos, datas, URLs, SHA-256 e seções por página física do PDF. |
| `dados/qa.json`, `dados/chat.json` | Perguntas, diálogos, respostas, âncoras editoriais e referências por turno. |
| `dados/teste.json`, `dados/teste.sha256` | Teste fixado antes da geração do treino e verificado pelo pipeline. |
| `dados/teste_evidencias.json` | Complementos de fonte associados ao teste congelado. |
| [`dados/prompt_editorial.md`](dados/prompt_editorial.md) | Modelo e instrução integral usada na correção dos exemplos. |
| `tokenizador/` | Tokenizador oficial do Qwen2.5-0.5B-Instruct e licença Apache 2.0. |
| `corpus/corpus_texto.jsonl` | Trechos de 256 a 512 tokens, com origem, página, seção e data. |
| `corpus/corpus_qa.jsonl` | Pares no formato Alpaca, com contexto no campo `input` e cópia da evidência em `trecho`. |
| `corpus/corpus_chat.jsonl` | Mensagens com instrução de sistema, duas trocas e evidências quando aplicáveis. |
| `corpus/corpus_teste.jsonl` | Perguntas de avaliação com resposta esperada e tipo. Mantenha separado do treino. |
| `corpus/qualidade.json` | Contagens, médias, duplicatas, exemplos sorteados e ficha antes e depois. |
| `revisao.csv` | Amostra para conferência humana, com linhas dos JSONL e observações da conferência assistida. |
| `Relatorio_Fabrica_CitizenTech.pdf`, `Demonstracao_Fabrica_CitizenTech_Final.mp4` | Relatório e gravação contínua da execução com narração. |

PyMuPDF lê PDFs, python-docx lê documentos Word, Beautiful Soup extrai conteúdo HTML, spaCy identifica nomes e Tokenizers conta tokens com o vocabulário do [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct). O Flask fornece a interface.

## Como os dados foram montados

O pipeline filtra capas, créditos e referências, normaliza o texto em UTF-8/NFC e mascara CPF, e-mail, telefone e nomes no conteúdo e nos títulos. O rótulo de telefone ajuda a distinguir números compactos de CPFs. Frases que continuam na página seguinte permanecem juntas, com as duas páginas registradas. O manifesto lista as exceções para instituições, leis e termos conferidos. A ficha tem CPF e DDD inválidos e domínio `.invalid`. Os dados da ficha ficam na demonstração e na evidência de qualidade.

As perguntas e respostas foram preparadas com assistência do Codex, usando os documentos selecionados. Na execução, o Python localiza o trecho literal, aplica as regras e exporta os registros. Se uma âncora não estiver presente no documento limpo, a geração falha antes de substituir os arquivos. As perguntas informais preservam grafia, abreviações e caixa. As respostas seguem português padrão.

Para montar uma nova curadoria de perguntas, conversas e teste, atualize o manifesto e escreva os exemplos com âncoras das fontes. Prepare o novo teste antes do treino e registre seu hash. A edição revisada preserva as perguntas e os gabaritos congelados. O caso 15 recebeu uma fonte oficial complementar.

A equipe deve revisar pelo menos 33 das 39 linhas reservadas em `revisao.csv`, incluindo 20 pares de perguntas e respostas para a conferência de fidelidade. Após ler a resposta e o trecho, registre **sim** ou **não** na coluna `alterado` e descreva a decisão em `comentário`. As notas da conferência assistida estão identificadas e a revisão do grupo está pendente. Confira a privacidade de novas fontes antes da publicação. Preserve os trechos datados e consulte os canais oficiais atuais para abrigos, vias e alertas.
