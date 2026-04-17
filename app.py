print("APP STARTING...")

import os
import random
from flask import Flask, render_template, request, redirect, session, flash
from dotenv import load_dotenv
from pymongo import MongoClient
from google import genai 
from PIL import Image
from werkzeug.utils import secure_filename

# ===================== CONFIGURATION =====================
load_dotenv() 

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "farm_secret_789")

# --- MongoDB Connection ---
MONGO_URI = os.getenv("MONGO_URI")
users = None

if MONGO_URI:
    try:
        # 5-second timeout to prevent the app from hanging if DB is down
        client_db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client_db.farm_database
        users = db.users
        client_db.admin.command('ping')
        print("MongoDB Connected Successfully!")
    except Exception as e:
        print(f"MongoDB Connection Error: {e}")
else:
    print("CRITICAL: MONGO_URI missing from environment variables!")

# --- Gemini Configuration (OAuth 2 Fix) ---
GEMINI_API_KEY = os.getenv("GEMINI_KEY")
client_ai = None

if GEMINI_API_KEY:
    # vertexai=False ensures we use the API key directly (Developer Mode)
    client_ai = genai.Client(api_key=GEMINI_API_KEY, vertexai=False)
    print("Gemini AI Client Ready.")

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===================== NAVIGATION ROUTES =====================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/schemes')
def schemes():
    # Example schemes data; you can also fetch this from MongoDB
    farm_schemes = [
        {"name": "PM-Kisan", "detail": "Direct income support of ₹6,000/year."},
        {"name": "Crop Insurance", "detail": "Protection against natural calamities."},
        {"name": "Soil Health Card", "detail": "Free soil testing and nutrient advice."}
    ]
    return render_template('schemes.html', schemes=farm_schemes)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        message = request.form.get('message')
        # Saving messages to a local file for admin to see
        with open("messages.txt", "a") as f:
            f.write(f"{name}|{message}\n")
        return render_template("contact.html", success=True)
    return render_template("contact.html")

# ===================== AI UPLOAD SYSTEM =====================

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('image')
    if not file or file.filename == "":
        return "No file selected"

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    if not client_ai:
        return "AI Error: API Key not configured."

    try:
        img = Image.open(filepath)
        prompt = "Analyze this agricultural image. Identify the crop and condition. Respond with 'Crop: [name]', 'Condition: [status]', and 'Advice: [tip]'."

        response = client_ai.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[prompt, img]
        )
        
        output = response.text.strip().replace("*", "")
        
        # Default analysis values
        analysis = {"health": "Unknown", "condition": "Processing Error", "fertilizer": "N/A", "harvest": "N/A"}

        # Parsing logic for AI response
        lines = output.split('\n')
        for line in lines:
            if ":" in line:
                key, val = line.split(":", 1)
                k = key.lower()
                if "crop" in k: analysis["health"] = val.strip()
                elif "condition" in k: analysis["condition"] = val.strip()
                elif "advice" in k: analysis["harvest"] = val.strip()

        return render_template("result.html", image=filepath, result=analysis)
    except Exception as e:
        return f"AI Error: {str(e)}"

# ===================== USER AUTH SYSTEM =====================

@app.route('/user')
def user_page():
    return render_template("user_login.html")

@app.route('/login', methods=['POST'])
def login():
    if not users:
        return "DB offline: Please check MongoDB Network Access/Whitelist."
    
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    user = users.find_one({"email": email, "password": password})

    if user:
        session['user'] = user['username']
        return redirect('/user_dashboard')
    
    flash("Invalid Login Details")
    return redirect('/user')

@app.route('/create_account', methods=['POST'])
def create_account():
    if not users:
        return "DB offline: Cannot create account right now."
    
    email = request.form.get('email', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if users.find_one({"email": email}):
        flash("Email already registered")
        return redirect('/user')

    users.insert_one({"email": email, "username": username, "password": password})
    flash("Account Created Successfully!")
    return redirect('/user')

@app.route('/user_dashboard')
def user_dashboard():
    if 'user' in session:
        return render_template("user_dashboard.html", user=session['user'])
    return redirect('/user')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ===================== RUN APP =====================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host='0.0.0.0', port=port, debug=True)
