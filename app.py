from flask import Flask, request, jsonify, send_file
import fdb
import os
from fpdf import FPDF
import io

app = Flask(__name__)

# 🔗 Configuração do banco
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_DATABASE"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", 3050)),
    "charset": "UTF8"
}

API_TOKEN = os.getenv("API_TOKEN", "seu_token_aqui")

# 🔒 Validação de token
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

        if not results:
            return jsonify({"error": "Nenhum dado encontrado"}), 404

        # 📄 Criar PDF no formato A4
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "Relatório de Consulta Firebird", ln=True, align='C')
        pdf.ln(5)

        # 📏 Definir larguras proporcionais
        num_columns = len(columns)
        page_width = 210 - 20  # A4 width - margins (10+10)
        col_width = page_width / num_columns

        # 🔠 Cabeçalho
        pdf.set_font("Arial", 'B', 10)
        for col in columns:
            pdf.cell(col_width, 8, str(col), border=1, align='C')
        pdf.ln()

        # 📊 Dados
        pdf.set_font("Arial", '', 9)
        for row in results:
            for item in row:
                text = str(item) if item is not None else ''
                if isinstance(item, float):
                    text = f"{item:.2f}"

                if len(text) > 25:  # Se for muito grande, reduz a fonte
                    pdf.set_font("Arial", '', 8)
                else:
                    pdf.set_font("Arial", '', 9)

                pdf.cell(col_width, 8, text, border=1, align='C')
            pdf.ln()

        # 📥 PDF em memória
        pdf_output = io.BytesIO()
        pdf_output_bytes = pdf.output(dest='S').encode('latin-1')
        pdf_output.write(pdf_output_bytes)
        pdf_output.seek(0)

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
