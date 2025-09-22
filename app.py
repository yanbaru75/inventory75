import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import case, func

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
        app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    else:
        db_path = os.path.join(app.instance_path, "inventory.db")
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    return app

app = create_app()
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="staff")
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(120))
    email = db.Column(db.String(120))
    delivery_days = db.Column(db.String(120))
    lead_time_days = db.Column(db.Integer, default=1)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    unit = db.Column(db.String(50), default="個")
    location = db.Column(db.String(50), default="常温")
    par = db.Column(db.Integer, default=0)
    reorder_point = db.Column(db.Integer, default=0)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier.id"))
    notes = db.Column(db.Text)
    supplier = db.relationship("Supplier", backref=db.backref("items", lazy=True))

class StockMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False)
    kind = db.Column(db.String(10), nullable=False)  # in/out/waste/adj
    qty = db.Column(db.Float, nullable=False, default=0)
    ts = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    note = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    item = db.relationship("Item", backref=db.backref("movements", lazy=True))
    user = db.relationship("User", backref=db.backref("movements", lazy=True))

@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

def ensure_bootstrap_user():
    if User.query.count() == 0:
        u = User(username="admin", role="admin")
        u.set_password("admin123")
        db.session.add(u); db.session.commit()
        print("✅ 初期ユーザー: admin / admin123（ログイン後に変更推奨）")

def current_stock_map():
    signed = func.sum(
        case(
            (StockMovement.kind == "in", StockMovement.qty),
            (StockMovement.kind == "out", -StockMovement.qty),
            (StockMovement.kind == "waste", -StockMovement.qty),
            else_=StockMovement.qty,
        )
    )
    rows = db.session.query(StockMovement.item_id, func.coalesce(signed, 0.0)).group_by(StockMovement.item_id).all()
    return {item_id: float(qty or 0.0) for item_id, qty in rows}

@app.before_request
def _bootstrap():
    try:
        User.query.first()
    except Exception:
        db.create_all()
    if User.query.count() == 0:
        db.create_all(); ensure_bootstrap_user()

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user); flash("ログインしました。", "success")
            return redirect(url_for("inventory"))
        flash("ユーザー名またはパスワードが違います。", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user(); flash("ログアウトしました。", "success")
    return redirect(url_for("login"))

@app.route("/")
@login_required
def inventory():
    items = Item.query.order_by(Item.location, Item.name).all()
    stock = current_stock_map()
    rows = []
    for it in items:
        now = stock.get(it.id, 0.0)
        suggested = max(0, int((it.par or 0) - now))
        rows.append((it, now, suggested))
    return render_template("inventory.html", rows=rows)

@app.route("/movements/new", methods=["GET","POST"])
@login_required
def add_movement():
    if request.method == "POST":
        m = StockMovement(
            item_id=int(request.form["item_id"]),
            kind=request.form["kind"],
            qty=float(request.form["qty"]),
            note=request.form.get("note","").strip(),
            user_id=current_user.id,
        )
        db.session.add(m); db.session.commit()
        flash("在庫の更新を登録しました。", "success")
        return redirect(url_for("inventory"))
    items = Item.query.order_by(Item.name).all()
    return render_template("movement_form.html", items=items)

@app.route("/items")
@login_required
def items_list():
    items = Item.query.order_by(Item.location, Item.name).all()
    suppliers = {s.id: s for s in Supplier.query.all()}
    return render_template("items_list.html", items=items, suppliers=suppliers)

@app.route("/items/new", methods=["GET","POST"])
@login_required
def item_new():
    suppliers = Supplier.query.order_by(Supplier.name).all()
    if request.method == "POST":
        it = Item(
            name=request.form["name"].strip(),
            unit=request.form.get("unit","個").strip(),
            location=request.form.get("location","常温").strip(),
            par=int(request.form.get("par") or 0),
            reorder_point=int(request.form.get("reorder_point") or 0),
            supplier_id=int(request.form.get("supplier_id") or 0) or None,
            notes=request.form.get("notes","").strip(),
        )
        db.session.add(it); db.session.commit()
        flash("品目を追加しました。", "success")
        return redirect(url_for("items_list"))
    return render_template("item_form.html", item=None, suppliers=suppliers)

@app.route("/items/<int:item_id>/edit", methods=["GET","POST"])
@login_required
def item_edit(item_id):
    it = db.session.get(Item, item_id)
    if not it:
        flash("品目が見つかりません。", "error")
        return redirect(url_for("items_list"))
    suppliers = Supplier.query.order_by(Supplier.name).all()
    if request.method == "POST":
        it.name = request.form["name"].strip()
        it.unit = request.form.get("unit","個").strip()
        it.location = request.form.get("location","常温").strip()
        it.par = int(request.form.get("par") or 0)
        it.reorder_point = int(request.form.get("reorder_point") or 0)
        it.supplier_id = int(request.form.get("supplier_id") or 0) or None
        it.notes = request.form.get("notes","").strip()
        db.session.commit(); flash("品目を更新しました。", "success")
        return redirect(url_for("items_list"))
    return render_template("item_form.html", item=it, suppliers=suppliers)

@app.route("/suppliers")
@login_required
def suppliers_list():
    sp = Supplier.query.order_by(Supplier.name).all()
    return render_template("suppliers_list.html", suppliers=sp)

@app.route("/suppliers/new", methods=["GET","POST"])
@login_required
def supplier_new():
    if request.method == "POST":
        s = Supplier(
            name=request.form["name"].strip(),
            phone=request.form.get("phone","").strip(),
            email=request.form.get("email","").strip(),
            delivery_days=request.form.get("delivery_days","").strip(),
            lead_time_days=int(request.form.get("lead_time_days") or 1),
        )
        db.session.add(s); db.session.commit()
        flash("仕入先を追加しました。", "success")
        return redirect(url_for("suppliers_list"))
    return render_template("supplier_form.html", supplier=None)

@app.route("/suppliers/<int:supplier_id>/edit", methods=["GET","POST"])
@login_required
def supplier_edit(supplier_id):
    s = db.session.get(Supplier, supplier_id)
    if not s:
        flash("仕入先が見つかりません。", "error")
        return redirect(url_for("suppliers_list"))
    if request.method == "POST":
        s.name = request.form["name"].strip()
        s.phone = request.form.get("phone","").strip()
        s.email = request.form.get("email","").strip()
        s.delivery_days = request.form.get("delivery_days","").strip()
        s.lead_time_days = int(request.form.get("lead_time_days") or 1)
        db.session.commit(); flash("仕入先を更新しました。", "success")
        return redirect(url_for("suppliers_list"))
    return render_template("supplier_form.html", supplier=s)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

