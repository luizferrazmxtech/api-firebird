from flask import Flask, request, jsonify, send_file
import fdb
import os
from fpdf import FPDF
import io
from collections import defaultdict

app = Flask(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_DATABASE"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", 3050)),
    "charset": "UTF8"
}

API_TOKEN = os.getenv("API_TOKEN", "seu_token_aqui")


@app.before_request
def check_auth():
    token = request.headers.get('Authorization')
    if token != f"Bearer {API_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401


@app.route('/', methods=['GET'])
def home():
    return "🚀 API Firebird está online!"


@app.route('/pdf', methods=['GET'])
def generate_pdf():
    sql = request.args.get('sql')
    if not sql:
        return jsonify({"error": "SQL query is required"}), 400
    if not sql.strip().lower().startswith("select"):
        return jsonify({"error": "Only SELECT queries are allowed"}), 400

    try:
        # Conecta ao Firebird
        dsn = f"{DB_CONFIG['host']}/{DB_CONFIG['port']}:{DB_CONFIG['database']}"
        con = fdb.connect(
            dsn=dsn,
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            charset=DB_CONFIG["charset"]
        )
        cur = con.cursor()
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        con.close()

        # Organiza dados por NRORC e SERIEO
        data = defaultdict(list)
        for row in rows:
            row_dict = dict(zip(columns, row))
            key = (row_dict['NRORC'], row_dict['SERIEO'])
            data[key].append(row_dict)

        # Cria o PDF
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "Relatório de Consulta Firebird", ln=True, align='C')
        pdf.ln(5)

        for (nrorc, serieo), items in data.items():
            # Cabeçalho do orçamento
            pdf.set_font("Arial", 'B', 14)
            pdf.set_fill_color(200, 220, 255)
            pdf.cell(0, 10, f"ORÇAMENTO: {nrorc}-{serieo}", ln=True, fill=True)
            pdf.ln(2)

            # Tabela dos itens
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(10, 8, "Item", 1, 0, 'C')
            pdf.cell(80, 8, "Descrição", 1, 0, 'C')
            pdf.cell(30, 8, "Quant.", 1, 0, 'C')
            pdf.cell(20, 8, "Unid.", 1, 1, 'C')

            pdf.set_font("Arial", '', 12)

            for idx, item in enumerate(items, 1):
                descr = item.get('DESCR', '')
                quant = item.get('QUANT', '')
                unida = item.get('UNIDA', '').strip()

                pdf.cell(10, 8, str(idx), 1, 0, 'C')
                pdf.cell(80, 8, descr, 1, 0, 'L')
                pdf.cell(30, 8, str(quant), 1, 0, 'C')
                pdf.cell(20, 8, unida, 1, 1, 'C')

            pdf.ln(1)

            # Dados de volume e preço (pegamos do primeiro item, já que são iguais para a mesma SERIEO)
            vol = items[0].get('VOLUME', '')
            univol = items[0].get('UNIVOL', '')
            prcobr = items[0].get('PRCOBR', '')

            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, f"VOLUME: {vol} {univol}", ln=True)
            pdf.cell(0, 8, f"TOTAL: {prcobr}", ln=True)
            pdf.ln(8)

        # Salvar PDF na memória
        pdf_output = io.BytesIO()
        pdf_bytes = pdf.output(dest='S').encode('latin1')
        pdf_output.write(pdf_bytes)
        pdf_output.seek(0)

        return send_file(pdf_output,
                         mimetype='application/pdf',
                         as_attachment=True,
                         download_name='relatorio.pdf')

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
