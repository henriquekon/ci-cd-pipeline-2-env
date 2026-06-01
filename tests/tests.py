import json
import os
import sys
import time
import pytest
import psycopg2
import psycopg2.extras
import requests
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

# Banco

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', 5432)),
    'user': os.environ.get('DB_USER', 'receitas'),
    'password': os.environ.get('DB_PASSWORD', 'postgres_ci'),
    'database': os.environ.get('DB_NAME', 'receitas_test'),
}

MAILTRAP_API_TOKEN = os.environ.get('MAILTRAP_API_TOKEN', '')
MAILTRAP_INBOX_ID = os.environ.get('MAILTRAP_INBOX_ID', '')

# Em testes, vou utilizar mailtrap (pois gmail dificulta esse tipo de envio, e mailtrap apresenta um ambiente já pronto para isso).
# Obs: a ideia é funcionar exatamente igual, a única coisa que vai mudar são as credenciais específicas. Qualquer erro que ocorre
# nos testes e não em production, e vice-versa, provavelmente demonstrará erro na api do gmail/mailtrap em específico.

EMAIL_CONFIG = {
    'host': os.environ.get('MAIL_HOST', 'sandbox.smtp.mailtrap.io'),
    'port': int(os.environ.get('MAIL_PORT', 2525)),
    'user': os.environ.get('MAILTRAP_USER', ''),
    'password': os.environ.get('MAILTRAP_PASS', ''),
    'from': os.environ.get('MAIL_FROM', 'test@receitas.com'),
    'to': os.environ.get('MAIL_TO', 'test@receitas.com'),
}


def get_test_db():
    return psycopg2.connect(**DB_CONFIG)


def clean_test_db():
    conn = get_test_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM receita WHERE nome LIKE 'TESTE_%'") # deleta todas receitas criadas aqui
    conn.commit()
    cur.close()
    conn.close()


# Fixtures:

@pytest.fixture(scope="session")
def app_module():
    with patch("psycopg2.connect"), patch("smtplib.SMTP"):
        import importlib
        import app as _app
        importlib.reload(_app)
        return _app


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    clean_test_db()
    yield
    clean_test_db()


@pytest.fixture
def client(app_module):
    app_module.app.config["TESTING"] = True
    app_module.app.config["SECRET_KEY"] = "test-secret"
    app_module.EMAIL_CONFIG.update(EMAIL_CONFIG)
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture
def logged_client(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "Test User"
    return client


def _mock_row(data: dict):
    row = MagicMock()
    row.keys.return_value = list(data.keys())
    row.__getitem__ = lambda self, k: data[k]
    row.__iter__ = lambda self: iter(data)
    return row


# Testes de autenticação (api):
class TestAuth:

    # 1 - login com credenciais corretas
    def test_login_success(self, client, app_module):
        user_data = {"id": 1, "nome": "Admin", "login": "admin", "senha": "admin123", "situacao": "ativo"}
        with patch.object(app_module, "get_db") as mock_db:
            conn = MagicMock()
            cur = MagicMock()
            cur.fetchone.return_value = _mock_row(user_data)
            conn.cursor.return_value = cur
            mock_db.return_value = conn
            resp = client.post("/api/login",
                               data=json.dumps({"login": "admin", "senha": "admin123"}),
                               content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    # 2 - login com credenciais incorretas
    def test_login_failure(self, client, app_module):
        with patch.object(app_module, "get_db") as mock_db:
            conn = MagicMock()
            cur = MagicMock()
            cur.fetchone.return_value = None
            conn.cursor.return_value = cur
            mock_db.return_value = conn
            resp = client.post("/api/login",
                               data=json.dumps({"login": "wrong", "senha": "wrong"}),
                               content_type="application/json")
        assert resp.status_code == 401
        assert resp.get_json()["success"] is False

    # 3 - logout
    def test_logout(self, logged_client):
        resp = logged_client.post("/api/logout")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    # 4 - rota protegida exige login
    def test_protected_route_requires_login(self, client):
        resp = client.get("/api/receitas")
        assert resp.status_code == 401
        assert "Login necessário" in resp.get_json()["error"]


# Testes com banco (feito upgrade para ser banco "real", sem mock de conexão igual era feito anteriormente)
# O banco utilizado, porém, não é o mesmo da produção/staging, PORÉM, utiliza o mesmo serviço e apresenta a mesma estrutura 
# (somente dados mudarão, por ser outra branch)
class TestBancoReal:

    # 5 - inserir receita no banco e verificar que foi salva
    def test_inserir_e_buscar_receita(self):
        conn = get_test_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s) RETURNING id",
            ("TESTE_Bolo", "Bolo de teste", 10.00, "doce")
        )
        receita_id = cur.fetchone()["id"]
        conn.commit()

        cur.execute("SELECT * FROM receita WHERE id = %s", (receita_id,))
        receita = cur.fetchone()
        assert receita is not None
        assert receita["nome"] == "TESTE_Bolo"
        assert float(receita["custo"]) == 10.00
        assert receita["tipo_receita"] == "doce"

        cur.execute("DELETE FROM receita WHERE id = %s", (receita_id,))
        conn.commit()
        cur.close()
        conn.close()

    # 6 - data_registro é preenchida automaticamente pelo banco
    def test_data_registro_automatica(self):
        conn = get_test_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s) RETURNING id",
            ("TESTE_DataAuto", "Teste data automática", 10.00, "doce")
        )
        receita_id = cur.fetchone()["id"]
        conn.commit()
 
        cur.execute("SELECT data_registro FROM receita WHERE id = %s", (receita_id,))
        data_registro = cur.fetchone()["data_registro"]
        assert data_registro is not None
 
        cur.execute("DELETE FROM receita WHERE id = %s", (receita_id,))
        conn.commit()
        cur.close()
        conn.close()


    # 7 - buscar receita inexistente retorna None
    def test_buscar_receita_inexistente(self):
        conn = get_test_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM receita WHERE id = %s", (999999,))
        receita = cur.fetchone()
        assert receita is None
        cur.close()
        conn.close()

    # 8 - atualizar receita no banco e verificar mudança
    def test_atualizar_receita(self):
        conn = get_test_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s) RETURNING id",
            ("TESTE_Pizza", "Pizza de teste", 30.00, "salgada")
        )
        receita_id = cur.fetchone()["id"]
        conn.commit()

        cur.execute(
            "UPDATE receita SET custo = %s WHERE id = %s",
            (45.00, receita_id)
        )
        conn.commit()

        cur.execute("SELECT custo FROM receita WHERE id = %s", (receita_id,))
        assert float(cur.fetchone()["custo"]) == 45.00

        cur.execute("DELETE FROM receita WHERE id = %s", (receita_id,))
        conn.commit()
        cur.close()
        conn.close()

    # 9 - deletar receita e verificar que sumiu
    def test_deletar_receita(self):
        conn = get_test_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s) RETURNING id",
            ("TESTE_Coxinha", "Coxinha de teste", 5.00, "salgada")
        )
        receita_id = cur.fetchone()["id"]
        conn.commit()

        cur.execute("DELETE FROM receita WHERE id = %s", (receita_id,))
        conn.commit()

        cur.execute("SELECT * FROM receita WHERE id = %s", (receita_id,))
        assert cur.fetchone() is None
        cur.close()
        conn.close()

    # 10 - filtro por tipo retorna só receitas do tipo correto
    def test_filtro_por_tipo(self):
        conn = get_test_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s)",
            ("TESTE_Pudim", "Pudim de teste", 12.00, "doce")
        )
        cur.execute(
            "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s)",
            ("TESTE_Lasanha", "Lasanha de teste", 40.00, "salgada")
        )
        conn.commit()

        cur.execute("SELECT * FROM receita WHERE nome LIKE 'TESTE_%' AND tipo_receita = 'doce'")
        doces = cur.fetchall()
        assert all(r["tipo_receita"] == "doce" for r in doces)

        cur.execute("DELETE FROM receita WHERE nome LIKE 'TESTE_%'")
        conn.commit()
        cur.close()
        conn.close()

    # 11 - filtro por nome
    def test_filtro_por_nome(self):
        conn = get_test_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s)",
            ("TESTE_Mousse", "Mousse de teste", 15.00, "doce")
        )
        conn.commit()

        cur.execute("SELECT * FROM receita WHERE nome ILIKE %s", ("%TESTE_Mousse%",))
        resultado = cur.fetchall()
        assert len(resultado) >= 1
        assert any("TESTE_Mousse" in r["nome"] for r in resultado)

        cur.execute("DELETE FROM receita WHERE nome LIKE 'TESTE_%'")
        conn.commit()
        cur.close()
        conn.close()

    # 12 - filtro por intervalo de datas retorna somente receitas no período
    def test_filtro_por_data(self):
        conn = get_test_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s) RETURNING id",
            ("TESTE_DataFiltro", "Receita para filtro de data", 20.00, "doce")
        )
        receita_id = cur.fetchone()["id"]
        conn.commit()
 
        cur.execute(
            "SELECT * FROM receita WHERE nome LIKE 'TESTE_%' AND data_registro >= NOW() - INTERVAL '1 minute'"
        )
        resultado = cur.fetchall()
        assert len(resultado) >= 1
 
        cur.execute("DELETE FROM receita WHERE id = %s", (receita_id,))
        conn.commit()
        cur.close()
        conn.close()

    # 13 - nome duplicado: erro
    def test_nome_duplicado_falha(self):
        conn = get_test_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s)",
            ("TESTE_Unico", "Receita única", 20.00, "doce")
        )
        conn.commit()

        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s)",
                ("TESTE_Unico", "Duplicada", 20.00, "doce")
            )
            conn.commit()

        conn.rollback()
        cur.execute("DELETE FROM receita WHERE nome = 'TESTE_Unico'")
        conn.commit()
        cur.close()
        conn.close()

    # 14 - tipo inválido: erro
    def test_tipo_invalido_falha_no_banco(self):
        conn = get_test_db()
        cur = conn.cursor()
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s)",
                ("TESTE_Invalido", "Desc", 10.00, "invalido")
            )
            conn.commit()
        conn.rollback()
        cur.close()
        conn.close()


# Teste de e-mail (atualmente, mailtrap. Pode ser configurado para utilizar outro serviço).
# Dessa vez, assim como banco, fiz upgrade para testar com serviço real, sem mock.
class TestEmailReal:

    def _limpar_inbox(self):
        if not MAILTRAP_API_TOKEN:
            return
        requests.patch(
            f"https://mailtrap.io/api/v1/inboxes/{MAILTRAP_INBOX_ID}/clean",
            headers={"Api-Token": MAILTRAP_API_TOKEN}
        )

    def _buscar_emails(self):
        if not MAILTRAP_API_TOKEN:
            return []
        resp = requests.get(
            f"https://mailtrap.io/api/v1/inboxes/{MAILTRAP_INBOX_ID}/messages",
            headers={"Api-Token": MAILTRAP_API_TOKEN}
        )
        return resp.json() if resp.status_code == 200 else []

    # 15 - e-mail ao criar receita 
    def test_email_enviado_ao_criar(self, app_module):
        self._limpar_inbox()
        time.sleep(1)

        app_module.EMAIL_CONFIG.update(EMAIL_CONFIG)
        receita = {
            "nome": "TESTE_EmailCreate",
            "descricao": "Teste de envio",
            "custo": 10.0,
            "tipo_receita": "doce"
        }
        subject = f"[Receitas] Nova receita criada: {receita['nome']}"
        result = app_module.send_email(subject, app_module.build_email_body("create", receita))
        assert result is True

        time.sleep(5)
        emails = self._buscar_emails()
        subjects = [e.get("subject", "") for e in emails]
        assert any("TESTE_EmailCreate" in s for s in subjects)

    # 16 - e-mail ao atualizar receita
    def test_email_enviado_ao_atualizar(self, app_module):
        time.sleep(5)
        self._limpar_inbox()

        app_module.EMAIL_CONFIG.update(EMAIL_CONFIG)
        receita = {
            "nome": "TESTE_EmailUpdate",
            "descricao": "Teste de atualização",
            "custo": 20.0,
            "tipo_receita": "salgada"
        }
        subject = f"[Receitas] Receita atualizada: {receita['nome']}"
        result = app_module.send_email(subject, app_module.build_email_body("update", receita))
        assert result is True

        time.sleep(5)
        emails = self._buscar_emails()
        subjects = [e.get("subject", "") for e in emails]
        assert any("TESTE_EmailUpdate" in s for s in subjects)


# Teste de PDF
# Mais um upgrade para verificar, de fato, se PDF foi gerado. Sem simples mock
class TestPdfReal:

    # 17 - PDF gerado válido
    def test_pdf_bytes_validos(self, logged_client, app_module):
        conn = get_test_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "INSERT INTO receita (nome, descricao, custo, tipo_receita) VALUES (%s, %s, %s, %s) RETURNING id",
            ("TESTE_PDF", "Receita para PDF", 25.00, "doce")
        )
        receita_id = cur.fetchone()["id"]
        conn.commit()
        cur.close()
        conn.close()

        with patch.object(app_module, "get_db") as mock_db:
            conn_mock = MagicMock()
            cur_mock = MagicMock()
            cur_mock.fetchone.return_value = _mock_row({
                "id": receita_id,
                "nome": "TESTE_PDF",
                "descricao": "Receita para PDF",
                "custo": 25.00,
                "tipo_receita": "doce",
                "data_registro": MagicMock(strftime=lambda f: "2026-01-01T00:00:00"),
            })
            conn_mock.cursor.return_value = cur_mock
            mock_db.return_value = conn_mock

            resp = logged_client.get(f"/api/receitas/{receita_id}/pdf")

        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        pdf_bytes = resp.data
        assert len(pdf_bytes) > 1000
        assert pdf_bytes[:4] == b'%PDF'

        conn = get_test_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM receita WHERE id = %s", (receita_id,))
        conn.commit()
        cur.close()
        conn.close()

    # 18 - PDF de receita inexistente: 404
    def test_pdf_nao_encontrado(self, logged_client, app_module):
        with patch.object(app_module, "get_db") as mock_db:
            conn = MagicMock()
            cur = MagicMock()
            cur.fetchone.return_value = None
            conn.cursor.return_value = cur
            mock_db.return_value = conn
            resp = logged_client.get("/api/receitas/999999/pdf")
        assert resp.status_code == 404


# Testes de apis
class TestApiValidacoes:

    # 19 - campos obrigatórios ausentes: 400
    def test_criar_sem_campos_obrigatorios(self, logged_client):
        resp = logged_client.post("/api/receitas",
                                  data=json.dumps({"nome": "Bolo"}),
                                  content_type="application/json")
        assert resp.status_code == 400
        assert "obrigatórios" in resp.get_json()["error"]

    # 20 - tipo inválido: 400
    def test_criar_tipo_invalido(self, logged_client):
        resp = logged_client.post("/api/receitas",
                                  data=json.dumps({"nome": "X", "descricao": "Y",
                                                   "custo": 10, "tipo_receita": "invalido"}),
                                  content_type="application/json")
        assert resp.status_code == 400
        assert "Tipo" in resp.get_json()["error"]

    # 21 - atualizar receita inexistente: 404
    def test_atualizar_inexistente(self, logged_client, app_module):
        with patch.object(app_module, "get_db") as mock_db:
            conn = MagicMock()
            cur = MagicMock()
            cur.fetchone.return_value = None
            conn.cursor.return_value = cur
            mock_db.return_value = conn
            resp = logged_client.put("/api/receitas/999999",
                                     data=json.dumps({"nome": "X", "descricao": "Y",
                                                      "custo": 10, "tipo_receita": "doce"}),
                                     content_type="application/json")
        assert resp.status_code == 404

    # 22 - deletar receita inexistente: 404
    def test_deletar_inexistente(self, logged_client, app_module):
        with patch.object(app_module, "get_db") as mock_db:
            conn = MagicMock()
            cur = MagicMock()
            cur.fetchone.return_value = None
            conn.cursor.return_value = cur
            mock_db.return_value = conn
            resp = logged_client.delete("/api/receitas/999999")
        assert resp.status_code == 404