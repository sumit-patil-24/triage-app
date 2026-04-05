import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import joblib

data = pd.DataFrame([
    [65,1,1,1,1,"RED"],
    [30,1,1,0,0,"YELLOW"],
    [25,0,0,0,0,"GREEN"],
    [70,1,0,1,1,"RED"],
    [40,1,1,1,0,"YELLOW"],
    [20,0,0,1,0,"GREEN"],
])

data.columns = ["age","fever","sweating","cough","comorbidity","triage"]

X = data.drop("triage", axis=1)
y = data["triage"]

model = RandomForestClassifier(n_estimators=100)
model.fit(X, y)

joblib.dump(model, "triage_model.joblib")

print("✅ Model ready")