from flask import Flask, request, jsonify, send_file, render_template_string, redirect
import fdb
import os
from fpdf import FPDF
import io
from urllib.parse import quote_plus, unquote_plus
import datetime

app = Flask(__name__)

# Configurações do banco Firebird via variáveis de ambiente (com defaults)
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "farmaciaamazon01.ddns.net"),
    "database": os.getenv("DB_DATABASE", "ALTERDB"),
    "user": os.getenv("DB_USER", "SYSDBA"),
    "password": os.getenv("DB_PASSWORD", "masterkey"),
    "port": int(os.getenv("DB_PORT", 3050)),
    "charset": os.getenv("DB_CHARSET", "WIN1252")
}
API_TOKEN = "amazon"

# Servir logo estático
@app.route('/logo.png')
def logo_png():
    path = os.path.join(app.root_path, 'logo.png')
    if os.path.exists(path):
        return send_file(path, mimetype='image/png')
    return '', 404

class PDF(FPDF):
    def header(self):
        logo_path = os.path.join(app.root_path, 'logo.png')
        if os.path.exists(logo_path):
            try: self.image(logo_path, x=10, y=2, w=100)
            except: pass
        self.set_font('Arial', 'B', 12)
        self.set_xy(140, 10)
        self.cell(60, 10, f"ORÇAMENTO: {self.order_number}-{self.total_formulations}", align='R')
        if getattr(self, 'patient_name', ''):
            self.set_xy(140, 17)
            self.cell(60, 8, f"PACIENTE: {self.patient_name}", align='R')
        self.ln(25)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        page_str = f"Orçamento: {self.order_number} - Página {self.page_no()}/{{nb}}"
        self.cell(0, 10, page_str, align='C')

@app.before_request
def check_auth():
    if request.endpoint in ('home', 'logo_png', 'generate_pdf'):
        return
    token = request.headers.get('Authorization')
    if token != f"Bearer {API_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

# Carrega itens agrupados + dtentr
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
        return None, None, None, {}
    first = dict(zip(cols, rows[0]))
    order    = first.get('NRORC')
    patient  = first.get('NOMEPA', '')
    dtentr   = first.get('DTENTR')
    if isinstance(dtentr, datetime.datetime):
        dtentr = dtentr.date()

    grouped = {}
    for r in rows:
        rec = dict(zip(cols, r))
        key = (rec['NRORC'], rec['SERIEO'])
        info = grouped.setdefault(key, {
            'items': [], 'volume': rec.get('VOLUME'),
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
    return order, patient, dtentr, grouped

# Carrega totais gerais e desconto
def load_totals(nrorc, filial):
    sql = (
        f"SELECT VRRQU, VRDSC FROM fc15000 "
        f"WHERE NRORC='{nrorc}' AND CDFIL='{filial}'"
    )
    dsn = f"{DB_CONFIG['host']}/{DB_CONFIG['port']}:{DB_CONFIG['database']}"
    con = fdb.connect(dsn=dsn,
                      user=DB_CONFIG['user'],
                      password=DB_CONFIG['password'],
                      charset=DB_CONFIG['charset'])
    cur = con.cursor()
    cur.execute(sql)
    row = cur.fetchone()
    con.close()
    if not row:
        return 0.0, 0.0
    return float(row[0] or 0), float(row[1] or 0)

# Formulário e visualização HTML
@app.route('/', methods=['GET'])
def home():
    nrorc = request.args.get('nrorc', '').strip()
    filial = request.args.get('filial', '1').strip()
    fmt = request.args.get('format', 'html')
    if not nrorc:
        return render_template_string('''<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="UTF-8"><title>Consultar Orçamento</title>
<style>/* seu CSS */</style></head><body>
<!-- seu formulário -->
</body></html>''')

    # Monta consulta incluindo DTENTR
    sql = (
        f"SELECT f10.NRORC,f10.SERIEO,f10.TPCMP,f10.DESCR,f10.QUANT,f10.UNIDA," 
        f"f00.VOLUME,f00.UNIVOL,f00.PRCOBR,f00.NOMEPA, f00.DTENTR "
        f"FROM fc15110 f10 JOIN fc15100 f00 "
        f"ON f10.NRORC=f00.NRORC AND f10.SERIEO=f00.SERIEO "
        f"WHERE f10.NRORC='{nrorc}' AND f10.cdfil='{filial}' AND f10.TPCMP IN ('C','H','F')"
    )
    order, patient, dtentr, grouped = load_grouped(sql)
    if not grouped:
        return f"<p>Orçamento {nrorc} não encontrado.</p>", 404

    total_forms       = len(grouped)
    total_geral_items = sum(info['prcobr'] for info in grouped.values())
    valor_geral, valor_desc = load_totals(order, filial)
    valor_final       = valor_geral - valor_desc
    validade          = (dtentr + datetime.timedelta(days=7)) if dtentr else None

    # Formata datas
    dtentr_str   = dtentr.strftime('%d/%m/%Y') if dtentr else ''
    validade_str = validade.strftime('%d/%m/%Y') if validade else ''

    if fmt == 'pdf':
        return redirect(f"/pdf?nrorc={order}&filial={filial}")

    html_tpl = '''<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="UTF-8"><title>Orçamento {{order}}</title>
<style>/* seu CSS */</style></head><body>
<header>...<div><strong>ORÇAMENTO:</strong> {{order}}-{{total_forms}}</div>... </header>
<main>
{% for info in grouped.values() %}
  <div class="section">
    <div class="header">Formulação {{"%02d"|format(loop.index)}}</div>
    <div class="items">
      {% for it in info['items'] %}
      <div><span class="descr">{{it.descr}}</span><span class="qty">{{it.quant}}</span><span class="unit">{{it.unida}}</span></div>
      {% endfor %}
    </div>
    <div class="volume-total"><div class="left"><strong>Volume:</strong> {{info.volume}} {{info.univol}}</div><div class="right"><strong>Total:</strong> R$ {{"%.2f"|format(info.prcobr)}}</div><div class="clear"></div></div>
  </div>
{% endfor %}
</main>
<div class="totais">
  <p>VALOR TOTAL GERAL: R$ {{"%.2f"|format(valor_geral)}}</p>
  <p>VALOR DO DESCONTO: R$ {{"%.2f"|format(valor_desc)}}</p>
  <p style="background:rgb(180,240,180);padding:6px;">VALOR TOTAL DO ORÇAMENTO: R$ {{"%.2f"|format(valor_final)}}</p>
  <p><strong>Data do Orçamento:</strong> {{dtentr_str}}</p>
  <p><strong>Validade do Orçamento:</strong> {{validade_str}}</p>
</div>
<a class="btn" href="/pdf?nrorc={{order}}&filial={{filial}}">Download PDF</a>
<footer>Orçamento: {{order}} - Página 1/{{total_forms}}</footer>
</body></html>'''

    return render_template_string(html_tpl,
        order=order,
        patient=patient,
        grouped=grouped,
        total_forms=total_forms,
        valor_geral=valor_geral,
        valor_desc=valor_desc,
        valor_final=valor_final,
        dtentr_str=dtentr_str,
        validade_str=validade_str,
        filial=filial
    )

@app.route('/pdf', methods=['GET'])
def generate_pdf():
    nrorc = request.args.get('nrorc', '').strip()
    filial = request.args.get('filial', '1').strip()
    sql = (
        f"SELECT f10.NRORC,f10.SERIEO,f10.TPCMP,f10.DESCR,f10.QUANT,f10.UNIDA," 
        f"f00.VOLUME,f00.UNIVOL,f00.PRCOBR,f00.NOMEPA, f00.DTENTR "
        f"FROM fc15110 f10 JOIN fc15100 f00 "
        f"ON f10.NRORC=f00.NRORC AND f10.SERIEO=f00.SERIEO "
        f"WHERE f10.NRORC='{nrorc}' AND f10.cdfil='{filial}' AND f10.TPCMP IN ('C','H','F')"
    )
    order, patient, dtentr, grouped = load_grouped(sql)
    total_forms       = len(grouped)
    total_geral_items = sum(i['prcobr'] for i in grouped.values())
    valor_geral, valor_desc = load_totals(order, filial)
    valor_final       = valor_geral - valor_desc
    validade          = (dtentr + datetime.timedelta(days=7)) if dtentr else None

    pdf = PDF(format='A4')
    pdf.alias_nb_pages()
    pdf.order_number      = order
    pdf.total_formulations = total_forms
    pdf.patient_name      = patient
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    desc_w, qty_w, unit_w, row_h = 110, 30, 30, 6
    for idx, info in enumerate(grouped.values(), start=1):
        if pdf.get_y() + row_h > pdf.page_break_trigger:
            pdf.add_page()
        pdf.set_fill_color(200, 230, 200)
        pdf.set_text_color(60, 60, 60)
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, f"Formulação {idx:02}", ln=True, align='L', fill=True)
        pdf.set_font('Arial', '', 11)
        for it in info['items']:
            if pdf.get_y() + row_h > pdf.page_break_trigger:
                pdf.add_page()
            y = pdf.get_y()
            pdf.set_xy(pdf.l_margin, y)
            pdf.cell(desc_w, row_h, it['descr'], border=0)
            x_qty = pdf.w - pdf.r_margin - unit_w - qty_w
            pdf.set_xy(x_qty, y)
            pdf.cell(qty_w, row_h, str(it['quant']), border=0, align='R')
            x_unida = pdf.w - pdf.r_margin - unit_w
            pdf.set_xy(x_unida, y)
            pdf.cell(unit_w, row_h, it['unida'], border=0, ln=1, align='R')
        y = pdf.get_y()
        if y + 8 > pdf.page_break_trigger:
            pdf.add_page()
            y = pdf.get_y()
        pdf.set_xy(10, y)
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(70, 8, f"Volume: {info['volume']} {info['univol']}", border=0)
        pdf.set_xy(140, y)
        pdf.cell(60, 8, f"Total: R$ {info['prcobr']:.2f}", border=0, ln=1, align='R')
        pdf.ln(4)

    # totais finais e datas
    pdf.set_fill_color(180, 240, 180)
    pdf.set_text_color(60, 60, 60)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, f"VALOR TOTAL GERAL: R$ {valor_geral:.2f}", ln=True, align='R')
    pdf.cell(0, 8, f"VALOR DO DESCONTO: R$ {valor_desc:.2f}", ln=True, align='R')
    pdf.cell(0,10, f"VALOR TOTAL DO ORÇAMENTO: R$ {valor_final:.2f}", ln=True, align='R', fill=True)
    pdf.ln(4)
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 8, f"Data do Orçamento: {dtentr.strftime('%d/%m/%Y') if dtentr else ''}", ln=True)
    if validade:
        pdf.cell(0, 8, f"Validade do Orçamento: {validade.strftime('%d/%m/%Y')}", ln=True)

    out = pdf.output(dest='S')
    if isinstance(out, str): out = out.encode('latin-1')
    filename = f"ORCAMENTO_AMAZON_{order}.pdf"
    return send_file(io.BytesIO(out), mimetype='application/pdf', as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
