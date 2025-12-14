

from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import os
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = "construar-local"

# =========================
# DB: Render (Postgres) o local (SQLite)
# =========================
db_url = os.environ.get("DATABASE_URL")
if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(app.instance_path, "construar.db")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# =========================
# MODELOS
# =========================
class Obra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    ubicacion = db.Column(db.String(200), nullable=True)
    cliente = db.Column(db.String(120), nullable=True)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

class PartidaPresupuesto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"), nullable=False)
    obra = db.relationship("Obra", backref=db.backref("partidas_presupuesto", lazy=True))

    partida = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.String(250), nullable=False)
    unidad = db.Column(db.String(30), nullable=True)
    cantidad = db.Column(db.Float, default=0.0)
    precio_unitario = db.Column(db.Float, default=0.0)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

class Gasto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"), nullable=False)
    obra = db.relationship("Obra", backref=db.backref("gastos", lazy=True))

    fecha = db.Column(db.Date, nullable=False, default=date.today)  # gasto por día
    concepto = db.Column(db.String(250), nullable=False)
    monto = db.Column(db.Float, nullable=False, default=0.0)

    # FOTO (ticket/nota) guardada en DB
    foto_nombre = db.Column(db.String(200), nullable=True)
    foto_mime = db.Column(db.String(80), nullable=True)
    foto_bytes = db.Column(db.LargeBinary, nullable=True)

    creado = db.Column(db.DateTime, default=datetime.utcnow)

def ensure_gasto_photo_columns():
    """Agrega columnas de foto si no existen (para nube/local) sin migraciones."""
    dialect = db.engine.dialect.name  # 'postgresql' o 'sqlite'
    if dialect == "postgresql":
        stmts = [
            "ALTER TABLE gasto ADD COLUMN IF NOT EXISTS foto_nombre VARCHAR(200);",
            "ALTER TABLE gasto ADD COLUMN IF NOT EXISTS foto_mime VARCHAR(80);",
            "ALTER TABLE gasto ADD COLUMN IF NOT EXISTS foto_bytes BYTEA;",
        ]
        for s in stmts:
            db.session.execute(text(s))
        db.session.commit()
    else:
        # sqlite: no soporta IF NOT EXISTS en todas las versiones; se intenta y se ignora si falla
        stmts = [
            "ALTER TABLE gasto ADD COLUMN foto_nombre TEXT;",
            "ALTER TABLE gasto ADD COLUMN foto_mime TEXT;",
            "ALTER TABLE gasto ADD COLUMN foto_bytes BLOB;",
        ]
        for s in stmts:
            try:
                db.session.execute(text(s))
                db.session.commit()
            except Exception:
                db.session.rollback()

with app.app_context():
    os.makedirs(app.instance_path, exist_ok=True)
    db.create_all()
    ensure_gasto_photo_columns()

# =========================
# RUTAS
# =========================
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/obras")
def obras():
    lista = Obra.query.order_by(Obra.creado.desc()).all()
    return render_template("obras.html", obras=lista)

@app.route("/obras/nueva", methods=["GET", "POST"])
def nueva_obra():
    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        ubicacion = (request.form.get("ubicacion") or "").strip()
        cliente = (request.form.get("cliente") or "").strip()

        if not nombre:
            flash("Falta el nombre de la obra.", "error")
            return redirect(url_for("nueva_obra"))

        o = Obra(nombre=nombre, ubicacion=ubicacion or None, cliente=cliente or None)
        db.session.add(o)
        db.session.commit()
        flash("Obra creada correctamente ✅", "ok")
        return redirect(url_for("obras"))

    return render_template("nueva_obra.html")

@app.route("/presupuesto")
def presupuesto():
    obras_lista = Obra.query.order_by(Obra.creado.desc()).all()
    return render_template("presupuesto.html", obras=obras_lista)

# =========================
# FOTO: servir imagen del gasto
# =========================
@app.route("/gastos/<int:gasto_id>/foto")
def gasto_foto(gasto_id):
    g = Gasto.query.get_or_404(gasto_id)
    if not g.foto_bytes or not g.foto_mime:
        return ("", 404)
    return Response(g.foto_bytes, mimetype=g.foto_mime)

# =========================
# GASTOS POR DÍA + FOTO
# =========================
@app.route("/gastos", methods=["GET", "POST"])
def gastos():
    obras_lista = Obra.query.order_by(Obra.creado.desc()).all()

    fecha_str = request.args.get("fecha") or date.today().isoformat()
    try:
        fecha_sel = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        fecha_sel = date.today()

    obra_id_q = request.args.get("obra_id")
    obra_id_sel = int(obra_id_q) if obra_id_q and obra_id_q.isdigit() else None

    if request.method == "POST":
        obra_id = request.form.get("obra_id")
        concepto = (request.form.get("concepto") or "").strip()
        monto_raw = (request.form.get("monto") or "").strip()
        fecha_post = request.form.get("fecha") or date.today().isoformat()

        try:
            f = datetime.strptime(fecha_post, "%Y-%m-%d").date()
        except ValueError:
            f = date.today()

        if not obra_id or not obra_id.isdigit():
            flash("Selecciona una obra.", "error")
            return redirect(url_for("gastos", fecha=f.isoformat()))

        try:
            monto = float(monto_raw.replace(",", ""))
        except ValueError:
            monto = -1

        if not concepto:
            flash("Escribe el concepto del gasto.", "error")
            return redirect(url_for("gastos", obra_id=obra_id, fecha=f.isoformat()))

        if monto <= 0:
            flash("El monto debe ser mayor a 0.", "error")
            return redirect(url_for("gastos", obra_id=obra_id, fecha=f.isoformat()))

        # FOTO (opcional)
        foto = request.files.get("foto")
        foto_nombre = None
        foto_mime = None
        foto_bytes = None

        if foto and foto.filename:
            # Validación básica: solo imágenes
            foto_mime = (foto.mimetype or "").lower()
            if not foto_mime.startswith("image/"):
                flash("La foto debe ser una imagen (JPG/PNG/HEIC, etc).", "error")
                return redirect(url_for("gastos", obra_id=obra_id, fecha=f.isoformat()))

            # Límite (3 MB)
            raw = foto.read()
            if len(raw) > 3 * 1024 * 1024:
                flash("La foto pesa mucho. Máximo 3 MB.", "error")
                return redirect(url_for("gastos", obra_id=obra_id, fecha=f.isoformat()))

            foto_nombre = foto.filename
            foto_bytes = raw

        g = Gasto(
            obra_id=int(obra_id),
            fecha=f,
            concepto=concepto,
            monto=monto,
            foto_nombre=foto_nombre,
            foto_mime=foto_mime,
            foto_bytes=foto_bytes
        )
        db.session.add(g)
        db.session.commit()

        flash("Gasto guardado ✅", "ok")
        return redirect(url_for("gastos", obra_id=obra_id, fecha=f.isoformat()))

    q = Gasto.query.filter(Gasto.fecha == fecha_sel).order_by(Gasto.creado.desc())
    if obra_id_sel:
        q = q.filter(Gasto.obra_id == obra_id_sel)

    lista_gastos = q.all()
    total_dia = sum((g.monto or 0) for g in lista_gastos)

    return render_template(
        "gastos.html",
        obras=obras_lista,
        gastos=lista_gastos,
        fecha_sel=fecha_sel,
        obra_id_sel=obra_id_sel,
        total_dia=total_dia
    )

@app.route("/dashboard")
def dashboard():
    obras_lista = Obra.query.order_by(Obra.creado.desc()).all()

    filas = []
    total_pres = 0.0
    total_gas = 0.0

    for o in obras_lista:
        partidas = PartidaPresupuesto.query.filter_by(obra_id=o.id).all()
        gastos_obra = Gasto.query.filter_by(obra_id=o.id).all()

        pres = sum((p.cantidad or 0) * (p.precio_unitario or 0) for p in partidas)
        gas = sum((g.monto or 0) for g in gastos_obra)

        diff = pres - gas
        avance = (gas / pres * 100.0) if pres > 0 else 0.0

        filas.append({
            "obra": o.nombre,
            "presupuesto": pres,
            "gastos": gas,
            "diferencia": diff,
            "avance": avance
        })

        total_pres += pres
        total_gas += gas

    total_diff = total_pres - total_gas
    total_avance = (total_gas / total_pres * 100.0) if total_pres > 0 else 0.0

    return render_template(
        "dashboard.html",
        filas=filas,
        total_pres=total_pres,
        total_gas=total_gas,
        total_diff=total_diff,
        total_avance=total_avance
    )

# SOLO PARA LOCAL (Render usa gunicorn)
if __name__ == "__main__":
    app.run(debug=True)

