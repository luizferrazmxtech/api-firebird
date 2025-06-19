from flask import Flask, request, jsonify, send_file
import fdb
import os
from fpdf import FPDF
import io

app = Flask(__name__)

# Configurações do banco
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_DATABASE"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", 3050)),
    "charset": "UTF8"
}

API_TOKEN = os.getenv("API_TOKEN", "seu_token_aqui")


# Autenticação simples por token
@app.before_request
def check_auth():
    token = request.headers.get('Authorization')
    if token != f"Bearer {API_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401


@app.route('/', methods=['GET'])
def home():
    return "🚀 API Firebird está online!"


# Endpoint de consulta normal
@app.route('/query', methods=['GET'])
def run_query():
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
        results = [dict(zip(columns, row)) for row in cur.fetchall()]

        con.close()
        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Endpoint para gerar PDF formatado
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
        rows = cur.fetchall()
        con.close()

        if not rows:
            return jsonify({"error": "No data found"}), 404

        # Organiza os dados por NRORC e SERIEO
        data_group = {}
        for row in rows:
            row_dict = dict(zip(columns, row))
            nrorc = row_dict.get('NRORC')
            serieo = row_dict.get('SERIEO')
            key = (nrorc, serieo)
            if key not in data_group:
                data_group[key] = {
                    "items": [],
                    "volume": row_dict.get('VOLUME'),
                    "univol": row_dict.get('UNIVOL'),
                    "prcobr": row_dict.get('PRCOBR')
                }
            data_group[key]['items'].append({
                "descr": row_dict.get('DESCR'),
                "quant": row_dict.get('QUANT'),
                "unida": row_dict.get('UNIDA')
            })

        # Criar PDF
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "Relatório de Orçamento", ln=True, align='C')
        pdf.ln(5)

        for (nrorc, serieo), details in data_group.items():
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 8, f"ORÇAMENTO: {nrorc}-{serieo}", ln=True)

            pdf.set_font("Arial", 'B', 12)
            pdf.cell(10, 8, "Item", 1, 0, 'C')
            pdf.cell(80, 8, "Descrição", 1, 0, 'C')
            pdf.cell(30, 8, "Quantidade", 1, 0, 'C')
            pdf.cell(30, 8, "Unidade", 1, 1, 'C')

            pdf.set_font("Arial", '', 12)
            for idx, item in enumerate(details['items'], start=1):
                pdf.cell(10, 8, str(idx), 1, 0, 'C')
                pdf.cell(80, 8, str(item['descr']), 1, 0, 'L')
                pdf.cell(30, 8, f"{item['quant']}", 1, 0, 'C')
                pdf.cell(30, 8, str(item['unida']), 1, 1, 'C')

            pdf.set_font("Arial", 'B', 12)
            pdf.ln(2)
            pdf.cell(0, 8, f"VOLUME: {details['volume']} {details['univol']}", ln=True)
            pdf.cell(0, 8, f"TOTAL: R$ {details['prcobr']:.2f}", ln=True)
            pdf.ln(10)

        # Gerar PDF na memória
        pdf_bytes = pdf.output(dest='S')
        if isinstance(pdf_bytes, str):
            pdf_bytes = pdf_bytes.encode('latin-1')
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
