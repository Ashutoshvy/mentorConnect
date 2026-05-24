# Mentor Connect

## Local Run Karo:
pip install -r requirements.txt
python app.py

## Deploy (Render):
Environment Variables:
- MONGO_URI = mongodb+srv://mentoruser:Mentor2026@cluster0.yjrqtjh.mongodb.net/mentor_connect?retryWrites=true&w=majority&appName=Cluster0
- SECRET_KEY = mentorconnect2026sviit

Start Command: gunicorn app:app
