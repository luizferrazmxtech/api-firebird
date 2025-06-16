from flask import Flask, request, jsonify, make_response
import fdb
import os
from fpdf import FPDF

app = Flask(__name__)

# Configurações do banco Firebird
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_DATABASE"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", 3050)),
    "charset": "UTF8"
}

API_TOKEN = os.getenv("API_TOKEN", "seu_token_aqui")

# Middleware de autenticação
@app.before_request
def check_auth():
    token = request.headers.get('Authorization')
    if token != f"Bearer {API_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

# Endpoint principal
@app.route('/', methods=['GET'])
def home():
    return "🚀 API Firebird está online!"

# Endpoint para consultas SQL
@app.route('/query', methods=['GET'])
def run_query():
    sql = request.args.get('sql')
    if not sql:
        return jsonify({"error": "SQL query is required"}), 400

    if not sql.strip().lower().startswith("select"):
        return jsonify({"error": "Only SELECT queries are allowed"}), 400

    try:
        con = fdb.connect(**DB_CONFIG)
        cur = con.cursor()
        cur.execute(sql)

        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in cur.fetchall()]

        con.close()
        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Endpoint para gerar PDF a partir de uma query
@app.route('/pdf', methods=['GET'])
def generate_pdf():
    sql = request.args.get('sql')
    if not sql:
        return jsonify({"error": "SQL query is required"}), 400

    if not sql.strip().lower().startswith("select"):
        return jsonify({"error": "Only SELECT queries are allowed"}), 400

    try:
        con = fdb.connect(**DB_CONFIG)
        cur = con.cursor()
        cur.execute(sql)

        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in cur.fetchall()]
        con.close()

        if not results:
            return jsonify({"error": "No data found"}), 404

        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Cabeçalho
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "Relatório de Dados", ln=True, align='C')
        pdf.ln(5)

        # Cabeçalho da tabela
        pdf.set_font("Arial", 'B', 10)
        for col in columns:
            pdf.cell(190/len(columns), 8, str(col), border=1, align='C')
        pdf.ln()

        # Dados da tabela
        pdf.set_font("Arial", '', 9)
        for row in results:
            for col in columns:
                texto = str(row[col]) if row[col] is not None else ""
                pdf.cell(190/len(columns), 8, texto, border=1, align='C')
            pdf.ln()

        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        response = make_response(pdf_bytes)
        response.headers.set('Content-Disposition', 'attachment', filename='relatorio.pdf')
        response.headers.set('Content-Type', 'application/pdf')
        return response


    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
