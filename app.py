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


@app.route('/', methods=['GET'])
def home():
    return "🚀 API Firebird está online!"


@app.route('/pdf', methods=['GET'])
def generate_pdf():
    sql = request.args.get('sql')
    if not sql:
        return jsonify({"error": "SQL query is required"}), 400
    if not sql.strip().lower().startswith("select"):
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

        # Organizar dados
        data_group = {}
        for row in rows:
            row_dict = dict(zip(columns, row))
            nrorc = row_dict.get('NRORC')
            serieo = row_dict.get('SERIEO')
            key = (nrorc, serieo)
            if key not in data_group:
                data_group[key] = {
                    "items": [],
                    "volume": row_dict.get('VOLUME'),
                    "univol": row_dict.get('UNIVOL'),
                    "prcobr": row_dict.get('PRCOBR')
                }
            data_group[key]['items'].append({
                "descr": row_dict.get('DESCR'),
                "quant": row_dict.get('QUANT'),
                "unida": row_dict.get('UNIDA')
            })

        formula_count = len(data_group)

        # Criar PDF
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Cabeçalho superior direito com nº de orçamento
        first_nrorc = list(data_group.keys())[0][0]
        pdf.set_font("Arial", '', 12)
        pdf.set_xy(160, 10)
        pdf.cell(40, 10, f"ORÇAMENTO: {first_nrorc}-{formula_count}", align='R')
        pdf.ln(10)

        total_geral = 0

        for idx, ((nrorc, serieo), details) in enumerate(data_group.items(), start=1):
            total_geral += float(details['prcobr'])

            # Título da Formulação
            pdf.set_fill_color(180, 180, 180)  # Cinza mais escuro
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, f"Formulação {idx:02}", ln=True, fill=True, align='C')

            pdf.ln(2)

            # Itens sem cabeçalho
            pdf.set_font("Arial", '', 12)
            for item in details['items']:
                descr = str(item['descr'])
                quant = str(item['quant'])
                unida = str(item['unida']).strip()

                # Descrição à esquerda, quantidade e unidade à direita
                line = f"{descr:<60} {quant} {unida}"
                pdf.cell(0, 8, line, ln=True, align='C')

            pdf.ln(2)

            # Rodapé da formulação: Volume e Total
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, 
                     f"Volume: {details['volume']} {details['univol']}".ljust(50) +
                     f"Total: R$ {details['prcobr']:.2f}".rjust(50), 
                     ln=True, align='C')

            pdf.ln(5)

        # Total Geral no final
        pdf.set_fill_color(200, 220, 255)
        pdf.set_font("Arial", 'B', 13)
        pdf.cell(0, 10, f"TOTAL GERAL DO ORÇAMENTO: R$ {total_geral:.2f}", ln=True, fill=True, align='C')

        # Gerar PDF
        pdf_bytes = pdf.output(dest='S')
        if isinstance(pdf_bytes, str):
            pdf_bytes = pdf_bytes.encode('latin-1')
        pdf_output = io.BytesIO(pdf_bytes)

        return send_file(
            pdf_output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='relatorio.pdf'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
