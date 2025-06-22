from flask import Flask, request, jsonify, send_file, render_template_string, redirect
import fdb
import os
from fpdf import FPDF
import io
from urllib.parse import quote_plus, unquote_plus

app = Flask(__name__)

# Configurações do banco Firebird hardcoded
DB_CONFIG = {
    "host": "farmaciaamazon01.ddns.net",
    "database": "ALTERDB",
    "user": "SYSDBA",
    "password": "masterkey",
    "port": 3050,
    "charset": "WIN1252"
}
# Token de segurança
API_TOKEN = "amazon"

# Servir logo diretamente
@app.route('/logo.png')
def logo_png():
    path = os.path.join(app.root_path, 'logo.png')
    if os.path.exists(path):
        return send_file(path, mimetype='image/png')
    return '', 404

class PDF(FPDF):
    def header(self):
        # Logo maior
        path = os.path.join(app.root_path, 'logo.png')
        if os.path.exists(path):
            try:
                self.image(path, x=10, y=-5, w=100)
            except:
                pass
        # Orçamento
        self.set_font('Arial', 'B', 12)
        self.set_xy(140, 10)
        self.cell(60, 10, f"ORÇAMENTO: {self.order_number}-{self.total_formulations}", align='R')
        # Paciente
        if getattr(self, 'patient_name', ''):
            self.set_xy(140, 17)
            self.cell(60, 8, f"PACIENTE: {self.patient_name}", align='R')
        self.ln(25)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        # Página atual / total de páginas
        page_no = self.page_no()
        page_str = f"Orçamento: {self.order_number} - Página {page_no}/{{nb}}"
        self.cell(0, 10, page_str, align='C')

@app.before_request
def check_auth():
    # libera acesso às páginas iniciais e PDF sem token
    if request.endpoint in ('home', 'logo_png', 'generate_pdf'):
        return
    token = request.headers.get('Authorization')
    if token != f"Bearer {API_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

# Helper para carregar dados via SQL
def load_grouped(sql):
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
        return None, None, {}
    first = dict(zip(cols, rows[0]))
    order = first.get('NRORC')
    patient = first.get('NOMEPA', '')
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
            info['items'].append({
                'descr': descr,
                'quant': rec.get('QUANT') or '',
                'unida': rec.get('UNIDA') or ''
            })
    return order, patient, grouped

# Página inicial: formulário e resultado HTML/PDF
@app.route('/', methods=['GET'])
def home():
    nrorc = request.args.get('nrorc', '').strip()
    fmt = request.args.get('format', 'html')
    if not nrorc:
        # exibe formulário com logo centralizado e maior
        return render_template_string('''
<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="UTF-8">
  <title>Consultar Orçamento</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #f8f8f8; }
    header { background: #f0f0f0; padding: 40px; display: flex; align-items: center; }
    header img { height: 200px; }
    header h1 { margin-left: auto; margin-right: 20px; font-size: 24px; }
    .container { max-width: 400px; margin: 40px auto; background: #fff; padding: 20px; border-radius: 8px; }
    .container h2 { text-align: center; }
    label, input, button { display: block; width: 100%; margin-bottom: 10px; }
    input { padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
    .btn-html { padding: 10px; background: #c8e6c9; color: #3C3C3C; border: none; border-radius: 4px; font-weight: bold; }
    .btn-pdf  { padding: 10px; background: #a5d6a7; color: #fff; border: none; border-radius: 4px; font-weight: bold; }
  </style>
</head>
<body>
<header>
  <img src="/logo.png" alt="Logo">
  <h1>Consultar Orçamento</h1>
</header>
<div class="container">
  <form action="/" method="get">
    <label for="nrorc">Número do Orçamento:</label>
    <input id="nrorc" name="nrorc" required>
    <button class="btn-html" type="submit" name="format" value="html">Visualizar HTML</button>
    <button class="btn-pdf"  type="submit" name="format" value="pdf">Download PDF</button>
  </form>
</div>
</body>
</html>
''')
    # monta SQL fixo
    sql = ("SELECT f10.NRORC,f10.SERIEO,f10.TPCMP,f10.DESCR,f10.QUANT,f10.UNIDA,"
           "f00.VOLUME,f00.UNIVOL,f00.PRCOBR,f00.NOMEPA FROM fc15110 f10 JOIN fc15100 f00 "
           "ON f10.NRORC=f00.NRORC AND f10.SERIEO=f00.SERIEO "
           f"WHERE f10.NRORC='{nrorc}' AND f10.TPCMP IN ('C','H','F')")
    order, patient, grouped = load_grouped(sql)
    if not grouped:
        return f"<p>Orçamento {nrorc} não encontrado.</p>", 404
    total_forms = len(grouped)
    if fmt == 'pdf':
        return redirect(f"/pdf?nrorc={order}")
    # renderiza HTML inline
    html_tpl = '''
<!DOCTYPE html><html lang="pt-br"><head><meta charset="UTF-8"><title>Orçamento {{order}}</title>
<style>
body{font-family:Arial,sans-serif;margin:20px}
header,footer{background:#f0f0f0;padding:10px;overflow:hidden}
header img{height:100px;float:left}
header .info{float:right;text-align:right}
.clear{clear:both}
.section{margin-top:20px}
.section .header{background:rgb(200,230,200);color:#3C3C3C;padding:6px;font-weight:bold}
.items div{display:flex;padding:6px 0}
.items .descr{flex:1}
.items .qty,.items .unit{width:50px;text-align:center}
.volume-total{margin:10px 0;overflow:hidden}
.volume-total .left{float:left}
.volume-total .right{float:right}
footer{font-size:0.8em;color:#666;text-align:center;margin-top:40px}
a.btn{display:inline-block;margin-top:20px;padding:8px 12px;background:#189c00;color:#fff;text-decoration:none;border-radius:4px}
</style></head><body>
<header>
  <img src="/logo.png" alt="Logo">
  <div class="info">
    <div><span class="header-label">ORÇAMENTO:</span> {{order}}-{{total_forms}}</div>
    {% if patient %}<div><span class="header-label">PACIENTE:</span> {{patient}}</div>{% endif %}
  </div>
  <div class="clear"></div>
</header>
<main>
{% for info in grouped.values() %}
  <div class="section">
    <div class="header">Formulação {{"%02d"|format(loop.index)}}</div>
    <div class="items">
      {% for it in info['items'] %}
      <div><span class="descr">{{it.descr}}</span><span class="qty">{{it.quant}}</span><span class="unit">{{it.unida}}</span></div>
      {% endfor %}
    </div>
    <div class="volume-total"> <div class="left"><strong>Volume:</strong> {{info.volume}} {{info.univol}}</div> <div class="right"><strong>Total:</strong> R$ {{"%.2f"|format(info.prcobr)}}</div> <div class="clear"></div> </div>
  </div>
{% endfor %}
</main>
<a class="btn" href="/pdf?nrorc={{order}}">Download PDF</a>
<footer>Orçamento: {{order}} - Página 1</footer>
</body>
</html>
'''
    return render_template_string(html_tpl,
        order=order,
        patient=patient,
        grouped=grouped,
        total_forms=total_forms
    )

@app.route('/pdf', methods=['GET'])
def generate_pdf():
    nrorc = request.args.get('nrorc', '').strip()
    if not nrorc:
        return jsonify({"error": "nrorc parameter is required"}), 400
    # monta mesmo SQL do home
    sql = ("SELECT f10.NRORC,f10.SERIEO,f10.TPCMP,f10.DESCR,f10.QUANT,f10.UNIDA,"
           "f00.VOLUME,f00.UNIVOL,f00.PRCOBR,f00.NOMEPA FROM fc15110 f10 JOIN fc15100 f00 "
           "ON f10.NRORC=f00.NRORC AND f10.SERIEO=f00.SERIEO "
           f"WHERE f10.NRORC='{nrorc}' AND f10.TPCMP IN ('C','H','F')")
    order, patient, grouped = load_grouped(sql)
    if not grouped:
        return jsonify({"error": "No data found"}), 404
    total_forms = len(grouped)
    # Geração PDF com alias total páginas
    pdf = PDF(format='A4')
    pdf.alias_nb_pages()
    pdf.order_number = order
    pdf.total_formulations = total_forms
    pdf.patient_name = patient
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    desc_w, qty_w, unit_w, row_h = 110, 30, 30, 6
    for idx, info in enumerate(grouped.values(), start=1):
        pdf.set_fill_color(200, 230, 200)
        pdf.set_text_color(60, 60, 60)
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, f"Formulação {idx:02}", ln=1, align='L', fill=True)
        pdf.set_font('Arial', '', 11)
        for it in info['items']:
            pdf.cell(desc_w, row_h, it['descr'], border=0)
            pdf.cell(qty_w, row_h, str(it['quant']), border=0, align='C')
            pdf.cell(unit_w, row_h, it['unida'], border=0, ln=1, align='C')
        pdf.ln(1)
        y = pdf.get_y()
        pdf.set_xy(10, y)
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(70, 8, f"Volume: {info['volume']} {info['univol']}", border=0)
        pdf.set_xy(140, y)
        pdf.cell(60, 8, f"Total: R$ {info['prcobr']:.2f}", border=0, ln=1, align='R')
        pdf.ln(4)
    pdf.set_fill_color(180, 240, 180)
    pdf.set_text_color(60, 60, 60)
    pdf.set_font('Arial', 'B', 13)
    total_geral = sum(i['prcobr'] for i in grouped.values())
    pdf.cell(0, 10, f"TOTAL GERAL DO ORÇAMENTO: R$ {total_geral:.2f}", ln=1, align='R', fill=True)
    out = pdf.output(dest='S')
    if isinstance(out, str):
        out = out.encode('latin-1')
    filename = f"ORCAMENTO_AMAZON_{order}.pdf"
    return send_file(io.BytesIO(out), mimetype='application/pdf', as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
