import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib
import json

# Generate synthetic training data
np.random.seed(42)
n_samples = 10000

data = {
    'age': np.random.randint(18, 90, n_samples),
    'fever': np.random.choice([0, 1], n_samples, p=[0.7, 0.3]),
    'sweating': np.random.choice([0, 1], n_samples, p=[0.8, 0.2]),
    'cough': np.random.choice([0, 1], n_samples, p=[0.6, 0.4]),
    'comorbidity': np.random.choice([0, 1], n_samples, p=[0.85, 0.15])
}

# Generate realistic labels
def generate_triage(row):
    score = 0
    if row['age'] > 65: score += 2
    if row['fever']: score += 1
    if row['cough']: score += 1
    if row['sweating']: score += 1
    if row['comorbidity']: score += 2
    
    if score >= 4: return 'RED'
    elif score >= 2: return 'YELLOW'
    return 'GREEN'

df = pd.DataFrame(data)
df['triage'] = df.apply(generate_triage, axis=1)

# Encode labels
label_map = {'GREEN': 0, 'YELLOW': 1, 'RED': 2}
df['label'] = df['triage'].map(label_map)

# Train model
X = df[['age', 'fever', 'sweating', 'cough', 'comorbidity']]
y = df['label']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Evaluate
y_pred = model.predict(X_test)
print("Model Performance:")
print(classification_report(y_test, y_pred, target_names=list(label_map.keys())))

# Save model
joblib.dump(model, 'triage_model.joblib')
print("✅ Model saved as 'triage_model.joblib'")

# Save label map
with open('label_map.json', 'w') as f:
    json.dump(label_map, f)