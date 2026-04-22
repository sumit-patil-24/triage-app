from flask import Flask, render_template, request, redirect, url_for
import joblib
import os
import smtplib
from email.mime.text import MIMEText
import sqlite3
from flask import session
import json

with open('medicines.json') as f:
    med_data = json.load(f)

app = Flask(__name__)

app.secret_key = "supersecretkey"

def init_db():
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            password TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        conn.close()

        return redirect('/login')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = cur.fetchone()
        conn.close()

        if user:
            session['user'] = username
            return redirect('/')
        else:
            return "Invalid credentials"

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')

# ==============================
# LOAD ML MODEL
# ==============================
MODEL_PATH = "triage_model.joblib"

if not os.path.exists(MODEL_PATH):
    raise Exception("❌ Model not found. Run train_model.py first.")

model = joblib.load(MODEL_PATH)

# ==============================
# MEMORY STORAGE
# ==============================
patients = []
priority_order = {"RED": 1, "YELLOW": 2, "GREEN": 3}

# ==============================
# EMAIL ALERT FUNCTION
# ==============================
def send_email_alert(patient):
    sender_email = "sumit425412@gmail.com"
    sender_password = os.getenv('EMAIL_PASSWORD')
    receiver_email = "patil04sumit@gmail.com"

    subject = "🚨 URGENT: RED Patient Alert"

    body = f"""
    🚨 HIGH PRIORITY PATIENT DETECTED

    Name: {patient['name']}
    Age: {patient['age']}
    Triage: {patient['triage']}

    Immediate medical attention required.
    """

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print("✅ Email sent successfully")
    except Exception as e:
        print("❌ Email error:", e)

# ==============================
# ML TRIAGE FUNCTION
# ==============================
def triage_patient(age, fever, sweating, cough, comorbidity):
    features = [[age, fever, sweating, cough, comorbidity]]
    return model.predict(features)[0]

def recommend_meds(patient):
    meds = set()

    if patient['fever'] == 1:
        meds.update(med_data.get('fever', []))

    if patient['cough'] == 1:
        meds.update(med_data.get('cough', []))

    if patient['sweating'] == 1:
        meds.update(med_data.get('sweating', []))

    if patient['comorbidity'] == 1:
        meds.update(med_data.get('comorbidity', []))
    
    if patient['headache'] == 1:
        meds.update(med_data.get('headache', []))

    if patient['fatigue'] == 1:
        meds.update(med_data.get('fatigue', []))

    if patient['breathing'] == 1:
        meds.update(med_data.get('breathing', []))

    return list(meds)

def get_action(triage):
    if triage == "RED":
        return "Immediate hospital referral"
    elif triage == "YELLOW":
        return "Monitor closely"
    else:
        return "Home care"

# ==============================
# ROUTE
# ==============================
@app.route('/', methods=['GET', 'POST'])
def index():

    if 'user' not in session:
     return redirect('/login')

    filter_priority = request.args.get('filter_priority', 'ALL')
    search_name = request.args.get('search_name', '').lower()

    if request.method == 'POST':

        # ======================
        # UPDATE NOTES
        # ======================
        if 'update_notes' in request.form:
            idx = int(request.form['patient_index'])
            patients[idx]['notes'] = request.form.get('notes', '')
            return redirect(url_for('index',
                                    filter_priority=filter_priority,
                                    search_name=search_name))

        # ======================
        # NEW PATIENT
        # ======================
        name = request.form.get('name')
        age = int(request.form.get('age'))

        fever = 1 if 'fever' in request.form else 0
        sweating = 1 if 'sweating' in request.form else 0
        cough = 1 if 'cough' in request.form else 0
        comorbidity = 1 if 'comorbidity' in request.form else 0
        headache = 1 if 'headache' in request.form else 0
        fatigue = 1 if 'fatigue' in request.form else 0
        breathing = 1 if 'breathing' in request.form else 0

        triage = triage_patient(age, fever, sweating, cough, comorbidity)
        action = get_action(triage)

        patient = {
            "name": name,
            "age": age,
            "fever": fever,
            "sweating": sweating,
            "cough": cough,
            "comorbidity": comorbidity,
            "triage": triage,
            "action": action,
            "notes": "",
            "headache": headache,
            "fatigue": fatigue,
            "breathing": breathing
        }

        patient["medicines"] = recommend_meds(patient)

        patients.append(patient)

        # ======================
        # ALERT TRIGGER
        # ======================
        if triage == "RED":
            send_email_alert(patient)

        return redirect(url_for('index',
                                filter_priority=filter_priority,
                                search_name=search_name))

    # ======================
    # DISPLAY LOGIC
    # ======================
    data = list(enumerate(patients))

    if filter_priority != 'ALL':
        data = [p for p in data if p[1]['triage'] == filter_priority]

    if search_name:
        data = [p for p in data if search_name in p[1]['name'].lower()]

    data = sorted(data, key=lambda x: priority_order[x[1]['triage']])

    # Counts
    counts = {"RED": 0, "YELLOW": 0, "GREEN": 0}
    for p in patients:
        counts[p['triage']] += 1

    return render_template("index.html",
                           patients=data,
                           counts=counts,
                           filter_priority=filter_priority,
                           search_name=search_name)

# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    app.run(debug=True)