import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# --- CONFIGURACIÓN DE SEGURIDAD Y BASE DE DATOS ---
app.config['SECRET_KEY'] = 'ipn_computacion_2026_secreto'

# Parche para compatibilidad de SQLAlchemy con Render (postgres:// -> postgresql://)
uri = os.getenv("DATABASE_URL", "sqlite:///gastos.db")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELOS DE LA BASE DE DATOS (ORM) ---
class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), default='usuario') # 'admin' o 'usuario'
    # Relación: Un usuario tiene muchos gastos
    gastos = db.relationship('Gasto', backref='dueno', lazy=True)

class Gasto(db.Model):
    __tablename__ = 'gastos'
    id = db.Column(db.Integer, primary_key=True)
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    fecha = db.Column(db.DateTime, server_default=db.func.now())
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# --- RUTAS DE LA APLICACIÓN ---

# 1. Landing Page e Interfaz de Usuario
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.rol == 'admin':
            return redirect(url_for('dashboard'))
        # Si es usuario normal, mostramos sus gastos en la misma landing
        mis_gastos = Gasto.query.filter_by(usuario_id=current_user.id).order_by(Gasto.id.desc()).all()
        return render_template('index.html', gastos=mis_gastos)
    return render_template('index.html') # Landing pública para no logueados

# 2. Dashboard (Exclusivo para ADMIN)
@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.rol != 'admin':
        flash('No tienes permiso para acceder a esta sección.')
        return redirect(url_for('index'))
    
    todos_los_gastos = Gasto.query.all()
    total_global = sum(g.monto for g in todos_los_gastos)
    return render_template('dashboard.html', gastos=todos_los_gastos, total=total_global)

# 3. Registro de nuevos usuarios
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if Usuario.query.filter_by(username=username).first():
            flash('El usuario ya existe.')
            return redirect(url_for('register'))
            
        hashed_pw = generate_password_hash(password)
        nuevo_usuario = Usuario(username=username, password=hashed_pw, rol='usuario')
        db.session.add(nuevo_usuario)
        db.session.commit()
        flash('Registro exitoso. ¡Inicia sesión!')
        return redirect(url_for('login'))
        
    return render_template('register.html')

# 4. Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = Usuario.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
        flash('Credenciales incorrectas.')
    return render_template('login.html')

# 5. Acción: Agregar Gasto
@app.route('/agregar', methods=['POST'])
@login_required
def agregar():
    monto = request.form.get('monto')
    descripcion = request.form.get('descripcion')
    
    if monto and descripcion:
        nuevo_gasto = Gasto(
            monto=float(monto),
            descripcion=descripcion,
            usuario_id=current_user.id
        )
        db.session.add(nuevo_gasto)
        db.session.commit()
        
    return redirect(url_for('index'))

# 6. Logout
@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# 7. Setup Inicial (CREAR TABLAS Y ADMIN)
@app.route('/setup')
def setup():
    db.create_all()
    # Crear admin por defecto si no existe
    if not Usuario.query.filter_by(username='admin').first():
        admin_pass = generate_password_hash('admin123')
        admin_user = Usuario(username='admin', password=admin_pass, rol='admin')
        db.session.add(admin_user)
        db.session.commit()
    return "Base de datos inicializada y Admin creado (admin / admin123)"

if __name__ == '__main__':
    # Usamos host 0.0.0.0 para que sea accesible desde el exterior en Render
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))