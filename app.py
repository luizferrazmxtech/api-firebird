from flask import Flask, request, jsonify, send_file
import fdb
import os
from fpdf import FPDF
import io

app = Flask(__name__)

# Configuração do Banco
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_DATABASE"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", 3050)),
    "charset": "UTF8"
}

# Token de Autenticação
API_TOKEN = os.getenv("API_TOKEN", "seu_token_aqui")

# Middleware de Autenticação
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

        # Criar PDF com formato A4
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Título
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "Relatório de Consulta Firebird", ln=True, align='C')
        pdf.ln(10)

        # Cabeçalho
        pdf.set_font("Arial", 'B', 10)
        col_width = 277 / len(columns)  # Divide proporcionalmente na página A4 horizontal

        for col in columns:
            pdf.cell(col_width, 10, str(col), border=1, align='C')
        pdf.ln()

        # Dados
        pdf.set_font("Arial", '', 9)
        for row in results:
            for item in row:
                text = str(item) if item is not None else ''
                pdf.cell(col_width, 8, text, border=1, align='C')
            pdf.ln()

        # Gerar PDF em memória
        pdf_bytes = pdf.output(dest='S').encode('latin-1')  # Para fpdf 1.x
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
