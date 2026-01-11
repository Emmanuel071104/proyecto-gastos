import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# --- CONFIGURACIÓN DE SEGURIDAD Y BASE DE DATOS ---
app.config['SECRET_KEY'] = 'simplefinance_2026_secreto'

# Configuración para PostgreSQL en Render o SQLite local
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
    rol = db.Column(db.String(20), default='usuario') # 'usuario' o 'admin'
    gastos = db.relationship('Gasto', backref='dueno', lazy=True)

class Categoria(db.Model):
    __tablename__ = 'categorias'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    gastos = db.relationship('Gasto', backref='categoria_rel', lazy=True)

class Gasto(db.Model):
    __tablename__ = 'gastos'
    id = db.Column(db.Integer, primary_key=True)
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    fecha = db.Column(db.DateTime, server_default=db.func.now())
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# --- RUTAS DE LA APLICACIÓN ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        # Redirección automática si es administrador
        if current_user.rol == 'admin':
            return redirect(url_for('dashboard'))
        
        # Lógica de filtros para usuarios regulares
        cat_id = request.args.get('categoria_id')
        inicio = request.args.get('inicio')
        fin = request.args.get('fin')

        query = Gasto.query.filter_by(usuario_id=current_user.id)

        if cat_id:
            query = query.filter_by(categoria_id=int(cat_id))
        if inicio and fin:
            query = query.filter(Gasto.fecha.between(inicio, fin))

        mis_gastos = query.order_by(Gasto.id.desc()).all()
        todas_categorias = Categoria.query.all()
        return render_template('index.html', gastos=mis_gastos, categorias=todas_categorias)
    return render_template('index.html')

@app.route('/chart-data')
@login_required
def chart_data():
    # Datos para el gráfico de pastel del usuario
    results = db.session.query(
        Categoria.nombre, db.func.sum(Gasto.monto)
    ).join(Gasto).filter(Gasto.usuario_id == current_user.id).group_by(Categoria.nombre).all()
    
    return jsonify({
        'labels': [r[0] for r in results],
        'values': [r[1] for r in results]
    })

@app.route('/eliminar/<int:id>')
@login_required
def eliminar(id):
    gasto = Gasto.query.get_or_404(id)
    # Verificación de propiedad para seguridad
    if gasto.usuario_id == current_user.id:
        db.session.delete(gasto)
        db.session.commit()
        flash('Registro eliminado correctamente.', 'success')
    return redirect(url_for('index'))

@app.route('/editar/<int:id>', methods=['POST'])
@login_required
def editar(id):
    gasto = Gasto.query.get_or_404(id)
    if gasto.usuario_id == current_user.id:
        gasto.monto = float(request.form.get('monto'))
        gasto.descripcion = request.form.get('descripcion')
        gasto.categoria_id = int(request.form.get('categoria_id'))
        db.session.commit()
        flash('Gasto actualizado con éxito.', 'success')
    return redirect(url_for('index'))

@app.route('/agregar', methods=['POST'])
@login_required
def agregar():
    monto = request.form.get('monto')
    descripcion = request.form.get('descripcion')
    cat_id = request.form.get('categoria_id')
    
    if monto and descripcion and cat_id:
        nuevo_gasto = Gasto(
            monto=float(monto),
            descripcion=descripcion,
            usuario_id=current_user.id,
            categoria_id=int(cat_id)
        )
        db.session.add(nuevo_gasto)
        db.session.commit()
        flash('Movimiento registrado.', 'success')
    return redirect(url_for('index'))

# --- RUTA DEL DASHBOARD ADMINISTRATIVO ACTUALIZADA ---

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.rol != 'admin':
        return redirect(url_for('index'))
    
    # Consultas para KPIs globales
    todos_los_gastos = Gasto.query.all()
    todos_los_usuarios = Usuario.query.all()
    
    total_global = sum(g.monto for g in todos_los_gastos)
    num_usuarios = len(todos_los_usuarios)
    promedio = total_global / num_usuarios if num_usuarios > 0 else 0
    
    # Últimos 5 movimientos del sistema
    actividad_reciente = Gasto.query.order_by(Gasto.id.desc()).limit(5).all()
    
    return render_template('dashboard.html', 
                           gastos=todos_los_gastos, 
                           total=total_global, 
                           usuarios=todos_los_usuarios,
                           num_usuarios=num_usuarios,
                           promedio=round(promedio, 2),
                           reciente=actividad_reciente)

# --- GESTIÓN DE SESIONES Y REGISTRO ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = Usuario.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
        flash('Credenciales incorrectas.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        if Usuario.query.filter_by(username=username).first():
            flash('Este nombre de usuario ya está en uso.', 'error')
        else:
            hashed_pw = generate_password_hash(request.form.get('password'))
            nuevo = Usuario(username=username, password=hashed_pw)
            db.session.add(nuevo)
            db.session.commit()
            flash('Cuenta creada. Ahora puedes iniciar sesión.', 'success')
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
        db.session.add_all([
            Categoria(nombre='Comida'), 
            Categoria(nombre='Transporte'), 
            Categoria(nombre='Ocio'), 
            Categoria(nombre='Salud')
        ])
    if not Usuario.query.filter_by(username='admin').first():
        # Contraseña por defecto para el admin inicial
        admin_pw = generate_password_hash('admin123')
        db.session.add(Usuario(username='admin', password=admin_pw, rol='admin'))
    db.session.commit()
    return "Infraestructura de base de datos inicializada correctamente."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))