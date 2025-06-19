from flask import Flask, request, jsonify, send_file
import fdb
import os
from fpdf import FPDF
import io

app = Flask(__name__)

# Configurações do banco Firebird via variáveis de ambiente
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_DATABASE"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", 3050)),
    "charset": "UTF8"
}

# Token de segurança
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
    # Parâmetro SQL
    sql = request.args.get('sql')
    if not sql or not sql.strip().lower().startswith("select"):
        return jsonify({"error": "Only SELECT queries are allowed"}), 400

    try:
        # Conexão Firebird
        dsn = f"{DB_CONFIG['host']}/{DB_CONFIG['port']}:{DB_CONFIG['database']}"
        con = fdb.connect(
            dsn=dsn,
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            charset=DB_CONFIG["charset"]
        )
        cur = con.cursor()
        cur.execute(sql)
        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        con.close()

        if not rows:
            return jsonify({"error": "No data found"}), 404

        # Agrupar por orçamento e formulação
        data = {}
        for r in rows:
            rec = dict(zip(cols, r))
            key = (rec['NRORC'], rec['SERIEO'])
            if key not in data:
                data[key] = {
                    'items': [],
                    'volume': rec.get('VOLUME'),
                    'univol': rec.get('UNIVOL'),
                    'prcobr': float(rec.get('PRCOBR') or 0)
                }
            data[key]['items'].append({
                'descr': rec.get('DESCR'),
                'quant': rec.get('QUANT'),
                'unida': rec.get('UNIDA')
            })

        # Calcula total geral
        total_geral = sum(v['prcobr'] for v in data.values())

        # Iniciar PDF
        pdf = FPDF(format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Espaço para logo
        if os.path.exists('logo.png'):
            pdf.image('logo.png', x=10, y=8, w=60)
        pdf.ln(45)

        # Cabeçalho Orçamento
        primeiro_nrorc = list(data.keys())[0][0]
        pdf.set_font('Arial', '', 12)
        pdf.set_xy(140, 10)
        pdf.cell(50, 10, f"ORÇAMENTO: {primeiro_nrorc}-{len(data)}", align='R')
        pdf.ln(10)

        # Conteúdo por formulação
        for idx, ((nro, ser), info) in enumerate(data.items(), start=1):
            # Título Formulação
            pdf.set_fill_color(100, 180, 120)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 9, f"Formulação {idx:02}", ln=True, align='L', fill=True)

            # Itens
            pdf.set_text_color(60, 60, 60)
            pdf.set_font('Arial', '', 11)
            pdf.ln(2)
            for item in info['items']:
                desc = item['descr'] or ''
                qt = item['quant'] or ''
                un = item['unida'] or ''
                line = f"{desc:<60} {str(qt)} {un}"
                pdf.cell(0, 8, line, ln=True, align='L')
            pdf.ln(2)

            # Volume e total da formulação
            pdf.set_font('Arial', 'B', 11)
            left = f"Volume: {info['volume']} {info['univol']}"
            right = f"Total: R$ {info['prcobr']:.2f}"
            pdf.cell(95, 8, left, border=0)
            pdf.cell(95, 8, right, border=0, ln=1, align='R')
            pdf.ln(5)

        # Total geral
        pdf.set_fill_color(220, 230, 250)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font('Arial', 'B', 13)
        pdf.cell(0, 10, f"TOTAL GERAL DO ORÇAMENTO: R$ {total_geral:.2f}", ln=True, align='C', fill=True)

        # Gera bytes e envia
        output = pdf.output(dest='S')
        if isinstance(output, str):
            output = output.encode('latin-1')
        buffer = io.BytesIO(output)
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name='orcamento.pdf')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
