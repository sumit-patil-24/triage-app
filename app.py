from flask import Flask, render_template, request, redirect, session, flash
import os, sqlite3, json, math, smtplib
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from email.mime.text import MIMEText
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = "secret123"

# --- CONFIGURATION (Environment Variables) ---
# Retrieve credentials securely
SENDER_EMAIL = os.environ.get('EMAIL_USER')
SENDER_PASSWORD = os.environ.get('EMAIL_PASS')

# --- DATA LOADING ---
def load_json(file, default):
    try:
        with open(file) as f:
            return json.load(f)
    except:
        return default

MED_DATA = load_json('medicines.json', {})
DOCTORS = load_json('doctors.json', [])

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS patients(
        id INTEGER PRIMARY KEY, name TEXT, data TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- UTILS & VALIDATION ---
def safe_float(v, default):
    """Prevents app crash if lat/lon is empty or malformed."""
    try:
        if v and str(v).strip():
            return float(v)
        return default
    except (ValueError, TypeError):
        return default

def dist(a, b, c, d):
    """Haversine formula for distance."""
    R = 6371
    dlat = math.radians(c - a)
    dlon = math.radians(d - b)
    x = math.sin(dlat / 2)**2 + math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.sin(dlon / 2)**2
    return R * 2 * math.atan2(math.sqrt(x), math.sqrt(1 - x))

def get_docs(lat, lon):
    """Find 3 nearest doctors."""
    arr = []
    for d in DOCTORS:
        dd = d.copy()
        dd['distance'] = round(dist(lat, lon, d['lat'], d['lon']), 1)
        arr.append(dd)
    return sorted(arr, key=lambda x: x['distance'])[:3]

def triage(p):
    """Triage scoring logic."""
    score = 0
    if p['age'] > 65: score += 3
    if p['fever']: score += 1
    if p['cough']: score += 1
    if p['breathing']: score += 3
    if p['comorbidity']: score += 2
    if p['sweating']: score += 1
    
    if score >= 6: return "RED"
    if score >= 3: return "YELLOW"
    return "GREEN"

# --- EMAIL ALERT SYSTEM ---
def send_email_alert(patient, doctor):
    """Automated SMTP notification gateway."""
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("❌ Skip Email: Environment variables EMAIL_USER or EMAIL_PASS not set.")
        return

    subject = f"🚨 EMERGENCY: Critical Patient {patient['name']}"
    body = f"""
    Emergency Alert for {doctor['name']},

    A critical (RED) patient has been registered near your location.
    
    Patient: {patient['name']} (Age: {patient['age']})
    Location Coordinates: {patient['lat']}, {patient['lon']}
    Action Status: {patient['action']}
    
    Please check the triage dashboard for details.
    """
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = doctor.get('email', 'hospital-emergency@example.com') 

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print(f"✅ Alert email sent to {doctor['name']}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

# --- ROUTES ---

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute("SELECT id, data FROM patients ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    patients = []
    counts = {'RED': 0, 'YELLOW': 0, 'GREEN': 0}
    for r in rows:
        p = json.loads(r[1])
        p['id'] = r[0]
        patients.append(p)
        counts[p['triage']] += 1
        
    return render_template('index.html', patients=patients, counts=counts)

@app.route('/add_patient', methods=['POST'])
def add_patient():
    if 'user_id' not in session:
        return redirect('/login')

    name = request.form.get('name', '').strip()
    if not name:
        flash("Name is required", "danger")
        return redirect('/')

    # Fixed float conversion with safe_float
    p = {
        'name': name,
        'age': int(request.form.get('age', 30)),
        'fever': 1 if 'fever' in request.form else 0,
        'cough': 1 if 'cough' in request.form else 0,
        'sweating': 1 if 'sweating' in request.form else 0,
        'headache': 1 if 'headache' in request.form else 0,
        'fatigue': 1 if 'fatigue' in request.form else 0,
        'breathing': 1 if 'breathing' in request.form else 0,
        'comorbidity': 1 if 'comorbidity' in request.form else 0,
        'lat': safe_float(request.form.get('lat'), 18.5204),
        'lon': safe_float(request.form.get('lon'), 73.8567),
        'notes': '',
        'timestamp': datetime.now().isoformat()
    }

    p['triage'] = triage(p)
    p['action'] = "🚨 Go hospital NOW" if p['triage'] == "RED" else "⚠️ Monitor" if p['triage'] == "YELLOW" else "✅ Home care"
    p['doctors'] = get_docs(p['lat'], p['lon'])
    
    # Map symptoms to medicines
    symptoms = ['fever', 'cough', 'sweating', 'headache', 'fatigue', 'breathing', 'comorbidity']
    p['medicines'] = list(set([m for s in symptoms if p.get(s) for m in MED_DATA.get(s, [])]))

    # Trigger Alert for RED patients
    if p['triage'] == "RED" and p['doctors']:
        send_email_alert(p, p['doctors'][0])

    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO patients(name,data) VALUES(?,?)", (p['name'], json.dumps(p)))
    conn.commit()
    conn.close()
    
    flash(f"Patient {name} Triaged as {p['triage']}", "success")
    return redirect('/')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, pw = request.form['username'], request.form['password']
        conn = sqlite3.connect('users.db')
        cur = conn.cursor()
        cur.execute("SELECT id, password FROM users WHERE username=?", (u,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user[1], pw):
            session['user_id'] = user[0]
            return redirect('/')
        flash("Invalid Credentials", "danger")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, pw = request.form['username'], request.form['password']
        conn = sqlite3.connect('users.db')
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users VALUES(NULL,?,?)", (u, generate_password_hash(pw)))
            conn.commit()
            return redirect('/login')
        except:
            flash("User already exists", "danger")
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    app.run(debug=True)