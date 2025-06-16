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

@app.route('/pdf', methods=['GET'])
def gerar_pdf():
    sql = request.args.get('sql')

    if not sql:
        return jsonify({'error': 'Parâmetro SQL não fornecido'}), 400

    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        results = cursor.fetchall()

        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        pdf.cell(200, 10, txt="Relatório Firebird", ln=True, align='C')
        pdf.ln(10)

        # Cabeçalho
        for col in columns:
            pdf.cell(40, 10, txt=str(col), border=1)
        pdf.ln()

        # Dados
        for row in results:
            for item in row:
                pdf.cell(40, 10, txt=str(item), border=1)
            pdf.ln()

        pdf_bytes = pdf.output(dest='S')

        response = make_response(pdf_bytes)
        response.headers.set('Content-Disposition', 'attachment', filename='relatorio.pdf')
        response.headers.set('Content-Type', 'application/pdf')
        return response

    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
