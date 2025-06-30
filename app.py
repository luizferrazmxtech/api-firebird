from flask import Flask, request, jsonify, send_file, render_template_string, redirect
import fdb
import os
from fpdf import FPDF
import io
import datetime

app = Flask(__name__)

# Configuração do Firebird
db_cfg = {
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
    return send_file(path, mimetype='image/png') if os.path.exists(path) else ('', 404)

# PDF class
class PDF(FPDF):
    def header(self):
        logo = os.path.join(app.root_path, 'logo.png')
        if os.path.exists(logo):
            try: self.image(logo, 10, 2, 100)
            except: pass
        self.set_font('Arial','B',12)
        self.set_xy(140, 10)
        self.cell(60, 10, f"ORÇAMENTO: {self.order_number}-{self.total_formulations}", 0, 1, 'R')
        if self.patient_name:
            self.set_xy(140, 17)
            self.cell(60, 8, f"PACIENTE: {self.patient_name}", 0, 1, 'R')
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial','I',8)
        self.cell(0,10, f"Orçamento: {self.order_number} - Página {self.page_no()}/{{nb}}",0,0,'C')

# Autenticação
@app.before_request
def auth():
    if request.endpoint in ['home','logo_png','generate_pdf']: return
    token = request.headers.get('Authorization','').replace('Bearer ','')
    if token != API_TOKEN:
        return jsonify({'error':'Unauthorized'}),401

# Carrega e agrupa dados
def load_grouped(sql):
    dsn = f"{db_cfg['host']}/{db_cfg['port']}:{db_cfg['database']}"
    con = fdb.connect(dsn=dsn, user=db_cfg['user'], password=db_cfg['password'], charset=db_cfg['charset'])
    cur = con.cursor()
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    con.close()
    if not rows: return None,None,None,{}

    first = dict(zip(cols,rows[0]))
    order = first['NRORC']
    patient = first.get('NOMEPA','')
    dtentr = first.get('DTENTR')
    if isinstance(dtentr, datetime.datetime): dtentr = dtentr.date()

    grouped = {}
    for r in rows:
        rec = dict(zip(cols,r))
        key = (rec['NRORC'],rec['SERIEO'])
        g = grouped.setdefault(key, {
            'items': [],
            'volume':rec.get('VOLUME'),
            'univol':rec.get('UNIVOL'),
            'prcobr':float(rec.get('PRCOBR') or 0),
            'vrdsc':float(rec.get('VRDSC') or 0)
        })
        if rec.get('DESCR','').strip():
            g['items'].append({
                'descr':rec['DESCR'],
                'quant':rec.get('QUANT',''),
                'unida':rec.get('UNIDA','')
            })
    for g in grouped.values():
        g['total'] = g['prcobr'] - g['vrdsc']
    return order,patient,dtentr,grouped

# Formulário e resultado HTML
@app.route('/', methods=['GET'])
def home():
    nrorc = request.args.get('nrorc','').strip()
    filial = request.args.get('filial','1').strip()
    fmt = request.args.get('format','html')
    # Formulário inicial
    if not nrorc:
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
          <title>Consultar Orçamento</title>
          <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
          <style>
            :root { --header-gray: #f0f0f0; }
            .logo { max-height: 180px; }
          </style>
        </head>
        <body>
        <div class="container mt-5">
          <div class="text-center mb-4" style="background-color:var(--header-gray); padding:20px;">
            <img src="/logo.png" class="logo" alt="Logo">
          </div>
          <div class="card">
            <div class="card-header bg-white">
              <h4 class="card-title mb-0">Consultar Orçamento</h4>
            </div>
            <div class="card-body">
              <form method="get">
                <div class="form-group">
                  <label for="nrorc">Número do Orçamento</label>
                  <input type="text" id="nrorc" name="nrorc" class="form-control" required>
                </div>
                <div class="form-group">
                  <label for="filial">Tipo</label>
                  <select id="filial" name="filial" class="form-control">
                    <option value="1">Matriz</option>
                    <option value="5">Filial</option>
                  </select>
                </div>
                <div class="d-flex">
                  <button type="submit" name="format" value="html" class="btn btn-success mr-2">Visualizar HTML</button>
                  <button type="submit" name="format" value="pdf" class="btn btn-secondary">Download PDF</button>
                </div>
              </form>
            </div>
          </div>
        </div>
        </body>
        </html>
        """
        )

    # Query e agrupamento
    sql = (
        f"SELECT f10.NRORC,f10.SERIEO,f10.TPCMP,f10.DESCR,f10.QUANT,f10.UNIDA,"
        f"f00.VOLUME,f00.UNIVOL,f00.PRCOBR,f00.VRDSC,f00.NOMEPA,f00.DTENTR "
        f"FROM fc15110 f10 JOIN fc15100 f00 ON f10.NRORC=f00.NRORC AND f10.SERIEO=f00.SERIEO "
        f"WHERE f10.NRORC='{nrorc}' AND f10.cdfil='{filial}' AND f10.TPCMP IN ('C','H','F')"
    )
    order,patient,dtentr,grouped = load_grouped(sql)
    if not grouped:
        return render_template_string("<h3 class='text-center text-danger mt-5'>Orçamento não encontrado.</h3>"),404

    total_geral = sum(g['total'] for g in grouped.values())
    dtentr_str = dtentr.strftime('%d/%m/%Y') if dtentr else ''
    validade = (dtentr + datetime.timedelta(days=7)) if dtentr else None
    validade_str = validade.strftime('%d/%m/%Y') if validade else ''

    if fmt=='pdf':
        return redirect(f"/pdf?nrorc={order}&filial={filial}")

    # HTML de resultado
    html = """
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
      <title>Orçamento {{order}}</title>
      <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
      <style>
        :root { --header-gray: #f0f0f0; --section-gray: #f8f9fa; }
        .logo { max-height: 60px; }
      </style>
    </head>
    <body>
    <div class="container mt-5">
      <div class="card">
        <div class="card-header p-0" style="background-color:var(--header-gray);">
          <div class="row no-gutters align-items-center">
            <div class="col-6 p-3">
              <img src="/logo.png" class="logo" alt="Logo">
            </div>
            <div class="col-6 text-right p-3">
              {% if patient %}<p class="mb-1"><strong>Paciente:</strong> {{patient}}</p>{% endif %}
              <p class="mb-0"><strong>Orçamento:</strong> {{order}}</p>
            </div>
          </div>
        </div>
        <div class="card-body">
          {% for info in grouped.values() %}
            <div class="card mb-3">
              <div class="card-header" style="background-color:var(--section-gray);">
                Fórmula {{loop.index}}
              </div>
              <div class="card-body">
                <ul class="list-group mb-2">
                  {% for it in info['items'] %}
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                      {{it.descr}} <span>{{it.quant}} {{it.unida}}</span>
                    </li>
                  {% endfor %}
                </ul>
                <p><strong>Volume:</strong> {{info.volume}} {{info.univol}}</p>
                <p><strong>Total:</strong> R$ {{"%.2f"|format(info.total)}}</p>
              </div>
            </div>
          {% endfor %}
          <hr>
          <div class="d-flex justify-content-start mb-3">
            <a href="/?" class="btn btn-outline-primary mr-2">Nova consulta</a>
            <a href="/?nrorc={{order}}&filial={{request.args.get('filial')}}&format=pdf" class="btn btn-success">Download PDF</a>
          </div>
          <div class="text-right">
            <p class="mb-1"><strong>Data do Orçamento:</strong> {{dtentr_str}}</p>
            <p class="mb-3"><strong>Validade:</strong> {{validade_str}}</p>
          </div>
          <h5 class="text-right">Valor Total Geral: R$ {{"%.2f"|format(total_geral)}}</h5>
        </div>
      </div>
    </div>
    </body>
    </html>
    """
    return render_template_string(html,
        order=order, patient=patient,
        grouped=grouped,
        total_geral=total_geral,
        dtentr_str=dtentr_str,
        validade_str=validade_str
    )

# Geração de PDF
@app.route('/pdf', methods=['GET'])
def generate_pdf():
    nrorc = request.args.get('nrorc','').strip()
    filial = request.args.get('filial','1').strip()
    sql = (
        f"SELECT f10.NRORC,f10.SERIEO,f10.TPCMP,f10.DESCR,f10.QUANT,f10.UNIDA,"
        f"f00.VOLUME,f00.UNIVOL,f00.PRCOBR,f00.VRDSC,f00.NOMEPA,f00.DTENTR "
        f"FROM fc15110 f10 JOIN fc15100 f00 ON f10.NRORC=f00.NRORC AND f10.SERIEO=f00.SERIEO "
        f"WHERE f10.NRORC='{nrorc}' AND f10.cdfil='{filial}' AND f10.TPCMP IN ('C','H','F')"
    )
    order,patient,dtentr,grouped = load_grouped(sql)
    total_forms = len(grouped)
    total_geral = sum(g['total'] for g in grouped.values())
    validade = (dtentr + datetime.timedelta(days=7)) if dtentr else None

    pdf = PDF(format='A4')
    pdf.alias_nb_pages()
    pdf.order_number = order
    pdf.total_formulations = total_forms
    pdf.patient_name = patient
    pdf.set_auto_page_break(True,20)
    pdf.add_page()

    for idx,info in enumerate(grouped.values(),start=1):
        if pdf.get_y()+10>pdf.page_break_trigger: pdf.add_page()
        pdf.set_font('Arial','B',12)
        pdf.cell(0,8,f"Formulação {idx:02}",ln=True)
        pdf.set_font('Arial','',11)
        for it in info['items']:
            pdf.cell(100,6,it['descr'],border=0)
            pdf.cell(30,6,str(it['quant']),border=0,align='R')
            pdf.cell(30,6,it['unida'],border=0,ln=1,align='R')
        pdf.ln(2)
        pdf.cell(0,6,f"Total: R$ {info['total']:.2f}",ln=True,align='R')
        pdf.ln(4)

    pdf.set_font('Arial','B',12)
    pdf.cell(0,8,f"VALOR TOTAL GERAL: R$ {total_geral:.2f}",ln=True,align='R')
    pdf.set_font('Arial','',11)
    pdf.cell(0,6,f"Data: {dtentr.strftime('%d/%m/%Y') if dtentr else ''}",ln=True)
    if validade:
        pdf.cell(0,6,f"Validade: {validade.strftime('%d/%m/%Y')}",ln=True)

    out = pdf.output(dest='S')
    out_bytes = out.encode('latin-1') if isinstance(out,str) else out
    return send_file(io.BytesIO(out_bytes),
                     mimetype='application/pdf',
                     as_attachment=True,
                     download_name=f"ORCAMENTO_{order}.pdf")

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)))
