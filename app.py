from flask import Flask, request, jsonify, send_file
import fdb
import os
from fpdf import FPDF
import io

app = Flask(__name__)

# Configuração do banco Firebird via variáveis de ambiente
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_DATABASE"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", 3050)),
    "charset": "UTF8"
}

# Token de segurança para autenticação
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
    if not sql or not sql.strip().lower().startswith("select"):
        return jsonify({"error": "Only SELECT queries are allowed"}), 400

    try:
        # Conexão ao Firebird
        dsn = f"{DB_CONFIG['host']}/{DB_CONFIG['port']}:{DB_CONFIG['database']}"
        con = fdb.connect(dsn=dsn,
                          user=DB_CONFIG['user'],
                          password=DB_CONFIG['password'],
                          charset=DB_CONFIG['charset'])
        cur = con.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        con.close()

        if not rows:
            return jsonify({"error": "No data found"}), 404

        # Agrupar por (NRORC, SERIEO)
        grouped = {}
        for r in rows:
            rec = dict(zip(cols, r))
            key = (rec['NRORC'], rec['SERIEO'])
            if key not in grouped:
                grouped[key] = {
                    'items': [],
                    'volume': rec.get('VOLUME'),
                    'univol': rec.get('UNIVOL'),
                    'prcobr': float(rec.get('PRCOBR') or 0)
                }
            grouped[key]['items'].append({
                'descr': rec.get('DESCR'),
                'quant': rec.get('QUANT'),
                'unida': rec.get('UNIDA')
            })

        total_geral = sum(v['prcobr'] for v in grouped.values())

        # Inicia PDF A4
        pdf = FPDF(format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # --- Cabeçalho: logo à esquerda e número do orçamento à direita ---
        # Desenha logo
        if os.path.exists('logo.png'):
            pdf.image('logo.png', x=10, y=2, w=50)
        # Orçamento no topo
        primeiro = list(grouped.keys())[0][0]
        pdf.set_font('Arial', '', 12)
        pdf.set_xy(140, 15)
        pdf.cell(60, 10, f"ORÇAMENTO: {primeiro}-{len(grouped)}", align='R')
        # Move cursor para abaixo desse cabeçalho
        pdf.set_y(45)

        # Definindo larguras das colunas de itens
        desc_w = 110
        qty_w = 40
        unit_w = 35

        # --- Cada Formulação ---
        for idx, ((nro, serie), info) in enumerate(grouped.items(), start=1):
            # Título da formulação com fundo verde claro e texto à esquerda
            pdf.set_fill_color(200, 230, 200)  # verde suave
            pdf.set_text_color(255, 255, 255)
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 10, f"Formulação {idx:02}", ln=True, align='L', fill=True)

            # Itens lado a lado, sem fundo adicional
            pdf.set_text_color(60, 60, 60)
            pdf.set_font('Arial', '', 11)
            for item in info['items']:
                pdf.cell(desc_w, 8, str(item['descr'] or ''), border=0)
                pdf.cell(qty_w, 8, str(item['quant'] or ''), border=0, align='C')
                pdf.cell(unit_w, 8, str(item['unida'] or ''), border=0, ln=1, align='C')

            # Volume e Total da formulação
            pdf.ln(1)
            pdf.set_font('Arial', 'B', 11)
            pdf.cell(70, 8, f"Volume: {info['volume']} {info['univol']}", border=0)
            pdf.cell(125, 8, f"Total: R$ {info['prcobr']:.2f}", border=0, ln=1, align='R')
            pdf.ln(5)

        # --- Total Geral no final ---
        pdf.set_fill_color(0, 100, 0)  # verde escuro para total geral
        pdf.set_text_color(0, 0, 0)
        pdf.set_font('Arial', 'B', 13)
        pdf.cell(0, 12, f"TOTAL GERAL DO ORÇAMENTO: R$ {total_geral:.2f}", ln=True, align='R', fill=True)

        # Gera e envia PDF
        out = pdf.output(dest='S')
        if isinstance(out, str):
            out = out.encode('latin-1')
        buffer = io.BytesIO(out)
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name='orcamento.pdf')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
