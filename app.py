from flask import Flask, request, jsonify, send_file, render_template_string, redirect
import fdb
import os
from fpdf import FPDF
import io
from urllib.parse import quote_plus, unquote_plus

app = Flask(__name__)

# Configurações do banco Firebird
DB_CONFIG = {
    "host": "farmaciaamazon01.ddns.net",
    "database": "ALTERDB",
    "user": "SYSDBA",
    "password": "masterkey",
    "port": 3050,
    "charset": "WIN1252"
}
API_TOKEN = "amazon"

# Rota para servir logo
@app.route('/logo.png')
def logo_png():
    path = os.path.join(app.root_path, 'logo.png')
    if os.path.exists(path):
        return send_file(path, mimetype='image/png')
    return '', 404

class PDF(FPDF):
    def header(self):
        path = os.path.join(app.root_path, 'logo.png')
        if os.path.exists(path):
            try: self.image(path, x=10, y=-5, w=100)
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

# Carrega dados do Firebird e agrupa por NRORC e SERIEO
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

# Endpoint home: formulário e visualização HTML
@app.route('/', methods=['GET'])
def home():
    nrorc = request.args.get('nrorc', '').strip()
    filial = request.args.get('filial', '1').strip()
    fmt = request.args.get('format', 'html')
    if not nrorc:
        return render_template_string('''...''')
    sql = (
        f"SELECT f10.NRORC,f10.SERIEO,f10.TPCMP,f10.DESCR,f10.QUANT,f10.UNIDA,"  
        f"f00.VOLUME,f00.UNIVOL,f00.PRCOBR,f00.NOMEPA FROM fc15110 f10 JOIN fc15100 f00 "
        f"ON f10.NRORC=f00.NRORC AND f10.SERIEO=f00.SERIEO "
        f"WHERE f10.NRORC='{nrorc}' AND f10.cdfil='{filial}' AND f10.TPCMP IN ('C','H','F')"
    )
    order, patient, grouped = load_grouped(sql)
    if not grouped:
        return f"<p>Orçamento {nrorc} não encontrado.</p>", 404
    total_forms = len(grouped)
    total_geral = sum(info['prcobr'] for info in grouped.values())
    if fmt == 'pdf':
        return redirect(f"/pdf?nrorc={order}&filial={filial}")
    html_tpl = '''...'''
    return render_template_string(html_tpl,
        order=order,
        patient=patient,
        grouped=grouped,
        total_forms=total_forms,
        total_geral=total_geral,
        filial=filial
    )

@app.route('/pdf', methods=['GET'])
def generate_pdf():
    nrorc = request.args.get('nrorc', '').strip()
    filial = request.args.get('filial', '1').strip()
    if not nrorc:
        return jsonify({"error": "nrorc parameter is required"}), 400
    sql = (
        f"SELECT f10.NRORC,f10.SERIEO,f10.TPCMP,f10.DESCR,f10.QUANT,f10.UNIDA,"  
        f"f00.VOLUME,f00.UNIVOL,f00.PRCOBR,f00.NOMEPA FROM fc15110 f10 JOIN fc15100 f00 "
        f"ON f10.NRORC=f00.NRORC AND f10.SERIEO=f00.SERIEO "
        f"WHERE f10.NRORC='{nrorc}' AND f10.cdfil='{filial}' AND f10.TPCMP IN ('C','H','F')"
    )
    order, patient, grouped = load_grouped(sql)
    if not grouped:
        return jsonify({"error": "No data found"}), 404
    total_forms = len(grouped)
    total_geral_pdf = sum(i['prcobr'] for i in grouped.values())
    pdf = PDF(format='A4')
    pdf.alias_nb_pages()
    pdf.order_number = order
    pdf.total_formulations = total_forms
    pdf.patient_name = patient
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    desc_w, qty_w, unit_w, row_h = 110, 30, 30, 6
    for idx, info in enumerate(grouped.values(), start=1):
        # nova quebra de página se necessário
        if pdf.get_y() + row_h > pdf.page_break_trigger:
            pdf.add_page()
        pdf.set_fill_color(200, 230, 200)
        pdf.set_text_color(60, 60, 60)
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, f"Formulação {idx:02}", ln=True, align='L', fill=True)
        pdf.set_font('Arial', '', 11)
        for it in info['items']:
            # checa quebra antes de cada linha
            if pdf.get_y() + row_h > pdf.page_break_trigger:
                pdf.add_page()
            y = pdf.get_y()
            pdf.set_xy(pdf.l_margin, y)
            pdf.cell(desc_w, row_h, it['descr'], border=0)
            # quant e unida alinhados no fim
            x_qty = pdf.w - pdf.r_margin - unit_w - qty_w
            pdf.set_xy(x_qty, y)
            pdf.cell(qty_w, row_h, str(it['quant']), border=0, align='R')
            x_unida = pdf.w - pdf.r_margin - unit_w
            pdf.set_xy(x_unida, y)
            pdf.cell(unit_w, row_h, it['unida'], border=0, ln=1, align='R')
        # volume e total
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
    # total geral
    pdf.set_fill_color(180, 240, 180)
    pdf.set_text_color(60, 60, 60)
    pdf.set_font('Arial', 'B', 13)
    pdf.cell(0, 10, f"TOTAL GERAL DO ORÇAMENTO: R$ {total_geral_pdf:.2f}", ln=True, align='R', fill=True)
    out = pdf.output(dest='S')
    if isinstance(out, str): out = out.encode('latin-1')
    filename = f"ORCAMENTO_AMAZON_{order}.pdf"
    return send_file(io.BytesIO(out), mimetype='application/pdf', as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))

