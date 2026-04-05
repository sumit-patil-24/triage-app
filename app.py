from flask import Flask, render_template, request, redirect, url_for
import joblib
import os

app = Flask(__name__)

# Load model safely
MODEL_PATH = "triage_model.joblib"

if not os.path.exists(MODEL_PATH):
    raise Exception("❌ Model file not found. Run train_model.py first.")

model = joblib.load(MODEL_PATH)

patients = []

priority_order = {"RED": 1, "YELLOW": 2, "GREEN": 3}

# ML prediction
def triage_patient(age, fever, sweating, cough, comorbidity):
    features = [[age, fever, sweating, cough, comorbidity]]
    return model.predict(features)[0]

@app.route('/', methods=['GET', 'POST'])
def index():
    filter_priority = request.args.get('filter_priority', 'ALL')
    search_name = request.args.get('search_name', '').lower()

    if request.method == 'POST':

        # ✅ Notes update (handled separately)
        if 'update_notes' in request.form:
            idx = int(request.form['patient_index'])
            patients[idx]['notes'] = request.form.get('notes', '')
            return redirect(url_for('index', filter_priority=filter_priority, search_name=search_name))

        # ✅ New patient
        name = request.form.get('name')
        age = int(request.form.get('age'))

        fever = 1 if 'fever' in request.form else 0
        sweating = 1 if 'sweating' in request.form else 0
        cough = 1 if 'cough' in request.form else 0
        comorbidity = 1 if 'comorbidity' in request.form else 0

        triage = triage_patient(age, fever, sweating, cough, comorbidity)

        patients.append({
            "name": name,
            "age": age,
            "fever": fever,
            "sweating": sweating,
            "cough": cough,
            "comorbidity": comorbidity,
            "triage": triage,
            "notes": ""
        })

        return redirect(url_for('index', filter_priority=filter_priority, search_name=search_name))

    # Prepare data
    data = list(enumerate(patients))

    # Filter
    if filter_priority != 'ALL':
        data = [p for p in data if p[1]['triage'] == filter_priority]

    # Search
    if search_name:
        data = [p for p in data if search_name in p[1]['name'].lower()]

    # Sort
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

if __name__ == "__main__":
    app.run(debug=True)