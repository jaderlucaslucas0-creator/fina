import os
from datetime import date
from decimal import Decimal
from flask import Flask, jsonify, request, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg

app = Flask(__name__, static_folder=".", static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "development-only-change-me")
DATABASE_URL = os.environ.get("DATABASE_URL")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS movements (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL CHECK (type IN ('entrada','saida')),
    category VARCHAR(100) NOT NULL,
    description TEXT,
    client TEXT,
    value NUMERIC(14,2) NOT NULL CHECK (value >= 0),
    status VARCHAR(20) NOT NULL CHECK (status IN ('recebido','pendente')),
    due_date DATE NOT NULL,
    installment INTEGER NOT NULL DEFAULT 1,
    total_installments INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_movements_user_date ON movements(user_id, due_date DESC);
"""

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL não configurada")
    return psycopg.connect(DATABASE_URL)

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
        conn.commit()

@app.before_request
def ensure_db():
    if DATABASE_URL:
        try:
            init_db()
        except Exception:
            pass

@app.get("/")
def home():
    return send_from_directory(".", "index.html")

@app.get("/api/health")
def health():
    try:
        init_db()
        return {"ok": True, "database": "online"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500

@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if len(username) < 3 or len(username) > 80:
        return {"error": "Usuário deve ter entre 3 e 80 caracteres."}, 400
    if len(password) < 6:
        return {"error": "A senha deve ter pelo menos 6 caracteres."}, 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users(username,password_hash) VALUES(%s,%s) RETURNING id",
                    (username, generate_password_hash(password))
                )
                user_id = cur.fetchone()[0]
            conn.commit()
        session.clear()
        session["user_id"] = user_id
        session["username"] = username
        return {"ok": True, "username": username}
    except psycopg.errors.UniqueViolation:
        return {"error": "Esse usuário já existe."}, 409

@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id,password_hash FROM users WHERE username=%s", (username,))
            row = cur.fetchone()
    if not row or not check_password_hash(row[1], password):
        return {"error": "Usuário ou senha inválidos."}, 401
    session.clear()
    session["user_id"] = row[0]
    session["username"] = username
    return {"ok": True, "username": username}

@app.post("/api/logout")
def logout():
    session.clear()
    return {"ok": True}

@app.get("/api/me")
def me():
    if not session.get("user_id"):
        return {"authenticated": False}
    return {"authenticated": True, "username": session["username"]}

@app.get("/api/movements")
def list_movements():
    if not session.get("user_id"):
        return {"error": "Não autenticado."}, 401
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT id,type,category,description,client,value,status,due_date,installment,total_installments
                           FROM movements WHERE user_id=%s ORDER BY due_date DESC,id DESC""",
                        (session["user_id"],))
            rows = cur.fetchall()
    return jsonify([
        {"id": r[0], "type": r[1], "cat": r[2], "desc": r[3] or "",
         "client": r[4] or "", "value": float(r[5]), "status": r[6],
         "date": r[7].isoformat(), "part": r[8], "totalParts": r[9]}
        for r in rows
    ])

@app.post("/api/movements")
def create_movement():
    if not session.get("user_id"):
        return {"error": "Não autenticado."}, 401
    data = request.get_json(silent=True) or {}
    try:
        total = Decimal(str(data.get("amount", "0")))
        parts = max(1, int(data.get("parts", 1)))
        first = date.fromisoformat(data["date"])
    except (ValueError, TypeError, KeyError):
        return {"error": "Dados inválidos."}, 400
    if total <= 0:
        return {"error": "Informe um valor maior que zero."}, 400
    if data.get("type") not in ("entrada", "saida"):
        return {"error": "Tipo inválido."}, 400
    each = (total / parts).quantize(Decimal("0.01"))
    values = [each] * (parts - 1) + [(total - each * (parts - 1)).quantize(Decimal("0.01"))]
    import calendar
    with get_db() as conn:
        with conn.cursor() as cur:
            for i, value in enumerate(values, 1):
                month_index = first.month - 1 + (i - 1)
                year = first.year + month_index // 12
                month = month_index % 12 + 1
                due = date(year, month, min(first.day, calendar.monthrange(year, month)[1]))
                cur.execute("""INSERT INTO movements
                    (user_id,type,category,description,client,value,status,due_date,installment,total_installments)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (session["user_id"], data["type"], data.get("cat","Outros"),
                     data.get("desc",""), data.get("client",""), value,
                     "pendente" if parts > 1 else data.get("status","pendente"),
                     due, i, parts))
        conn.commit()
    return {"ok": True}

@app.delete("/api/movements/<int:movement_id>")
def delete_movement(movement_id):
    if not session.get("user_id"):
        return {"error": "Não autenticado."}, 401
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM movements WHERE id=%s AND user_id=%s",
                        (movement_id, session["user_id"]))
        conn.commit()
    return {"ok": True}

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
