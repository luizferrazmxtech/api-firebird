from flask import Flask, request, jsonify, send_file, render_template_string
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
    "charset": "WIN1252"
}

# Token de segurança para autenticação
API_TOKEN = os.getenv("API_TOKEN", "seu_token_aqui")

class PDF(FPDF):
    def header(self):
        # Logo
        if os.path.exists('logo.png'):
            try:
                self.image('logo.png', x=10, y=-5, w=50, type='PNG')
            except:
                pass
        # ORÇAMENTO
        self.set_font('Arial', 'B', 12)
        self.set_xy(140, 10)
        self.cell(60, 10, f"ORÇAMENTO: {self.order_number}-{self.total_formulations}", align='R')
        # PACIENTE
        if getattr(self, 'patient_name', ''):
            self.set_xy(140, 17)
            self.cell(60, 8, f"PACIENTE: {self.patient_name}", align='R')
        self.ln(25)

    def footer(self):
        # Rodapé
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        page_str = f"Orçamento: {self.order_number} - Página {self.page_no()}/{self.alias_nb_pages()}"
        self.cell(0, 10, page_str, align='C')

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
        # Conexão Firebird
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
        # Extrai paciente e dados de orcamento
        first = dict(zip(cols, rows[0]))
        patient_name = first.get('NOMEPA', '')
        grouped = {}
        for r in rows:
            rec = dict(zip(cols, r))
            key = (rec['NRORC'], rec['SERIEO'])
            info = grouped.setdefault(key, {
                'items': [],
                'volume': rec.get('VOLUME'),
                'univol': rec.get('UNIVOL'),
                'prcobr': float(rec.get('PRCOBR') or 0)
            })
            descr = rec.get('DESCR') or ''
            if descr.strip():
                info['items'].append({'descr': descr, 'quant': rec.get('QUANT') or '', 'unida': rec.get('UNIDA') or ''})
        total_geral = sum(v['prcobr'] for v in grouped.values())
        order_num = list(grouped.keys())[0][0]
        total_forms = len(grouped)
        # Geração PDF
        pdf = PDF(format='A4')
        pdf.alias_nb_pages()
        pdf.order_number = order_num
        pdf.total_formulations = total_forms
        pdf.patient_name = patient_name
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()
        w_desc, w_qty, w_unit, h = 110, 30, 30, 6
        for idx, (_, info) in enumerate(grouped.items(), 1):
            pdf.set_fill_color(200, 230, 200)
            pdf.set_text_color(60, 60, 60)
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, h, f"Formulação {idx:02}", ln=1, fill=True)
            pdf.set_font('Arial', '', 11)
            for it in info['items']:
                pdf.cell(w_desc, h, it['descr'], border=0)
                pdf.cell(w_qty, h, str(it['quant']), border=0, align='C')
                pdf.cell(w_unit, h, it['unida'], border=0, ln=1, align='C')
            y = pdf.get_y()
            pdf.ln(1)
            pdf.set_xy(10, y)
            pdf.set_font('Arial', 'B', 11)
            pdf.cell(70, h, f"Volume: {info['volume']} {info['univol']}")
            pdf.set_xy(140, y)
            pdf.cell(60, h, f"Total: R$ {info['prcobr']:.2f}", align='R')
            pdf.ln(4)
        pdf.set_fill_color(180, 240, 180)
        pdf.set_font('Arial', 'B', 13)
        pdf.cell(0, 10, f"TOTAL GERAL DO ORÇAMENTO: R$ {total_geral:.2f}", ln=1, align='R', fill=True)
        data = pdf.output(dest='S')
        if isinstance(data, str): data = data.encode('latin-1')
        return send_file(io.BytesIO(data), mimetype='application/pdf', as_attachment=True, download_name='orcamento.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Endpoint HTML no mesmo padrão do PDF
@app.route('/html', methods=['GET'])
def generate_html():
    sql = request.args.get('sql')
    if not sql or not sql.strip().lower().startswith("select"):
        return jsonify({"error": "Only SELECT queries are allowed"}), 400
    try:
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
        first = dict(zip(cols, rows[0]))
        patient_name = first.get('NOMEPA', '')
        grouped = {}
        for r in rows:
            rec = dict(zip(cols, r))
            key = (rec['NRORC'], rec['SERIEO'])
            info = grouped.setdefault(key, {
                'items': [],
                'volume': rec.get('VOLUME'),
                'univol': rec.get('UNIVOL'),
                'prcobr': float(rec.get('PRCOBR') or 0)
            })
            descr = rec.get('DESCR') or ''
            if descr.strip():
                info['items'].append({'descr': descr, 'quant': rec.get('QUANT') or '', 'unida': rec.get('UNIDA') or ''})
        total_geral = sum(v['prcobr'] for v in grouped.values())
        order_num = list(grouped.keys())[0][0]
        total_forms = len(grouped)
        # Template HTML
        tpl = '''
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Orçamento {{order_num}}</title>
<style>
body{font-family:Arial,sans-serif;margin:20px;}
header,footer{overflow:hidden;padding:10px;background:#f0f0f0;}
header img{height:50px;float:left;}
header .info{float:right;text-align:right;}
header .info .label{font-weight:bold;}
.clear{clear:both;}
.formula{margin-top:20px;}
.formula-header{background:rgb(200,230,200);color:#3C3C3C;padding:6px;font-weight:bold;}
.items div{display:flex;padding:2px 0;}
.items .descr{flex:1;}
.items .qty, .items .unit{width:50px;text-align:center;}
.volume-total{margin:10px 0;}
.volume-total .left{float:left;}
.volume-total .right{float:right;}
footer{font-size:0.8em;color:#666;text-align:center;margin-top:40px;}
</style>
</head>
<body>
<header>
<img src="logo.png">
<div class="info">
<div><span class="label">ORÇAMENTO:</span> {{order_num}}-{{total_forms}}</div>
{% if patient_name %}<div><span class="label">PACIENTE:</span> {{patient_name}}</div>{% endif %}
</div>
<div class="clear"></div>
</header>
{% for idx,(key,info) in formulations %}
<div class="formula">
<div class="formula-header">Formulação {{"%02d"|format(idx)}}</div>
<div class="items">
{% for it in info.items %}
<div><span class="descr">{{it.descr}}</span><span class="qty">{{it.quant}}</span><span class="unit">{{it.unida}}</span></div>
{% endfor %}
</div>
<div class="volume-total">
<div class="left"><strong>Volume:</strong> {{info.volume}} {{info.univol}}</div>
<div class="right"><strong>Total:</strong> R$ {{"%.2f"|format(info.prcobr)}}</div>
<div class="clear"></div>
</div>
</div>
{% endfor %}
<footer>Orçamento: {{order_num}} - Página 1</footer>
</body>
</html>
'''
        # Render
        html = render_template_string(tpl,
            order_num=order_num,
            total_forms=total_forms,
            patient_name=patient_name,
            formulations=list(grouped.items()),
            total_geral=total_geral
        )
        return html
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
