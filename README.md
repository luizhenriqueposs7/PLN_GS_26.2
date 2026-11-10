# Fábrica de Corpus CitizenTech

**FIAP · Global Solution · 2º semestre de 2026**

- Luiz Henrique Poss
- Luis Filipe Chaves Amorim
- Felipe Stefani Honorato

A ferramenta organiza documentos públicos para um futuro atendente sobre enchentes e deslizamentos. Os exemplos ensinam como orientar, pedir contexto, recusar e encaminhar. Os trechos datados guardam os fatos para consulta. O projeto entrega os dados, sem treinamento de modelo.

## Vídeo da demonstração

[Assistir à execução no YouTube](https://youtu.be/rtItMzbgg9Q) · 1min23s.

## Executar

Use Python 3.11 a 3.13. Abra o terminal nesta pasta e instale as dependências. A primeira instalação baixa cerca de 600 MB, principalmente o reconhecedor de nomes em português. A geração usa os documentos e o tokenizador incluídos e roda offline, sem chave de API.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python fabrica.py gerar
.\.venv\Scripts\python -m unittest -v
```

No Linux ou macOS, substitua `.\.venv\Scripts\python` por `.venv/bin/python`.

Para abrir a interface, execute `python interface.py` com o Python do ambiente e acesse [127.0.0.1:8767](http://127.0.0.1:8767). Selecione `entradas/ficha_ficticia.txt` e clique em **Inspecionar e anonimizar** para conferir os quatro marcadores. Para gerar, deixe a seleção vazia para usar as cópias incluídas ou envie as cinco fontes oficiais com seus nomes originais. O SHA-256 valida a versão recebida. PDF com texto, TXT em UTF-8, DOCX, HTML e texto colado passam pela inspeção. O upload é temporário e a interface escuta apenas no computador local.

Os mesmos passos estão disponíveis no terminal. Com o ambiente ativado, use `python fabrica.py inspecionar entradas/ficha_ficticia.txt` ou envie texto pela entrada padrão com `python fabrica.py inspecionar --colar`. Para uma execução em outra pasta, use `python fabrica.py gerar --saida nova_saida`. A interface e o terminal geram o mesmo conjunto.

## Arquivos

| Caminho | Conteúdo |
| --- | --- |
| `fabrica.py`, `interface.py` | Pipeline e interface local de importação e exportação. |
| `entradas/` | Cinco fontes oficiais e a ficha de atendimento fictícia. |
| `dados/fontes.json` | Títulos, órgãos, datas, URLs, SHA-256 e seções por página física do PDF. |
| `dados/qa.json`, `dados/chat.json` | Perguntas, diálogos, respostas e âncoras editoriais. |
| `dados/teste.json`, `dados/teste.sha256` | Teste fixado antes da geração do treino e verificado pelo pipeline. |
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

O pipeline filtra capas, créditos e referências, normaliza o texto em UTF-8/NFC e mascara CPF, e-mail, telefone e nomes antes da segmentação. Nomes institucionais, títulos legais e falsos positivos conferidos nas fontes têm exceções explícitas no manifesto. A ficha tem CPF e DDD inválidos e domínio `.invalid`. Os dados da ficha ficam apenas na demonstração e na evidência de qualidade.

As perguntas e respostas foram preparadas com assistência do Codex, usando os documentos selecionados. Na execução, o Python localiza o trecho literal, aplica as regras e exporta os registros. Se uma âncora não estiver presente no documento limpo, a geração falha antes de substituir os arquivos. As perguntas informais preservam grafia, abreviações e caixa. As respostas seguem português padrão.

Para trocar o recorte ou usar novas fontes na geração, atualize o manifesto, prepare o novo teste antes do treino, registre seu hash e escreva as perguntas e diálogos com âncoras das novas fontes. A inspeção aceita arquivos avulsos e texto colado, mas só as fontes aprovadas no manifesto entram no pacote.

Aplique revisão humana à amostra de `revisao.csv` antes da entrega acadêmica. Confira a fidelidade, a linguagem e os encaminhamentos. A coluna `alterado` está em branco para a equipe registrar **sim** ou **não** após a leitura. A proteção automática reduz o risco, mas requer revisão da origem ao incorporar documentos. Preserve os trechos datados e consulte os canais oficiais atuais para abrigos, vias e alertas.
