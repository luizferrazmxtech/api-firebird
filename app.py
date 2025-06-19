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

@app.route('/')
def home():
    return "🚀 API Firebird está online!"

@app.route('/pdf', methods=['GET'])
def generate_pdf():
    sql = request.args.get('sql')
    if not sql or not sql.strip().lower().startswith("select"):
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

        # Agrupar por (NRORC, SERIEO)
        grouped = {}
        for row in rows:
            record = dict(zip(columns, row))
            key = (record['NRORC'], record['SERIEO'])
            if key not in grouped:
                grouped[key] = {
                    'items': [],
                    'volume': record.get('VOLUME'),
                    'univol': record.get('UNIVOL'),
                    'prcobr': float(record.get('PRCOBR') or 0)
                }
            grouped[key]['items'].append({
                'descr': record.get('DESCR'),
                'quant': record.get('QUANT'),
                'unida': record.get('UNIDA')
            })

        total_geral = sum(g['prcobr'] for g in grouped.values())

        # Criar PDF
        pdf = FPDF(format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Espaço para logo
        if os.path.exists("logo.png"):
            pdf.image("logo.png", x=10, y=8, w=50)
        pdf.ln(40)

        # Cabeçalho superior direito com nº de orçamento
        first_nrorc = list(grouped.keys())[0][0]
        pdf.set_font("Arial", '', 12)
        pdf.set_xy(160, 10)
        pdf.cell(40, 10, f"ORÇAMENTO: {first_nrorc}-{len(grouped)}", align='R')
        pdf.ln(10)

        # Gerar seções de formulação
        for idx, ((nrorc, serieo), info) in enumerate(grouped.items(), 1):
            # Título da Formulação com fundo verde claro e texto à esquerda
            pdf.set_fill_color(100, 180, 120)  # verde claro
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 9, f"Formulação {idx:02}", ln=True, align='L', fill=True)

            pdf.set_text_color(60, 60, 60)
            pdf.set_font("Arial", '', 11)
            pdf.ln(2)

            # Itens alinhados à esquerda, sem fundo
            for item in info['items']:
                descr = item['descr'] or ''
                quant = item['quant'] or ''
                unida = item['unida'] or ''
                line = f"{descr:<60} {quant} {unida}"
                pdf.cell(0, 8, line, ln=True, align='L')

            pdf.ln(2)
            pdf.set_font("Arial", 'B', 12)
            left = f"Volume: {info['volume']} {info['univol']}"
            right = f"Total: R$ {info['prcobr']:.2f}"
            pdf.cell(95, 8, left, border=0, ln=0)
            pdf.cell(95, 8, right, border=0, ln=1, align='R')
            pdf.ln(5)

        # Total Geral centra
