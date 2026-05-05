from flask import Flask, render_template, request, redirect, session, flash
import os, sqlite3, json, math
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret123"

# Load JSON
def load_json(file, default):
    try:
        with open(file) as f:
            return json.load(f)
    except:
        return default

MED_DATA = load_json('medicines.json', {})
DOCTORS = load_json('doctors.json', [])

# DB
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

# Load patients
def load_patients():
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute("SELECT id,data FROM patients ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    patients = []
    for r in rows:
        p = json.loads(r[1])
        p['id'] = r[0]
        patients.append(p)
    return patients

# Save / update
def save_patient(p):
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()

    if 'id' in p:
        cur.execute("UPDATE patients SET data=? WHERE id=?",
                    (json.dumps(p), p['id']))
    else:
        cur.execute("INSERT INTO patients(name,data) VALUES(?,?)",
                    (p['name'], json.dumps(p)))

    conn.commit()
    conn.close()

# Safe float
def safe_float(v, default):
    try:
        return float(v) if str(v).strip() else default
    except:
        return default

# Distance
def dist(a,b,c,d):
    R=6371
    dlat=math.radians(c-a)
    dlon=math.radians(d-b)
    x=math.sin(dlat/2)**2+math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(dlon/2)**2
    return R*2*math.atan2(math.sqrt(x),math.sqrt(1-x))

# Doctors
def get_docs(lat,lon):
    arr=[]
    for d in DOCTORS:
        dd=d.copy()
        dd['distance']=round(dist(lat,lon,d['lat'],d['lon']),1)
        arr.append(dd)
    return sorted(arr,key=lambda x:x['distance'])[:3]

# Medicines
def meds(p):
    m=set()
    for s in ['fever','cough','sweating','headache','fatigue','breathing','comorbidity']:
        if p.get(s):
            m.update(MED_DATA.get(s,[]))
    return list(m)

# Triage
def triage(p):
    s=0
    if p['age']>65:s+=3
    if p['fever']:s+=1
    if p['cough']:s+=1
    if p['breathing']:s+=3
    if p['comorbidity']:s+=2
    if p['sweating']:s+=1

    if s>=6:return "RED"
    if s>=3:return "YELLOW"
    return "GREEN"

def action(t):
    return {
        "RED":"🚨 Go hospital NOW",
        "YELLOW":"⚠️ Monitor",
        "GREEN":"✅ Home care"
    }[t]

# ROUTES

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect('/login')

    patients=load_patients()
    count={'RED':0,'YELLOW':0,'GREEN':0}
    for p in patients:
        count[p['triage']]+=1

    return render_template('index.html',patients=patients,counts=count)

@app.route('/add_patient',methods=['POST'])
def add_patient():
    if 'user_id' not in session:
        return redirect('/login')

    name=request.form.get('name','').strip()
    if not name:
        flash("Name required","danger")
        return redirect('/')

    p={
        'name':name,
        'age':int(request.form.get('age',30)),
        'fever':1 if 'fever' in request.form else 0,
        'cough':1 if 'cough' in request.form else 0,
        'sweating':1 if 'sweating' in request.form else 0,
        'headache':1 if 'headache' in request.form else 0,
        'fatigue':1 if 'fatigue' in request.form else 0,
        'breathing':1 if 'breathing' in request.form else 0,
        'comorbidity':1 if 'comorbidity' in request.form else 0,
        'lat':safe_float(request.form.get('lat'),18.5204),
        'lon':safe_float(request.form.get('lon'),73.8567),
        'notes':'',
        'timestamp':datetime.now().isoformat()
    }

    p['triage']=triage(p)
    p['action']=action(p['triage'])
    p['medicines']=meds(p)
    p['doctors']=get_docs(p['lat'],p['lon'])

    save_patient(p)
    flash("Patient added","success")
    return redirect('/')

@app.route('/update_notes',methods=['POST'])
def update_notes():
    pid=request.form.get('patient_id')
    notes=request.form.get('notes','')

    pts=load_patients()
    for p in pts:
        if str(p['id'])==str(pid):
            p['notes']=notes
            save_patient(p)
            break

    flash("Saved","success")
    return redirect('/')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=request.form['username']
        p=request.form['password']

        conn=sqlite3.connect('users.db')
        cur=conn.cursor()
        cur.execute("SELECT id,password FROM users WHERE username=?",(u,))
        user=cur.fetchone()
        conn.close()

        if user and check_password_hash(user[1],p):
            session['user_id']=user[0]
            return redirect('/')
        flash("Wrong login","danger")

    return render_template('login.html')

@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        u=request.form['username']
        p=request.form['password']

        conn=sqlite3.connect('users.db')
        cur=conn.cursor()
        try:
            cur.execute("INSERT INTO users VALUES(NULL,?,?)",
                        (u,generate_password_hash(p)))
            conn.commit()
        except:
            flash("User exists","danger")
            return redirect('/register')
        conn.close()
        return redirect('/login')

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__=='__main__':
    app.run(debug=True)