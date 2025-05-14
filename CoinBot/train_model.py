# train_model.py
import pandas as pd
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from lightgbm import LGBMClassifier

# Veriyi yükle
df = pd.read_csv("news_train.csv")
X_text = df["text"]
y = df["label"]

# TF-IDF + Model eğitimi
vectorizer = TfidfVectorizer(max_features=1000)
X = vectorizer.fit_transform(X_text)
model = LGBMClassifier(n_estimators=100, num_leaves=31, min_data_in_leaf=1)
model.fit(X, y)

# Kaydet
joblib.dump(model, "news_model.pkl")
joblib.dump(vectorizer, "vectorizer.pkl")

print("✅ Model ve vectorizer kaydedildi.")