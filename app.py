from flask import Flask, render_template, request, redirect, url_for, session, flash
import joblib
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3
import json
import math
import pandas as pd
import numpy as np
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'super-secret-triage-key-2024')

# Load data
try:
    with open('medicines.json', 'r') as f:
        MED_DATA = json.load(f)
    with open('doctors.json', 'r') as f:
        DOCTORS = json.load(f)
except:
    MED_DATA = {}
    DOCTORS = []

def init_db():
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Load ML Model
model = None
try:
    if os.path.exists("triage_model.joblib"):
        model = joblib.load("triage_model.joblib")
        logger.info("✅ ML Model loaded")
except:
    logger.warning("⚠️ Using rule-based triage")

patients_cache = []

def load_patients():
    global patients_cache
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute("SELECT data FROM patients ORDER BY created_at DESC")
    records = cur.fetchall()
    patients_cache = []
    for record in records:
        try:
            patient = json.loads(record[0])
            patients_cache.append(patient)
        except:
            pass
    conn.close()

def clean_for_json(obj):
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(v) for v in obj]
    return obj

def save_patient(patient):
    patient_clean = clean_for_json(patient)
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO patients (name, data) VALUES (?, ?)",
                (patient_clean['name'], json.dumps(patient_clean)))
    conn.commit()
    conn.close()
    load_patients()

load_patients()

PRIORITY_ORDER = {"RED": 1, "YELLOW": 2, "GREEN": 3}

def send_alert(patient):
    try:
        sender = "sumit425412@gmail.com"
        password = os.getenv('EMAIL_PASSWORD')
        if not password: 
            print("⚠️ Set EMAIL_PASSWORD for alerts")
            return False
        
        receiver = "patil04sumit@gmail.com"
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = receiver
        msg['Subject'] = f"🚨 RED ALERT: {patient['name']}"
        
        body = f"""
🚨 CRITICAL PATIENT ALERT 🚨

PATIENT: {patient['name']} (Age: {patient['age']})
TRIA GE: RED
LOCATION: {patient['lat']}, {patient['lon']}
ACTION: {patient['action']}

IMMEDIATE ATTENTION REQUIRED!
        """
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        print("✅ EMAIL SENT!")
        return True
    except Exception as e:
        print(f"Email failed: {e}")
        return False

def triage_patient(patient_data):
    # Aggressive rule-based scoring
    score = 0
    print(f"🔍 TRIAGE DEBUG: {patient_data['name']}")
    
    if patient_data['age'] > 65: 
        score += 3
        print(f"  +3 Age >65 ({patient_data['age']})")
    if patient_data['age'] > 75: 
        score += 2
        print(f"  +2 Age >75")
    
    if patient_data['fever']: 
        score += 1
        print("  +1 Fever")
    if patient_data['cough']: 
        score += 1
        print("  +1 Cough")
    if patient_data['breathing']: 
        score += 3
        print("  +3 BREATHING EMERGENCY!")
    if patient_data['comorbidity']: 
        score += 2
        print("  +2 Comorbidity")
    if patient_data['sweating']: 
        score += 1
        print("  +1 Sweating")
    
    print(f"  TOTAL SCORE: {score}")
    
    if score >= 6: 
        print("  🎯 RESULT: RED")
        return "RED"
    elif score >= 3: 
        print("  🎯 RESULT: YELLOW")
        return "YELLOW"
    print("  🎯 RESULT: GREEN")
    return "GREEN"

def recommend_medicines(patient):
    meds = set()
    symptoms = ['fever', 'cough', 'sweating', 'headache', 'fatigue', 'breathing', 'comorbidity']
    for symptom in symptoms:
        if patient.get(symptom, 0):
            meds.update(MED_DATA.get(symptom, []))
    return list(meds)[:5]

def find_nearest_doctors(lat, lon, triage=None):
    doctors_with_distance = []

    for doc in DOCTORS:
        # Optional filtering based on severity
        if triage == "RED" and doc['specialty'] not in ["Emergency Medicine", "Pulmonology"]:
            continue

        distance = haversine_distance(lat, lon, doc['lat'], doc['lon'])
        doc_copy = doc.copy()
        doc_copy['distance'] = round(distance, 1)
        doctors_with_distance.append(doc_copy)

    return sorted(doctors_with_distance, key=lambda x: x['distance'])[:3]

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * 
         math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def get_action_plan(triage):
    return {
        "RED": "🚨 IMMEDIATE HOSPITAL - Call 108/102 NOW",
        "YELLOW": "⚠️ CLOSE MONITORING - Reassess in 1 hour", 
        "GREEN": "✅ HOME CARE - Monitor daily"
    }.get(triage, "Monitor")

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect('/login')
    
    priority = request.args.get('priority', 'ALL')
    search = request.args.get('search', '').lower()
    
    filtered = patients_cache.copy()
    if priority != 'ALL':
        filtered = [p for p in filtered if p['triage'] == priority]
    if search:
        filtered = [p for p in filtered if search in p['name'].lower()]
    
    filtered.sort(key=lambda x: PRIORITY_ORDER.get(x['triage'], 99))
    
    counts = {'RED': 0, 'YELLOW': 0, 'GREEN': 0}
    for p in patients_cache:
        counts[p['triage']] += 1
    
    return render_template('index.html', 
                         patients=filtered,
                         counts=counts,
                         priority=priority,
                         search=search)

@app.route('/emergency_patients')
def emergency_patients():
    red_patients = [p for p in patients_cache if p['triage'] == 'RED']
    return {"patients": red_patients}

@app.route('/add_patient', methods=['POST'])
def add_patient():
    if 'user_id' not in session:
        return redirect('/login')
    
    def safe_float(val, default):
        try:
            cleaned = str(val).strip()
            return float(cleaned) if cleaned else default
        except:
            return default
    
    def safe_int(val, default):
        try:
            return int(val)
        except:
            return default
    
    patient_data = {
        'name': request.form.get('name', 'Unknown').strip()[:50],
        'age': safe_int(request.form.get('age', 30), 30),
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
    
    patient_data['age'] = max(1, min(120, patient_data['age']))
    
    patient_data['triage'] = triage_patient(patient_data)
    patient_data['action'] = get_action_plan(patient_data['triage'])
    patient_data['medicines'] = recommend_medicines(patient_data)
    patient_data['doctors'] = find_nearest_doctors(
    patient_data['lat'],
    patient_data['lon'],
    patient_data['triage']
    )
    
    save_patient(patient_data)
    if patient_data['triage'] == 'RED':
        send_alert(patient_data)
    
    flash(f'✅ Patient "{patient_data["name"]}" ADDED! Triage: <strong>{patient_data["triage"]}</strong>', 'success')
    return redirect('/')

@app.route('/update_notes', methods=['POST'])
def update_notes():
    if 'user_id' not in session:
        return redirect('/login')
    
    patient_idx = int(request.form.get('patient_idx', 0))
    notes = request.form.get('notes', '')[:500]
    
    if 0 <= patient_idx < len(patients_cache):
        patients_cache[patient_idx]['notes'] = notes
        save_patient(patients_cache[patient_idx])
        flash('📝 Notes SAVED!', 'success')
    
    return redirect('/')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        conn = sqlite3.connect('users.db')
        cur = conn.cursor()
        cur.execute("SELECT id, password FROM users WHERE username=?", (username,))
        user = cur.fetchone()
        conn.close()
        
        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['username'] = username
            flash('✅ Welcome back!', 'success')
            return redirect('/')
        flash('❌ Wrong username/password', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        if len(password) < 6:
            flash('Password too short (min 6 chars)', 'danger')
            return render_template('register.html')
        
        try:
            conn = sqlite3.connect('users.db')
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                       (username, generate_password_hash(password)))
            conn.commit()
            conn.close()
            flash('✅ Account created! Login now.', 'success')
            return redirect('/login')
        except sqlite3.IntegrityError:
            flash('❌ Username already taken', 'danger')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('👋 See you later!', 'info')
    return redirect('/login')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)