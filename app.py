import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, session, send_from_directory
from pymongo import MongoClient
from bson import ObjectId
import hashlib
import datetime

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = os.getenv("SECRET_KEY", "mentorconnect2026")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client    = MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True)
db        = client["mentor_connect"]

users_col    = db["users"]
sessions_col = db["sessions"]
reviews_col  = db["reviews"]

def hash_pw(p):
    return hashlib.sha256(p.encode()).hexdigest()

def logged_in():
    return "user_id" in session

@app.route("/")
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "index.html")

@app.route("/<path:f>")
def static_files(f):
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), f)

@app.route("/test-db")
def test_db():
    try:
        client.admin.command('ping')
        return jsonify({"status": "Connected!", "users": users_col.count_documents({})}), 200
    except Exception as e:
        return jsonify({"status": "Not Connected", "error": str(e)}), 500

@app.route("/register", methods=["POST"])
def register():
    d        = request.get_json()
    name     = d.get("name","").strip()
    email    = d.get("email","").strip().lower()
    password = d.get("password","")
    role     = d.get("role","mentee")
    skills   = d.get("skills",[])
    bio      = d.get("bio","").strip()
    if not name or not email or not password:
        return jsonify({"error":"Please fill all fields."}), 400
    if len(password) < 6:
        return jsonify({"error":"Password min 6 characters."}), 400
    if users_col.find_one({"email":email}):
        return jsonify({"error":"Email already registered."}), 409
    result = users_col.insert_one({
        "name":name,"email":email,"password":hash_pw(password),
        "role":role,"skills":skills,"bio":bio,
        "rating":0.0,"review_count":0,
        "created_at":datetime.datetime.utcnow()
    })
    session["user_id"] = str(result.inserted_id)
    session["name"]    = name
    session["role"]    = role
    return jsonify({"message":f"Welcome, {name}!","name":name,"role":role}), 201

@app.route("/login", methods=["POST"])
def login():
    d     = request.get_json()
    email = d.get("email","").strip().lower()
    pw    = d.get("password","")
    user  = users_col.find_one({"email":email,"password":hash_pw(pw)})
    if not user:
        return jsonify({"error":"Wrong email or password."}), 401
    session["user_id"] = str(user["_id"])
    session["name"]    = user["name"]
    session["role"]    = user["role"]
    return jsonify({"message":f"Welcome back, {user['name']}!","name":user["name"],"role":user["role"]}), 200

@app.route("/logout")
def logout():
    session.clear()
    return jsonify({"message":"Logged out."}), 200

@app.route("/me")
def me():
    if not logged_in():
        return jsonify({"error":"Not logged in."}), 401
    user = users_col.find_one({"_id":ObjectId(session["user_id"])},{"password":0})
    if not user:
        session.clear()
        return jsonify({"error":"User not found."}), 404
    return jsonify({"id":str(user["_id"]),"name":user["name"],"email":user["email"],
                    "role":user["role"],"skills":user.get("skills",[]),
                    "bio":user.get("bio",""),"rating":user.get("rating",0.0),
                    "review_count":user.get("review_count",0)}), 200

@app.route("/mentors")
def get_mentors():
    q     = request.args.get("q","").strip()
    query = {"role":"mentor"}
    if q:
        query["$or"] = [{"name":{"$regex":q,"$options":"i"}},
                        {"skills":{"$regex":q,"$options":"i"}},
                        {"bio":{"$regex":q,"$options":"i"}}]
    mentors = list(users_col.find(query,{"password":0}))
    return jsonify([{"id":str(m["_id"]),"name":m["name"],"skills":m.get("skills",[]),
                     "bio":m.get("bio","No bio."),"rating":round(m.get("rating",0.0),1),
                     "review_count":m.get("review_count",0)} for m in mentors]), 200

@app.route("/book", methods=["POST"])
def book():
    if not logged_in():
        return jsonify({"error":"Please log in."}), 401
    d         = request.get_json()
    mentor_id = d.get("mentor_id","")
    date_str  = d.get("date","")
    time_str  = d.get("time","")
    topic     = d.get("topic","").strip()
    if not mentor_id or not date_str or not time_str:
        return jsonify({"error":"Provide mentor, date, time."}), 400
    try:
        mentor = users_col.find_one({"_id":ObjectId(mentor_id),"role":"mentor"})
    except:
        return jsonify({"error":"Invalid mentor ID."}), 400
    if not mentor:
        return jsonify({"error":"Mentor not found."}), 404
    try:
        scheduled_at = datetime.datetime.strptime(f"{date_str} {time_str}","%Y-%m-%d %H:%M")
    except:
        return jsonify({"error":"Invalid date/time."}), 400
    if sessions_col.find_one({"mentor_id":mentor_id,"scheduled_at":scheduled_at,"status":{"$ne":"cancelled"}}):
        return jsonify({"error":"Slot already booked."}), 409
    sessions_col.insert_one({
        "mentee_id":session["user_id"],"mentee_name":session["name"],
        "mentor_id":mentor_id,"mentor_name":mentor["name"],
        "topic":topic or "General Session","scheduled_at":scheduled_at,
        "status":"upcoming","created_at":datetime.datetime.utcnow()
    })
    return jsonify({"message":f"Session booked with {mentor['name']}!"}), 201

@app.route("/my-sessions")
def my_sessions():
    if not logged_in():
        return jsonify({"error":"Please log in."}), 401
    uid   = session["user_id"]
    role  = session["role"]
    query = {"mentee_id":uid} if role=="mentee" else {"mentor_id":uid}
    raw   = list(sessions_col.find(query).sort("scheduled_at",1))
    return jsonify([{"id":str(s["_id"]),"mentor_name":s.get("mentor_name",""),
                     "mentee_name":s.get("mentee_name",""),"topic":s.get("topic","General"),
                     "scheduled_at":s["scheduled_at"].strftime("%d %b %Y at %I:%M %p"),
                     "status":s.get("status","upcoming")} for s in raw]), 200

@app.route("/cancel-session/<sid>", methods=["POST"])
def cancel_session(sid):
    if not logged_in():
        return jsonify({"error":"Please log in."}), 401
    try:
        sess = sessions_col.find_one({"_id":ObjectId(sid)})
    except:
        return jsonify({"error":"Invalid ID."}), 400
    if not sess:
        return jsonify({"error":"Session not found."}), 404
    uid = session["user_id"]
    if sess["mentee_id"]!=uid and sess["mentor_id"]!=uid:
        return jsonify({"error":"Not authorized."}), 403
    sessions_col.update_one({"_id":ObjectId(sid)},{"$set":{"status":"cancelled"}})
    return jsonify({"message":"Session cancelled."}), 200

if __name__ == "__main__":
    app.run(debug=True)
