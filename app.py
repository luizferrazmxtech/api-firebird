from flask import Flask, request, jsonify, send_file, Response
import fdb
import os
from fpdf import FPDF
import io
from datetime import datetime

app = Flask(__name__)

# Configuração do banco
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_DATABASE"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", 3050)),
    "charset": "UTF8"
}

API_TOKEN = os.getenv("API_TOKEN", "seu_token_aqui")

# Caminho do logo
LOGO_PATH = "https://mxtech.inf.br/images/router_notifications/link_up_image.jpg"  # Coloque logo na mesma pasta do app ou use uma URL pública


@app.before_request
def check_auth():
    token = request.headers.get('Authorization')
    if token != f"Bearer {API_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401


@app.route('/', methods=['GET'])
def home():
    return "🚀 API Firebird está online!"


def executar_query(sql):
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
    results = cur.fetchall()

    con.close()

    return columns, results


# ✅ Endpoint JSON
@app.route('/query', methods=['GET'])
def run_query():
    sql = request.args.get('sql')
    if not sql:
        return jsonify({"error": "SQL query is required"}), 400
    if not sql.strip().lower().startswith("select"):
        return jsonify({"error": "Only SELECT queries are allowed"}), 400

    try:
        columns, results = executar_query(sql)
        data = [dict(zip(columns, row)) for row in results]
        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ✅ Endpoint PDF com logo + rodapé
@app.route('/pdf', methods=['GET'])
def generate_pdf():
    sql = request.args.get('sql')
    if not sql:
        return jsonify({"error": "SQL query is required"}), 400
    if not sql.strip().lower().startswith("select"):
        return jsonify({"error": "Only SELECT queries are allowed"}), 400

    try:
        columns, results = executar_query(sql)

        class PDF(FPDF):
            def header(self):
                if os.path.exists(LOGO_PATH):
                    self.image(LOGO_PATH, 10, 8, 33)
                self.set_font('Arial', 'B', 15)
                self.cell(0, 10, 'Relatório de Consulta Firebird', border=False, ln=True, align='C')
                self.ln(5)

            def footer(self):
                self.set_y(-15)
                self.set_font('Arial', 'I', 8)
                date_str = datetime.now().strftime('%d/%m/%Y %H:%M')
                self.cell(0, 10, f'Gerado em {date_str} - Página {self.page_no()}', align='C')

        pdf = PDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Cabeçalho da tabela
        pdf.set_font("Arial", 'B', 10)
        col_width = max(277 / len(columns), 30)

        for col in columns:
            pdf.cell(col_width, 10, str(col), border=1, align='C')
        pdf.ln()

        # Dados da tabela
        pdf.set_font("Arial", '', 9)
        for row in results:
            for item in row:
                text = str(item) if item is not None else ''
                pdf.cell(col_width, 8, text, border=1, align='C')
            pdf.ln()

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


# ✅ Endpoint HTML estilizado
@app.route('/html', methods=['GET'])
def generate_html():
    sql = request.args.get('sql')
    if not sql:
        return jsonify({"error": "SQL query is required"}), 400
    if not sql.strip().lower().startswith("select"):
        return jsonify({"error": "Only SELECT queries are allowed"}), 400

    try:
        columns, results = executar_query(sql)

        # Criar HTML com CSS bonito
        html = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <title>Relatório de Consulta</title>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; }}
                h1 {{ text-align: center; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ border: 1px solid #ccc; padding: 8px; text-align: center; }}
                th {{ background-color: #007BFF; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                img.logo {{ display: block; margin: auto; width: 150px; }}
            </style>
        </head>
        <body>
        """

        if os.path.exists(LOGO_PATH):
            html += f'<img src="data:image/png;base64,{encode_image_base64(LOGO_PATH)}" class="logo"/>'

        html += "<h1>Relatório de Consulta Firebird</h1>"
        html += "<table><tr>"
        for col in columns:
            html += f"<th>{col}</th>"
        html += "</tr>"

        for row in results:
            html += "<tr>"
            for item in row:
                html += f"<td>{item if item is not None else ''}</td>"
            html += "</tr>"

        html += "</table></body></html>"

        return Response(html, mimetype='text/html')

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Função auxiliar para embutir imagem no HTML
def encode_image_base64(image_path):
    import base64
    with open(image_path, 'rb') as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
