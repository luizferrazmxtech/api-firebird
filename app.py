from flask import Flask, request, jsonify, Response
import fdb
import os
from fpdf import FPDF

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

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Relatório de Orçamento', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def generate_pdf(data):
    pdf = PDF('P', 'mm', 'A4')
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    col_widths = [30, 25, 60, 20, 20, 20, 20, 20]
    headers = ["NRORC", "SERIEO", "DESCR", "QUANT", "UNIDA", "VOLUME", "UNIVOL", "PRCOBR"]

    for i, header in enumerate(headers):
        pdf.set_fill_color(200, 220, 255)  # azul claro
        pdf.cell(col_widths[i], 10, header, border=1, fill=True, align='C')
    pdf.ln()

    for row in data:
        pdf.cell(col_widths[0], 8, str(row.get("NRORC", "")), border=1)
        pdf.cell(col_widths[1], 8, str(row.get("SERIEO", "")), border=1)
        pdf.cell(col_widths[2], 8, str(row.get("DESCR", "")), border=1)
        pdf.cell(col_widths[3], 8, str(row.get("QUANT", "")), border=1, align='R')
        pdf.cell(col_widths[4], 8, str(row.get("UNIDA", "")), border=1)
        pdf.cell(col_widths[5], 8, str(row.get("VOLUME", "")), border=1)
        pdf.cell(col_widths[6], 8, str(row.get("UNIVOL", "")), border=1)
        pdf.cell(col_widths[7], 8, f'{row.get("PRCOBR", 0):.2f}', border=1, align='R')
        pdf.ln()

    return pdf.output(dest='S')

@app.route('/pdf', methods=['GET'])
def pdf_report():
    # Espera receber o parâmetro sql GET (mesmo que no /query)
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

        pdf_bytes = generate_pdf(results)
        return Response(pdf_bytes, mimetype='application/pdf', headers={"Content-Disposition": "attachment;filename=relatorio.pdf"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
