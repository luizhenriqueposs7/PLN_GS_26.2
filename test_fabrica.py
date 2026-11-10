import tempfile
import unittest
from pathlib import Path

from fabrica import anonimizar, chave, extrair, limpar, segmentar


class FabricaTest(unittest.TestCase):
    def test_limpeza_preserva_texto(self):
        bruto = 'Pág. 2\n  “Atenção” à inun-\ndação!\nhttps://gov.br\n\n\tPróxima linha.'
        self.assertEqual(limpar(bruto), '"Atenção" à inundação!\n\nPróxima linha.')
        self.assertEqual(chave("  É aqui?? "), chave("e AQUI"))

    def test_texto_docx_e_html(self):
        from docx import Document

        with tempfile.TemporaryDirectory() as temp:
            pasta = Path(temp)
            txt = pasta / "a.txt"
            txt.write_text("Texto com acentuação.", encoding="utf-8")
            self.assertEqual(extrair(txt)[0][2], "Texto com acentuação.")
            html = pasta / "b.html"
            html.write_text("<nav>Menu</nav><main><h2>Alertas</h2><p>Saia cedo.</p></main>", encoding="utf-8")
            self.assertEqual(extrair(html), [("Alertas", None, "Saia cedo.")])
            docx = pasta / "c.docx"
            documento = Document()
            documento.add_heading("Riscos", level=1)
            documento.add_paragraph("A encosta cedeu.")
            tabela = documento.add_table(rows=1, cols=2)
            tabela.rows[0].cells[0].text = "Canal"
            tabela.rows[0].cells[1].text = "Defesa Civil"
            documento.save(docx)
            self.assertEqual(extrair(docx), [("Riscos", None, "A encosta cedeu.\n\nCanal | Defesa Civil")])

    def test_mascara_e_preserva_instituicoes(self):
        import spacy

        ner = spacy.blank("pt")
        regras = ner.add_pipe("entity_ruler")
        regras.add_patterns([{"label": "PER", "pattern": nome} for nome in
                             ("Ana Exemplo", "Maria da Penha", "Defesa Civil", "EMAIL")])
        texto = ("Ana Exemplo citou a Lei Maria da Penha à Defesa Civil. "
                 "CPF 000.000.000-00, ana@example.invalid, +55 (00) 90000-0000. Ligue 193.")
        limpo = anonimizar(texto, ner, ("Lei Maria da Penha", "Defesa Civil"))
        self.assertEqual(limpo, "[NOME] citou a Lei Maria da Penha à Defesa Civil. "
                                "CPF [CPF], [EMAIL], [TELEFONE]. Ligue 193.")
        self.assertEqual(anonimizar("E-mail: teste@example.invalid", ner), "E-mail: [EMAIL]")

    def test_segmentacao_rebalanceia_sem_cortar_frases(self):
        frases = [" ".join([f"parte{i}"] * (100 + i)) + "." for i in range(7)]
        trechos, descartados = segmentar([(i, frase) for i, frase in enumerate(frases, 1)],
                                         lambda s: len(s.split()))
        self.assertEqual(" ".join(texto for texto, _, _ in trechos), " ".join(frases))
        self.assertTrue(all(256 <= len(texto.split()) <= 512 for texto, _, _ in trechos))
        self.assertEqual(trechos[-1][2], 7)
        self.assertEqual(descartados, 0)


if __name__ == "__main__":
    unittest.main()
