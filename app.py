from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    current_user,
    logout_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

# -----------------------
# App & DB configuration
# -----------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "change_this_in_production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///hospital.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


# -------------
# Models
# -------------

class User(UserMixin, db.Model):
    """
    Single User table with role:
    - 'admin'
    - 'doctor'
    - 'patient'
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin / doctor / patient

    # Extra fields for doctors/patients
    specialization = db.Column(db.String(120))  # for doctors
    age = db.Column(db.Integer)                 # for patients
    gender = db.Column(db.String(10))          # for patients
    phone = db.Column(db.String(50))           # for patients
    address = db.Column(db.String(255))        # for patients

    is_active_flag = db.Column(db.Boolean, default=True)

    def set_password(self, plain_password: str):
        self.password_hash = generate_password_hash(plain_password)

    def check_password(self, plain_password: str) -> bool:
        return check_password_hash(self.password_hash, plain_password)

    def get_id(self):
        # flask-login expects this method; default from UserMixin also works
        return str(self.id)


class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.String(255))


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default="Booked")  # Booked / Completed / Cancelled

    patient = db.relationship("User", foreign_keys=[patient_id], backref="patient_appointments")
    doctor = db.relationship("User", foreign_keys=[doctor_id], backref="doctor_appointments")


class Treatment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointment.id"), nullable=False)
    diagnosis = db.Column(db.Text)
    prescription = db.Column(db.Text)
    notes = db.Column(db.Text)

    appointment = db.relationship("Appointment", backref="treatment")


# -------------
# Login manager
# -------------

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# -----------------------
# Helper: init database
# -----------------------

def init_db():
    """Create tables and seed a default admin and some sample data."""
    if not os.path.exists("hospital.db"):
        db.create_all()

        # Create default admin (only if none exists)
        if not User.query.filter_by(role="admin").first():
            admin = User(
                name="Admin User",
                email="admin@example.com",
                role="admin",
            )
            admin.set_password("admin123")  # <<< change this before final submission
            db.session.add(admin)

        # Sample departments
        cardio = Department(name="Cardiology", description="Heart and blood vessels")
        neuro = Department(name="Neurology", description="Brain and nervous system")
        db.session.add_all([cardio, neuro])

        db.session.commit()
        print("Database initialized with default admin and departments.")


# -------------
# Routes
# -------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active_flag:
            login_user(user)
            flash("Login successful", "success")
            if user.role == "admin":
                return redirect(url_for("admin_dashboard"))
            elif user.role == "doctor":
                return redirect(url_for("doctor_dashboard"))
            else:
                return redirect(url_for("patient_dashboard"))
        else:
            flash("Invalid credentials or inactive user", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out", "info")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Simple registration for patients.
    Doctors will typically be added by admin later.
    """
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        age = request.form.get("age")
        gender = request.form.get("gender", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()

        if not name or not email or not password:
            flash("Name, email and password are required.", "danger")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return render_template("register.html")

        try:
            age_val = int(age) if age else None
        except ValueError:
            flash("Age must be a number.", "danger")
            return render_template("register.html")

        user = User(
            name=name,
            email=email,
            role="patient",
            age=age_val,
            gender=gender,
            phone=phone,
            address=address,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# -----------------
# Dashboards
# -----------------

@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    if current_user.role != "admin":
        flash("Unauthorized access", "danger")
        return redirect(url_for("index"))

    total_doctors = User.query.filter_by(role="doctor").count()
    total_patients = User.query.filter_by(role="patient").count()
    total_appointments = Appointment.query.count()

    recent_appointments = (
        Appointment.query.order_by(Appointment.date_time.desc()).limit(10).all()
    )

    return render_template(
        "admin_dashboard.html",
        total_doctors=total_doctors,
        total_patients=total_patients,
        total_appointments=total_appointments,
        recent_appointments=recent_appointments,
    )


@app.route("/doctor/dashboard")
@login_required
def doctor_dashboard():
    if current_user.role != "doctor":
        flash("Unauthorized access", "danger")
        return redirect(url_for("index"))

    upcoming_appointments = (
        Appointment.query
        .filter(
            Appointment.doctor_id == current_user.id,
            Appointment.date_time >= datetime.now(),
        )
        .order_by(Appointment.date_time.asc())
        .all()
    )

    return render_template(
        "doctor_dashboard.html",
        upcoming_appointments=upcoming_appointments,
    )


@app.route("/patient/dashboard")
@login_required
def patient_dashboard():
    if current_user.role != "patient":
        flash("Unauthorized access", "danger")
        return redirect(url_for("index"))

    upcoming_appointments = (
        Appointment.query
        .filter(
            Appointment.patient_id == current_user.id,
            Appointment.date_time >= datetime.now(),
        )
        .order_by(Appointment.date_time.asc())
        .all()
    )

    past_appointments = (
        Appointment.query
        .filter(
            Appointment.patient_id == current_user.id,
            Appointment.date_time < datetime.now(),
        )
        .order_by(Appointment.date_time.desc())
        .all()
    )

    return render_template(
        "patient_dashboard.html",
        upcoming_appointments=upcoming_appointments,
        past_appointments=past_appointments,
    )


# -------------
# Main
# -------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
