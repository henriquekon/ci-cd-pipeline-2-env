from flask import Flask, jsonify, request, session, send_file
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from functools import wraps
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import cm
import io
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'secret-key-ultra-top-secret'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

CORS(app, supports_credentials=True)
x = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'postgres'),
    'port': 5432,
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', 'postgres'),
    'database': os.environ.get('DB_NAME', 'receitas')
}

EMAIL_CONFIG = {
    'host': os.environ.get('MAIL_HOST', 'sandbox.smtp.mailtrap.io'),
    'port': int(os.environ.get('MAIL_PORT', 2525)),
    'user': os.environ.get('MAIL_USER', 'your_mailtrap_user'),
    'password': os.environ.get('MAIL_PASS', 'your_mailtrap_password'),
    'from': os.environ.get('MAIL_FROM', 'receitas@app.com'),
    'to': os.environ.get('MAIL_TO', 'admin@app.com'),
}


def get_db():
    return psycopg2.connect(**DB_CONFIG)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Login necessário'}), 401
        return f(*args, **kwargs)
    return decorated_function


def send_email(subject, body, to_email=None):
    try:
        recipient = to_email or EMAIL_CONFIG['to']
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_CONFIG['from']
        msg['To'] = recipient
        msg.attach(MIMEText(body, 'html'))

        server = smtplib.SMTP(EMAIL_CONFIG['host'], EMAIL_CONFIG['port'])
        server.starttls()
        server.login(EMAIL_CONFIG['user'], EMAIL_CONFIG['password'])
        server.sendmail(EMAIL_CONFIG['from'], recipient, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False


def build_email_body(action, receita):
    action_label = 'criada' if action == 'create' else 'atualizada'
    color = '#28a745' if action == 'create' else '#ffc107'
    tipo_color = '#c41e1e' if receita['tipo_receita'] == 'doce' else '#2e7d32'
    return f"""
    <html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px;">
      <div style="max-width:500px;margin:auto;background:white;
      border-radius:10px;padding:30px;box-shadow:0 2px 8px rgba(0,0,0,.1)">
        <h2 style="color:{color}">Receita {action_label}!</h2>
        <table style="width:100%;border-collapse:collapse;margin-top:15px">
          <tr><td style="padding:8px;color:#666;font-weight:bold">Nome</td>
              <td style="padding:8px">{receita['nome']}</td></tr>
          <tr style="background:#f9f9f9"><td style="padding:8px;color:#666;font-weight:bold">Descrição</td>
              <td style="padding:8px">{receita['descricao']}</td></tr>
          <tr><td style="padding:8px;color:#666;font-weight:bold">Custo</td>
              <td style="padding:8px;color:#2e7d32;font-weight:bold">R$ {float(receita['custo']):.2f}</td></tr>
          <tr style="background:#f9f9f9"><td style="padding:8px;color:#666;font-weight:bold">Tipo</td>
              <td style="padding:8px;color:{tipo_color};font-weight:bold">{receita['tipo_receita'].upper()}</td></tr>
        </table>
        <p style="color:#999;font-size:12px;margin-top:20px">
          Evento registrado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}
        </p>
      </div>
    </body></html>
    """


@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    login_val = data.get('login')
    senha = data.get('senha')

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM usuario WHERE login = %s AND senha = %s", (login_val, senha))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user:
        session['user_id'] = user['id']
        session['user_name'] = user['nome']
        session['user_email'] = user['email'] or EMAIL_CONFIG['to']
        return jsonify({'success': True, 'user': user['nome']})
    return jsonify({'success': False, 'error': 'Credenciais inválidas'}), 401


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/api/receitas', methods=['GET'])
@login_required
def get_receitas():
    tipo = request.args.get('tipo')
    nome = request.args.get('nome')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query = "SELECT * FROM receita WHERE 1=1"
    params = []

    if nome:
        query += " AND nome ILIKE %s"
        params.append(f'%{nome}%')

    if tipo and tipo in ('doce', 'salgada'):
        query += " AND tipo_receita = %s"
        params.append(tipo)

    if data_inicio:
        query += " AND data_registro >= %s"
        params.append(data_inicio)

    if data_fim:
        query += " AND data_registro <= %s"
        params.append(data_fim + ' 23:59:59')

    query += " ORDER BY data_registro DESC"

    cur.execute(query, params)
    receitas = []
    for row in cur.fetchall():
        r = dict(row)
        r['custo'] = float(r['custo'])
        r['data_registro'] = r['data_registro'].strftime('%Y-%m-%dT%H:%M:%S') if r['data_registro'] else None
        receitas.append(r)
    cur.close()
    conn.close()
    return jsonify(receitas)


@app.route('/api/receitas/<string:nome>', methods=['GET'])
@login_required
def get_receita_nome(nome):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM receita WHERE nome ILIKE %s", (f'%{nome}%',))
    receitas = cur.fetchall()
    cur.close()
    conn.close()

    if receitas:
        result = []
        for r in receitas:
            rd = dict(r)
            rd['custo'] = float(rd['custo'])
            rd['data_registro'] = rd['data_registro'].strftime('%Y-%m-%dT%H:%M:%S') if rd['data_registro'] else None
            result.append(rd)
        return jsonify(result)
    return jsonify({'error': 'Nenhuma receita encontrada'}), 404


@app.route('/api/receitas/<int:id>', methods=['GET'])
@login_required
def get_receita(id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM receita WHERE id = %s", (id,))
    receita = cur.fetchone()
    cur.close()
    conn.close()

    if receita:
        r = dict(receita)
        r['custo'] = float(r['custo'])
        r['data_registro'] = r['data_registro'].strftime('%Y-%m-%dT%H:%M:%S') if r['data_registro'] else None
        return jsonify(r)
    return jsonify({'error': 'Receita não encontrada'}), 404


@app.route('/api/receitas', methods=['POST'])
@login_required
def create_receita():
    data = request.json
    nome = data.get('nome')
    descricao = data.get('descricao')
    custo = data.get('custo')
    tipo_receita = data.get('tipo_receita')

    if not all([nome, descricao, custo, tipo_receita]):
        return jsonify({'error': 'Todos os campos são obrigatórios'}), 400

    if tipo_receita not in ('doce', 'salgada'):
        return jsonify({'error': 'Tipo deve ser "doce" ou "salgada"'}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s) RETURNING *",
        (nome, descricao, custo, tipo_receita)
    )
    new_receita = dict(cur.fetchone())
    new_receita['custo'] = float(new_receita['custo'])
    conn.commit()
    cur.close()
    conn.close()

    subject = f"[Receitas] Nova receita criada: {nome}"
    send_email(subject, build_email_body('create', new_receita), to_email=session.get('user_email'))

    return jsonify({'success': True, 'id': new_receita['id']}), 201


@app.route('/api/receitas/<int:id>', methods=['PUT'])
@login_required
def update_receita(id):
    data = request.json
    nome = data.get('nome')
    descricao = data.get('descricao')
    custo = data.get('custo')
    tipo_receita = data.get('tipo_receita')

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT * FROM receita WHERE id = %s", (id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({'error': 'Receita não encontrada'}), 404

    cur.execute(
        "UPDATE receita SET nome=%s, descricao=%s, custo=%s, tipo_receita=%s WHERE id=%s RETURNING *",
        (nome, descricao, custo, tipo_receita, id)
    )
    updated = dict(cur.fetchone())
    updated['custo'] = float(updated['custo'])
    conn.commit()
    cur.close()
    conn.close()

    subject = f"[Receitas] Receita atualizada: {nome}"
    send_email(subject, build_email_body('update', updated), to_email=session.get('user_email'))

    return jsonify({'success': True})


@app.route('/api/receitas/<int:id>', methods=['DELETE'])
@login_required
def delete_receita(id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT * FROM receita WHERE id = %s", (id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({'error': 'Receita não encontrada'}), 404

    cur.execute("DELETE FROM receita WHERE id = %s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/receitas/<int:id>/pdf', methods=['GET'])
@login_required
def export_receita_pdf(id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM receita WHERE id = %s", (id,))
    receita = cur.fetchone()
    cur.close()
    conn.close()

    if not receita:
        return jsonify({'error': 'Receita não encontrada'}), 404

    r = dict(receita)
    r['custo'] = float(r['custo'])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Title'],
                                 fontSize=24, textColor=colors.HexColor('#667eea'),
                                 spaceAfter=10)
    label_style = ParagraphStyle('Label', parent=styles['Normal'],
                                 fontSize=10, textColor=colors.grey)
    desc_style = ParagraphStyle('Desc', parent=styles['Normal'],
                                fontSize=12, leading=18, spaceAfter=10)

    tipo_color = colors.HexColor('#c41e1e') if r['tipo_receita'] == 'doce' else colors.HexColor('#2e7d32')
    data_fmt = r['data_registro'].strftime('%d/%m/%Y às %H:%M') if r['data_registro'] else '-'

    elements = [
        Paragraph(r['nome'], title_style),
        Spacer(1, 0.3*cm),
    ]

    table_data = [
        [Paragraph('<b>Tipo</b>', styles['Normal']),
         Paragraph(r['tipo_receita'].upper(), ParagraphStyle('tipo', parent=styles['Normal'],
        textColor=tipo_color, fontSize=12))],
        [Paragraph('<b>Custo</b>', styles['Normal']),
         Paragraph(f"R$ {r['custo']:.2f}", ParagraphStyle('custo', parent=styles['Normal'],
         textColor=colors.HexColor('#2e7d32'),
         fontSize=13, fontName='Helvetica-Bold'))],
        [Paragraph('<b>Data de Registro</b>', styles['Normal']),
         Paragraph(data_fmt, styles['Normal'])],
    ]
    t = Table(table_data, colWidths=[5*cm, 12*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#f9f9f9'), colors.white]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))

    elements.append(t)
    elements.append(Spacer(1, 0.6*cm))
    elements.append(Paragraph('<b>Descrição</b>', label_style))
    elements.append(Spacer(1, 0.2*cm))
    elements.append(Paragraph(r['descricao'], desc_style))
    elements.append(Spacer(1, 1*cm))

    # Footer
    footer = Paragraph(
        f"<font size='9' color='grey'>Gerado em "
        f"{datetime.now().strftime('%d/%m/%Y às %H:%M')} · Sistema de Receitas</font>",
        styles['Normal']
    )
    elements.append(footer)

    doc.build(elements)
    buffer.seek(0)

    filename = f"receita_{id}_{r['nome'].replace(' ', '_')}.pdf"
    return send_file(buffer, mimetype='application/pdf',
                     as_attachment=True, download_name=filename)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
