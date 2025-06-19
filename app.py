from flask import Flask, request, jsonify, send_file
import fdb
import os
from fpdf import FPDF
import io

app = Flask(__name__)

# Configuração do banco Firebird via variáveis de ambiente
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_DATABASE"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", 3050)),
    "charset": "WIN1252"
}

# Token de segurança para autenticação
API_TOKEN = os.getenv("API_TOKEN", "seu_token_aqui")

class PDF(FPDF):
    def header(self):
        # Logo
        if os.path.exists('logo.png'):
            try:
                self.image('logo.png', x=10, y=2, w=50, type='PNG')
            except:
                pass
        # Título Orçamento no topo direito
        self.set_font('Arial', '', 12)
        self.set_xy(140, 10)
        self.cell(60, 10, f"ORÇAMENTO: {self.order_number}-{self.total_formulations}", align='R')
        # Paciente abaixo do orçamento
        if hasattr(self, 'patient_name') and self.patient_name:
            self.set_xy(140, 17)
            self.cell(60, 8, f"PACIENTE: {self.patient_name}", align='R')
        self.ln(25)

    def footer(self):
        # Rodapé com número do orçamento e página
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        page = f"Orçamento: {self.order_number} - Página {self.page_no()}/{self.alias_nb_pages()}"
        self.cell(0, 10, page, align='C')

# ...

        pdf = PDF(format='A4')
        pdf.alias_nb_pages()
        pdf.order_number = primeiro_nrorc
        pdf.total_formulations = total_formulations
+        # Atribui nome do paciente se existir
+        pdf.patient_name = first_patient if 'first_patient' in locals() else ''
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()(format='A4')
        pdf.alias_nb_pages()
        pdf.order_number = primeiro_nrorc
        pdf.total_formulations = total_formulations
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        # Larguras das colunas de itens
        desc_w, qty_w, unit_w = 110, 30, 30
        row_h = 6

        # --- Cada Formulação ---
        for idx, ((nro, serie), info) in enumerate(grouped.items(), start=1):
            # Título da formulação com fundo verde claro e texto cinza escuro
            pdf.set_fill_color(200, 230, 200)
            pdf.set_text_color(60, 60, 60)
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 8, f"Formulação {idx:02}", ln=True, align='L', fill=True)

            # Itens lado a lado
            pdf.set_text_color(60, 60, 60)
            pdf.set_font('Arial', '', 11)
            for item in info['items']:
                if not item['descr'].strip():
                    continue
                pdf.cell(desc_w, row_h, item['descr'], border=0)
                pdf.cell(qty_w, row_h, str(item['quant']), border=0, align='C')
                pdf.cell(unit_w, row_h, item['unida'], border=0, ln=1, align='C')

            # Volume e total da formulação
            pdf.ln(1)
            pdf.set_font('Arial', 'B', 11)
            current_y = pdf.get_y()
            pdf.set_xy(10, current_y)
            pdf.cell(70, 8, f"Volume: {info['volume']} {info['univol']}", border=0)
            pdf.set_xy(140, current_y)
            pdf.cell(60, 8, f"Total: R$ {info['prcobr']:.2f}", border=0, ln=1, align='R')
            pdf.ln(4)

        # --- Total Geral no final ---
        pdf.set_fill_color(180, 240, 180)
        pdf.set_text_color(60, 60, 60)
        pdf.set_font('Arial', 'B', 13)
        pdf.cell(0, 10, f"TOTAL GERAL DO ORÇAMENTO: R$ {total_geral:.2f}", ln=True, align='R', fill=True)

        # Gera e envia PDF
        out = pdf.output(dest='S')
        if isinstance(out, str):
            out = out.encode('latin-1')
        buffer = io.BytesIO(out)
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name='orcamento.pdf')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
