import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'simplefinance_2026_secreto'

uri = os.getenv("DATABASE_URL", "sqlite:///gastos.db")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELOS (5 TABLAS) ---
class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), default='usuario')
    gastos = db.relationship('Gasto', backref='dueno', lazy=True, cascade="all, delete-orphan")
    presupuesto = db.relationship('Presupuesto', backref='dueno', lazy=True, uselist=False, cascade="all, delete-orphan")

class Categoria(db.Model):
    __tablename__ = 'categorias'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    gastos = db.relationship('Gasto', backref='categoria_rel', lazy=True)

class MetodoPago(db.Model):
    __tablename__ = 'metodos_pago'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    gastos = db.relationship('Gasto', backref='metodo_rel', lazy=True)

class Presupuesto(db.Model):
    __tablename__ = 'presupuestos'
    id = db.Column(db.Integer, primary_key=True)
    monto_limite = db.Column(db.Float, nullable=False, default=0.0)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)

class Gasto(db.Model):
    __tablename__ = 'gastos'
    id = db.Column(db.Integer, primary_key=True)
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    fecha = db.Column(db.DateTime, server_default=db.func.now())
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=False)
    metodo_id = db.Column(db.Integer, db.ForeignKey('metodos_pago.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# --- RUTAS DE LA GRÁFICA Y MANTENIMIENTO ---

@app.route('/chart-data')
@login_required
def chart_data():
    # Consulta para agrupar gastos por categoría
    results = db.session.query(Categoria.nombre, db.func.sum(Gasto.monto)).join(Gasto).filter(Gasto.usuario_id == current_user.id).group_by(Categoria.nombre).all()
    return jsonify({'labels': [r[0] for r in results], 'values': [r[1] for r in results]})

@app.route('/reset-db')
def reset_db():
    db.drop_all()
    db.create_all()
    return "Base de datos borrada y recreada. Ve a /setup"

# --- RUTAS DE USUARIO ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.rol == 'admin': return redirect(url_for('dashboard'))
        
        # Filtros
        cat_id = request.args.get('categoria_id')
        inicio, fin = request.args.get('inicio'), request.args.get('fin')
        query = Gasto.query.filter_by(usuario_id=current_user.id)
        if cat_id: query = query.filter_by(categoria_id=int(cat_id))
        if inicio and fin: query = query.filter(Gasto.fecha.between(inicio, fin))
        
        mis_gastos = query.order_by(Gasto.id.desc()).all()
        
        # Lógica de presupuesto
        p_user = Presupuesto.query.filter_by(usuario_id=current_user.id).first()
        limite = p_user.monto_limite if p_user else 0
        saldo = limite - sum(g.monto for g in mis_gastos)
        
        return render_template('index.html', gastos=mis_gastos, categorias=Categoria.query.all(), 
                               metodos=MetodoPago.query.all(), limite=limite, saldo=saldo)
    return render_template('index.html')

@app.route('/definir_presupuesto', methods=['POST'])
@login_required
def definir_presupuesto():
    monto = request.form.get('monto')
    if monto:
        p = Presupuesto.query.filter_by(usuario_id=current_user.id).first()
        if p: p.monto_limite = float(monto)
        else: db.session.add(Presupuesto(monto_limite=float(monto), usuario_id=current_user.id))
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/agregar', methods=['POST'])
@login_required
def agregar():
    m, d, c, met = request.form.get('monto'), request.form.get('descripcion'), request.form.get('categoria_id'), request.form.get('metodo_id')
    if m and d and c and met:
        db.session.add(Gasto(monto=float(m), descripcion=d, usuario_id=current_user.id, categoria_id=int(c), metodo_id=int(met)))
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/editar/<int:id>', methods=['POST'])
@login_required
def editar(id):
    g = Gasto.query.get_or_404(id)
    if g.usuario_id == current_user.id:
        g.monto, g.descripcion = float(request.form.get('monto')), request.form.get('descripcion')
        g.categoria_id, g.metodo_id = int(request.form.get('categoria_id')), int(request.form.get('metodo_id'))
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/eliminar/<int:id>')
@login_required
def eliminar(id):
    g = Gasto.query.get_or_404(id)
    if g.usuario_id == current_user.id:
        db.session.delete(g)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.rol != 'admin': return redirect(url_for('index'))
    gastos, usuarios = Gasto.query.all(), Usuario.query.all()
    total = sum(g.monto for g in gastos)
    promedio = total / len(usuarios) if usuarios else 0
    return render_template('dashboard.html', gastos=gastos, total=total, usuarios=usuarios, 
                           num_usuarios=len(usuarios), promedio=round(promedio, 2), 
                           reciente=Gasto.query.order_by(Gasto.id.desc()).limit(5).all())

@app.route('/eliminar_usuario/<int:id>')
@login_required
def eliminar_usuario(id):
    if current_user.rol != 'admin': return redirect(url_for('index'))
    u = Usuario.query.get_or_404(id)
    if u.id != current_user.id:
        db.session.delete(u)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = Usuario.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user = request.form.get('username')
        if not Usuario.query.filter_by(username=user).first():
            db.session.add(Usuario(username=user, password=generate_password_hash(request.form.get('password'))))
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/setup')
def setup():
    db.create_all()
    if not Categoria.query.first():
        db.session.add_all([Categoria(nombre='Comida'), Categoria(nombre='Transporte'), Categoria(nombre='Ocio'), Categoria(nombre='Salud')])
    if not MetodoPago.query.first():
        db.session.add_all([MetodoPago(nombre='Efectivo'), MetodoPago(nombre='Tarjeta Débito'), MetodoPago(nombre='Tarjeta Crédito')])
    if not Usuario.query.filter_by(username='admin').first():
        db.session.add(Usuario(username='admin', password=generate_password_hash('admin123'), rol='admin'))
    db.session.commit()
    return "Base configurada."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))