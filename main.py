
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

# --------------------
# APP
# --------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "construar-local")

# --------------------
# DATABASE (Render / PostgreSQL)
# --------------------
db_url = os.environ.get("DATABASE_URL")

if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if not db_url:
    db_url = "sqlite:///" + os.path.join(app.instance_path, "construar.db")

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# --------------------
# MODELOS
# --------------------
class Obra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    ubicacion = db.Column(db.String(200))
    cliente = db.Column(db.String(120))
    creado = db.Column(db.DateTime, default=datetime.utcnow)

class PartidaPresupuesto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"), nullable=False)
    obra = db.relationship("Obra", backref=db.backref("partidas_presupuesto", lazy=True))

    partida = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.String(250), nullable=False)
    unidad = db.Column(db.String(30))
    cantidad = db.Column(db.Float, default=0.0)
    precio_unitario = db.Column(db.Float, default=0.0)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

class Gasto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"), nullable=False)
    obra = db.relationship("Obra", backref=db.backref("gastos", lazy=True))

    fecha = db.Column(db.Date, nullable=False)
    categoria = db.Column(db.String(60), nullable=False)
    concepto = db.Column(db.String(250), nullable=False)
    monto = db.Column(db.Float, nullable=False, default=0.0)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

# --------------------
# CREAR TABLAS
# --------------------
with app.app_context():
    if db_url.startswith("sqlite:///"):
        os.makedirs(app.instance_path, exist_ok=True)
    db.create_all()

# --------------------
# HOME
# --------------------
@app.route("/")
def home():
    return render_template("index.html")

# --------------------
# NUEVA OBRA
# --------------------
@app.route("/obras/nueva", methods=["GET", "POST"])
def nueva_obra():
    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        ubicacion = (request.form.get("ubicacion") or "").strip()
        cliente = (request.form.get("cliente") or "").strip()

        if nombre:
            db.session.add(Obra(nombre=nombre, ubicacion=ubicacion, cliente=cliente))
            db.session.commit()

        return redirect(url_for("nueva_obra"))

    obras = Obra.query.order_by(Obra.creado.desc()).all()
    return render_template("nueva_obra.html", obras=obras)

# --------------------
# PRESUPUESTO
# --------------------
@app.route("/presupuesto", methods=["GET", "POST"])
def presupuesto():
    obras = Obra.query.order_by(Obra.creado.desc()).all()
    obra_id = request.args.get("obra_id", type=int)

    if obra_id is None and obras:
        obra_id = obras[0].id

    obra_sel = Obra.query.get(obra_id) if obra_id else None

    def to_float(x):
        try:
            return float((x or "0").replace(",", ""))
        except:
            return 0.0

    if request.method == "POST" and obra_sel:
        db.session.add(
            PartidaPresupuesto(
                obra_id=obra_sel.id,
                partida=request.form.get("partida"),
                descripcion=request.form.get("descripcion"),
                unidad=request.form.get("unidad"),
                cantidad=to_float(request.form.get("cantidad")),
                precio_unitario=to_float(request.form.get("precio_unitario")),
            )
        )
        db.session.commit()
        return redirect(url_for("presupuesto", obra_id=obra_sel.id))

    partidas = []
    total = 0.0
    if obra_sel:
        partidas = PartidaPresupuesto.query.filter_by(obra_id=obra_sel.id).all()
        total = sum((p.cantidad or 0) * (p.precio_unitario or 0) for p in partidas)

    return render_template("presupuesto.html", obras=obras, obra_sel=obra_sel, partidas=partidas, total=total)

# --------------------
# GASTOS (DESDE CELULAR)
# --------------------
@app.route("/gastos", methods=["GET", "POST"])
def gastos():
    obras = Obra.query.order_by(Obra.creado.desc()).all()
    obra_id = request.args.get("obra_id", type=int)

    if obra_id is None and obras:
        obra_id = obras[0].id

    obra_sel = Obra.query.get(obra_id) if obra_id else None

    def to_float(x):
        try:
            return float((x or "0").replace(",", ""))
        except:
            return 0.0

    if request.method == "POST" and obra_sel:
        fecha = datetime.strptime(request.form.get("fecha"), "%Y-%m-%d").date()
        db.session.add(
            Gasto(
                obra_id=obra_sel.id,
                fecha=fecha,
                categoria=request.form.get("categoria"),
                concepto=request.form.get("concepto"),
                monto=to_float(request.form.get("monto")),
            )
        )
        db.session.commit()
        return redirect(url_for("gastos", obra_id=obra_sel.id))

    gastos = []
    total = 0.0
    if obra_sel:
        gastos = Gasto.query.filter_by(obra_id=obra_sel.id).all()
        total = sum(g.monto or 0 for g in gastos)

    return render_template("gastos.html", obras=obras, obra_sel=obra_sel, gastos=gastos, total=total)

# --------------------
# DASHBOARD
# --------------------
@app.route("/dashboard")
def dashboard():
    obras = Obra.query.order_by(Obra.creado.desc()).all()

    filas = []
    total_pres = 0
    total_gas = 0

    for o in obras:
        pres = sum((p.cantidad or 0) * (p.precio_unitario or 0) for p in o.partidas_presupuesto)
        gas = sum((g.monto or 0) for g in o.gastos)

        filas.append({
            "obra": o,
            "presupuesto": pres,
            "gastos": gas,
            "diferencia": pres - gas,
            "avance": (gas / pres * 100) if pres > 0 else 0,
        })

        total_pres += pres
        total_gas += gas

    return render_template(
        "dashboard.html",
        filas=filas,
        total_pres=total_pres,
        total_gas=total_gas,
        total_diff=total_pres - total_gas,
        total_avance=(total_gas / total_pres * 100) if total_pres > 0 else 0,
    )

# --------------------
# SOLO PARA EJECUCIÓN LOCAL
# --------------------
if __name__ == "__main__":
    app.run(debug=True)
if __name__ == "__main__":
    app.run(debug=True)


