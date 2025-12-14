from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import cloudinary
import cloudinary.uploader

# -------------------------
# APP
# -------------------------
app = Flask(__name__)
app.secret_key = "construar-local"

# -------------------------
# BASE DE DATOS (NUEVA)
# -------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(INSTANCE_DIR, "construar_v2.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Limite de subida: 3 MB
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024

db = SQLAlchemy(app)

# -------------------------
# CLOUDINARY
# -------------------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# -------------------------
# MODELOS
# -------------------------
class Obra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

class Gasto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"), nullable=False)
    concepto = db.Column(db.String(200), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    foto_url = db.Column(db.String(500))
    foto_public_id = db.Column(db.String(200))
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    obra = db.relationship("Obra", backref=db.backref("gastos", lazy=True))

# -------------------------
# CREAR TABLAS
# -------------------------
with app.app_context():
    db.create_all()

# -------------------------
# RUTAS
# -------------------------
@app.route("/")
def home():
    return render_template("index.html")

# -------- OBRAS ----------
@app.route("/obras", methods=["GET", "POST"])
def obras():
    if request.method == "POST":
        nombre = request.form["nombre"]
        if nombre:
            db.session.add(Obra(nombre=nombre))
            db.session.commit()
            flash("Obra creada correctamente", "success")
        return redirect(url_for("obras"))

    lista = Obra.query.order_by(Obra.creado.desc()).all()
    return render_template("obras.html", obras=lista)

# -------- GASTOS ----------
@app.route("/gastos", methods=["GET", "POST"])
def gastos():
    obras = Obra.query.all()

    if request.method == "POST":
        obra_id = request.form["obra_id"]
        concepto = request.form["concepto"]
        monto = float(request.form["monto"])
        fecha = datetime.strptime(request.form["fecha"], "%Y-%m-%d").date()

        foto_url = None
        foto_public_id = None

        file = request.files.get("foto")

        if file and file.filename:
            try:
                resultado = cloudinary.uploader.upload(
                    file,
                    folder="construar/gastos",
                    resource_type="image"
                )
                foto_url = resultado.get("secure_url")
                foto_public_id = resultado.get("public_id")
            except Exception as e:
                print("ERROR CLOUDINARY:", e)

        gasto = Gasto(
            obra_id=obra_id,
            concepto=concepto,
            monto=monto,
            fecha=fecha,
            foto_url=foto_url,
            foto_public_id=foto_public_id
        )

        db.session.add(gasto)
        db.session.commit()

        flash("Gasto registrado correctamente", "success")
        return redirect(url_for("gastos"))

    lista = Gasto.query.order_by(Gasto.fecha.desc()).all()
    return render_template("gastos.html", gastos=lista, obras=obras)

# -------------------------
# ERRORES
# -------------------------
@app.errorhandler(413)
def archivo_muy_grande(e):
    return "La imagen supera el límite de 3 MB", 413

@app.errorhandler(500)
def error_servidor(e):
    return "Error interno del servidor", 500

# -------------------------
# MAIN
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)


