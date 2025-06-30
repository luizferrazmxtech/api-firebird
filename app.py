from flask import Flask, request, jsonify, send_file, render_template_string, redirect
import fdb
import os
from fpdf import FPDF
import io
import datetime

app = Flask(__name__)

# Configuração do Firebird
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "farmaciaamazon01.ddns.net"),
    "database": os.getenv("DB_DATABASE", "ALTERDB"),
    "user": os.getenv("DB_USER", "SYSDBA"),
    "password": os.getenv("DB_PASSWORD", "masterkey"),
    "port": int(os.getenv("DB_PORT", 3050)),
    "charset": os.getenv("DB_CHARSET", "WIN1252")
}

API_TOKEN = "amazon"

# Serve o logo
@app.route('/logo.png')
def logo_png():
    path = os.path.join(app.root_path, 'logo.png')
    if os.path.exists(path):
        return send_file(path, mimetype='image/png')
    return '', 404

# Classe PDF com cabeçalho e rodapé
class PDF(FPDF):
    def header(self):
        logo = os.path.join(app.root_path, 'logo.png')
        if os.path.exists(logo):
            try:
                self.image(logo, x=10, y=2, w=100)
            except:
                pass
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
        self.cell(0, 10, f"Orçamento: {self.order_number} - Página {self.page_no()}/{{nb}}", align='C')

# Autenticação (home e recursos públicos não exigem token)
@app.before_request
def check_auth():
    if request.endpoint in ('home', 'logo_png', 'generate_pdf'):
        return
    token = request.headers.get('Authorization')
    if token != f"Bearer {API_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

def load_grouped(sql):
    dsn = f"{DB_CONFIG['host']}/{DB_CONFIG['port']}:{DB_CONFIG['database']}"
    con = fdb.connect(dsn=dsn, user=DB_CONFIG['user'], password=DB_CONFIG['password'], charset=DB_CONFIG['charset'])
    cur = con.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    con.close()
    if not rows:
        return None, None, None, {}

    first = dict(zip(cols, rows[0]))
    order = first.get('NRORC')
    patient = first.get('NOMEPA', '')
    dtentr = first.get('DTENTR')
    if isinstance(dtentr, datetime.datetime):
        dtentr = dtentr.date()

    grouped = {}
    for r in rows:
        rec = dict(zip(cols, r))
        key = (rec['NRORC'], rec['SERIEO'])
        info = grouped.setdefault(key, {
            'items': [],
            'volume': rec.get('VOLUME'),
            'univol': rec.get('UNIVOL'),
            'prcobr': float(rec.get('PRCOBR') or 0),
            'vrdsc': float(rec.get('VRDSC') or 0)
        })
        descr = rec.get('DESCR') or ''
        if descr.strip():
            info['items'].append({
                'descr': descr,
                'quant': rec.get('QUANT') or '',
                'unida': rec.get('UNIDA') or ''
            })

    # Calcula total por formulação (PRCOBR - VRDSC)
    for info in grouped.values():
        info['total'] = info['prcobr'] - info['vrdsc']

    return order, patient, dtentr, grouped

# Rota principal: formulário e HTML de resultado
@app.route('/', methods=['GET'])
def home():
    nrorc = request.args.get('nrorc', '').strip()
    filial = request.args.get('filial', '1').strip()
    fmt = request.args.get('format', 'html')

    # sem número, exibe o form
    if not nrorc:
        return render_template_string('''
            <h1>Consultar Orçamento</h1>
            <form method="get">
              Número do Orçamento: <input name="nrorc"/><br/>
              Filial: <input name="filial" value="1"/><br/>
              <button type="submit" name="format" value="html">Visualizar HTML</button>
              <button type="submit" name="format" value="pdf">Download PDF</button>
            </form>
        ''')

    # monta SQL com DTENTR e VRDSC
    sql = (
        f"SELECT f10.NRORC,f10.SERIEO,f10.TPCMP,f10.DESCR,f10.QUANT,f10.UNIDA,"
        f"f00.VOLUME,f00.UNIVOL,f00.PRCOBR,f00.VRDSC,f00.NOMEPA,f00.DTENTR "
        f"FROM fc15110 f10 "
        f"JOIN fc15100 f00 ON f10.NRORC=f00.NRORC AND f10.SERIEO=f00.SERIEO "
        f"WHERE f10.NRORC='{nrorc}' AND f10.cdfil='{filial}' AND f10.TPCMP IN ('C','H','F')"
    )
    order, patient, dtentr, grouped = load_grouped(sql)
    if not grouped:
        return f"<h3>Orçamento {nrorc} não encontrado.</h3>", 404

    total_forms = len(grouped)
    total_geral = sum(info['total'] for info in grouped.values())

    validade = (dtentr + datetime.timedelta(days=7)) if dtentr else None
    dtentr_str = dtentr.strftime('%d/%m/%Y') if dtentr else ''
    validade_str = validade.strftime('%d/%m/%Y') if validade else ''

    if fmt == 'pdf':
        return redirect(f"/pdf?nrorc={order}&filial={filial}")

    html_tpl = '''
    <h1>Orçamento {{order}}</h1>
    {% if patient %}
    <p><strong>PACIENTE:</strong> {{patient}}</p>
    {% endif %}

    {% for info in grouped.values() %}
      <h3>Formulação {{"%02d"|format(loop.index)}}</h3>
      <ul>
        {% for it in info['items'] %}
          <li>{{it.descr}} {{it.quant}} {{it.unida}}</li>
        {% endfor %}
      </ul>
      <p>Volume: {{info.volume}} {{info.univol}}</p>
      <p><strong>Total:</strong> R$ {{"%.2f"|format(info.total)}}</p>
    {% endfor %}

    <h2>VALOR TOTAL GERAL: R$ {{"%.2f"|format(total_geral)}}</h2>
    <p>Data do Orçamento: {{dtentr_str}}</p>
    <p>Validade do Orçamento: {{validade_str}}</p>
    '''
    return render_template_string(
        html_tpl,
        order=order,
        patient=patient,
        grouped=grouped,
        total_forms=total_forms,
        total_geral=total_geral,
        dtentr_str=dtentr_str,
        validade_str=validade_str,
        filial=filial
    )

# Endpoint PDF (mesmo SQL)
@app.route('/pdf', methods=['GET'])
def generate_pdf():
    nrorc = request.args.get('nrorc', '').strip()
    filial = request.args.get('filial', '1').strip()

    sql = (
        f"SELECT f10.NRORC,f10.SERIEO,f10.TPCMP,f10.DESCR,f10.QUANT,f10.UNIDA,"
        f"f00.VOLUME,f00.UNIVOL,f00.PRCOBR,f00.VRDSC,f00.NOMEPA,f00.DTENTR "
        f"FROM fc15110 f10 "
        f"JOIN fc15100 f00 ON f10.NRORC=f00.NRORC AND f10.SERIEO=f00.SERIEO "
        f"WHERE f10.NRORC='{nrorc}' AND f10.cdfil='{filial}' AND f10.TPCMP IN ('C','H','F')"
    )
    order, patient, dtentr, grouped = load_grouped(sql)
    total_forms = len(grouped)
    total_geral = sum(info['total'] for info in grouped.values())
    validade = (dtentr + datetime.timedelta(days=7)) if dtentr else None

    pdf = PDF(format='A4')
    pdf.alias_nb_pages()
    pdf.order_number = order
    pdf.total_formulations = total_forms
    pdf.patient_name = patient
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
        if pdf.get_y() + 8 > pdf.page_break_trigger:
            pdf.add_page()
        y = pdf.get_y()
        pdf.set_xy(10, y)
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(70, 8, f"Volume: {info['volume']} {info['univol']}", border=0)
        pdf.set_xy(140, y)
        pdf.cell(60, 8, f"Total: R$ {info['total']:.2f}", border=0, ln=1, align='R')
        pdf.ln(4)

    # Total Geral e datas
    pdf.set_fill_color(180, 240, 180)
    pdf.set_text_color(60, 60, 60)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, f"VALOR TOTAL GERAL: R$ {total_geral:.2f}", ln=True, align='R')
    pdf.ln(4)
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 8, f"Data do Orçamento: {dtentr.strftime('%d/%m/%Y') if dtentr else ''}", ln=True)
    if validade:
        pdf.cell(0, 8, f"Validade do Orçamento: {validade.strftime('%d/%m/%Y')}", ln=True)

    out = pdf.output(dest='S')
    if isinstance(out, str):
        out = out.encode('latin-1')
    filename = f"ORCAMENTO_AMAZON_{order}.pdf"
    return send_file(io.BytesIO(out), mimetype='application/pdf', as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
