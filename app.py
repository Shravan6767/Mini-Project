print("APP STARTING...")

import os
import requests
import random
from flask import Flask, render_template, request, redirect, session, flash
from dotenv import load_dotenv
from pymongo import MongoClient
import google.generativeai as genai
from PIL import Image
from werkzeug.utils import secure_filename

# ===================== CONFIGURATION =====================
load_dotenv() # Moved to the top to ensure variables load first

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "secret123")

# MongoDB Connection
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client.farm_database
# Using 'users' to match your route logic
users = db.users 

# Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_KEY", "AQ.Ab8RN6LpjKkqpkGJ-DRR_sSCtb1zPWV_gKehm-OBXkh7xkrMJQ")
genai.configure(api_key=GEMINI_API_KEY)

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

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(file.filename))
    file.save(filepath)

    try:
        img = Image.open(filepath)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        prompt = """
        Analyze this agricultural image. 
        If it's NOT a crop/plant, respond ONLY with: NOT_CROP
        If it IS a crop, respond strictly in this format:
        Crop: <name of crop>
        Condition: <Describe health in 3-5 words>
        Advice: <One short farming tip>
        """

        response = model.generate_content([prompt, img])
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

    try:
        # Check if user already exists
        if users.find_one({"email": email}):
            flash("Email already registered")
            return redirect('/user')
            
        users.insert_one({
            "email": email, 
            "username": username, 
            "password": password
        })
        flash("Account Created Successfully")
    except Exception as e:
        flash("Error creating account.")
        print(f"Signup Error: {e}")

    return redirect('/user')

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()

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
    # Removed use_reloader=False for easier local development
    app.run(debug=True, port=5002)