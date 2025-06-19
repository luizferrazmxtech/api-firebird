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
        results = cur.fetchall()
        con.close()

        # Organiza os dados por NRORC e SERIEO
        data = {}
        for row in results:
            row_dict = dict(zip(columns, row))
            nr = row_dict.get('NRORC')
            serie = row_dict.get('SERIEO')
            key = f"{nr}-{serie}"

            if key not in data:
                data[key] = {
                    'items': [],
                    'volume': row_dict.get('VOLUME'),
                    'univol': row_dict.get('UNIVOL'),
                    'prcobr': row_dict.get('PRCOBR')
                }

            data[key]['items'].append({
                'descr': row_dict.get('DESCR'),
                'quant': row_dict.get('QUANT'),
                'unida': row_dict.get('UNIDA')
            })

        # Criação do PDF
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "Relatório de Consulta Firebird", ln=True, align='C')
        pdf.ln(5)

        for key, content in data.items():
            pdf.set_font("Arial", 'B', 14)
            pdf.set_fill_color(200, 220, 255)
            pdf.cell(0, 10, f"ORÇAMENTO: {key}", ln=True, fill=True)
            pdf.ln(2)

            # Cabeçalho dos itens
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(10, 8, "Item", 1, 0, 'C')
            pdf.cell(100, 8, "Descrição", 1, 0, 'C')
            pdf.cell(30, 8, "Quant.", 1, 0, 'C')
            pdf.cell(30, 8, "Unidade", 1, 1, 'C')

            # Itens
            pdf.set_font("Arial", '', 12)
            for idx, item in enumerate(content['items'], start=1):
                pdf.cell(10, 8, str(idx), 1, 0, 'C')
                pdf.cell(100, 8, str(item['descr']), 1, 0, 'L')
                pdf.cell(30, 8, str(item['quant']), 1, 0, 'C')
                pdf.cell(30, 8, str(item['unida']), 1, 1, 'C')

            pdf.ln(2)
            # Volume e Total
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, f"Volume: {content['volume']} {content['univol']}", ln=True)
            pdf.cell(0, 8, f"Total: R$ {content['prcobr']}", ln=True)
            pdf.ln(5)

        # Gerar PDF em memória corretamente
        pdf_bytes = pdf.output(dest='S').encode('latin1')
        pdf_output = io.BytesIO(pdf_bytes)

        return send_file(
            pdf_output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='relatorio.pdf'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
