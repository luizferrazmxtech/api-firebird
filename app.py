from flask import Flask, request, jsonify, send_file
import fdb
import os
from fpdf import FPDF
import io

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

@app.route('/pdf', methods=['GET'])
def generate_pdf():
    sql = request.args.get('sql')
    if not sql:
        return jsonify({"error": "SQL query is required"}), 400
    if not sql.strip().lower().startswith("select"):
        return jsonify({"error": "Only SELECT queries are allowed"}), 400

    try:
        con = fdb.connect(
            host=DB_CONFIG["host"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            port=DB_CONFIG["port"],
            charset=DB_CONFIG["charset"]
        )
        cur = con.cursor()
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description]
        results = cur.fetchall()
        con.close()

        # Criar PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, "Relatório de Consulta Firebird", ln=True, align='C')
        pdf.ln(10)

        pdf.set_font("Arial", 'B', 12)
        # Cabeçalho da tabela
        for col in columns:
            pdf.cell(30, 10, str(col), 1, 0, 'C')
        pdf.ln()

        pdf.set_font("Arial", '', 12)
        # Dados da tabela
        for row in results:
            for item in row:
                text = str(item)
                if isinstance(item, float):
                    text = f"{item:.2f}"
                pdf.cell(30, 10, text, 1, 0, 'C')
            pdf.ln()

        # Salvar PDF em memória
        pdf_output = io.BytesIO()
        pdf.output(pdf_output)
        pdf_output.seek(0)

        return send_file(pdf_output,
                         mimetype='application/pdf',
                         as_attachment=True,
                         download_name='relatorio.pdf')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
