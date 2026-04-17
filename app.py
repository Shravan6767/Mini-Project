print("APP STARTING...")

import os
import requests
import random
from flask import Flask, render_template, request, redirect, session, flash
from dotenv import load_dotenv
from pymongo import MongoClient
from google import genai  # Modern 2026 SDK
from PIL import Image
from werkzeug.utils import secure_filename

# ===================== CONFIGURATION =====================
load_dotenv() 

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "secret123")

# --- MongoDB Connection ---
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    print("CRITICAL ERROR: MONGO_URI is not set!")
    client_db = None
    users = None
else:
    try:
        client_db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client_db.farm_database
        users = db.users
        client_db.admin.command('ping')
        print("MongoDB Connected Successfully!")
    except Exception as e:
        print(f"MongoDB Connection Error: {e}")
        client_db = None
        users = None

# --- Gemini Configuration (Modern Client Style) ---
GEMINI_API_KEY = os.getenv("GEMINI_KEY")
if GEMINI_API_KEY:
    # This Client structure handles the AQ. key format correctly
    client_ai = genai.Client(api_key=GEMINI_API_KEY)
else:
    print("WARNING: GEMINI_KEY is missing!")
    client_ai = None

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===================== ROUTES =====================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('image')
    if not file or file.filename == "":
        return "No file selected"

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    try:
        img = Image.open(filepath)
        
        prompt = """
        Analyze this agricultural image. 
        If it's NOT a crop/plant, respond ONLY with: NOT_CROP
        If it IS a crop, respond strictly in this format:
        Crop: <name of crop>
        Condition: <Describe health in 3-5 words>
        Advice: <One short farming tip>
        """

        # Using the new contents-based generation for 2026
        response = client_ai.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[prompt, img]
        )
        
        output = response.text.strip().replace("*", "")

        fertilizers = [
            "NPK 19-19-19", "Urea (46% Nitrogen)", "DAP (Diammonium Phosphate)", 
            "Organic Neem Cake", "Potash (MOP)", "Ammonium Sulphate", 
            "Compost Manure", "Zinc Sulphate"
        ]
        
        analysis = {
            "health": "N/A",
            "condition": "N/A",
            "fertilizer": random.choice(fertilizers),
            "harvest": f"{random.randint(75, 98)}%"
        }

        if "NOT_CROP" in output.upper():
            analysis = {
                "health": "Invalid Image",
                "condition": "Please upload a crop image",
                "fertilizer": "None",
                "harvest": "0%"
            }
        else:
            lines = output.split('\n')
            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    k = key.lower()
                    v = value.strip()
                    if "crop" in k:
                        analysis["health"] = v
                    elif "condition" in k:
                        analysis["condition"] = v
                    elif "advice" in k:
                        analysis["harvest"] = f"{analysis['harvest']} - {v}"

        return render_template("result.html", image=filepath, result=analysis)

    except Exception as e:
        print(f"AI Error Logs: {str(e)}")
        return f"AI Error: {str(e)}"

# ===================== ADMIN SYSTEM =====================

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if email == "admin@farmday.com" and password == "1234":
            session['admin'] = True
            return redirect('/dashboard')
        return render_template("admin_login.html", error="Invalid Credentials")
    return render_template("admin_login.html")

@app.route('/dashboard')
def dashboard():
    if not session.get('admin'):
        return redirect('/admin')

    messages = []
    if os.path.exists("messages.txt"):
        with open("messages.txt", "r") as f:
            for line in f:
                parts = line.strip().split("|")
                if len(parts) >= 2:
                    messages.append({"name": parts[0], "message": parts[1]})
    return render_template("dashboard.html", messages=messages)

# ===================== USER SYSTEM =====================

@app.route('/create_account', methods=['POST'])
def create_account():
    email = request.form.get('email', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not users:
        flash("Database offline.")
        return redirect('/user')

    try:
        if users.find_one({"email": email}):
            flash("Email already registered")
            return redirect('/user')
            
        users.insert_one({"email": email, "username": username, "password": password})
        flash("Account Created Successfully")
    except Exception as e:
        flash("Error creating account.")
        print(f"Signup Error: {e}")

    return redirect('/user')

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()

    if not users:
        flash("Database offline.")
        return redirect('/user')

    user = users.find_one({"email": email, "password": password})

    if user:
        session['user'] = user['username']
        return redirect('/user_dashboard')

    flash("Invalid Login Details")
    return redirect('/user')

@app.route('/user_dashboard')
def user_dashboard():
    if 'user' in session:
        return render_template("user_dashboard.html", user=session['user'])
    return redirect('/user')

@app.route('/user')
def user_page():
    return render_template("user_login.html")

# ===================== HELPERS =====================

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.context_processor
def inject_user():
    return dict(current_user=session.get('user'))

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        message = request.form.get('message')
        with open("messages.txt", "a") as f:
            f.write(f"{name}|{message}|\n")
        return render_template("contact.html", success=True)
    return render_template("contact.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host='0.0.0.0', port=port, debug=True)
