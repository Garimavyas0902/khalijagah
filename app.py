from flask import Flask, render_template, request, redirect, url_for, session, send_file
import google.generativeai as genai
import re
import mysql.connector
import os
from io import BytesIO
from xhtml2pdf import pisa
from dotenv import load_dotenv
  
load_dotenv()

app = Flask(__name__)  

GEMINI_API_KEY = "AIzaSyB9CinM07uAUbr6WXNrmAcKFScU0PYdOdo"
genai.configure(api_key=GEMINI_API_KEY)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

model = genai.GenerativeModel(model_name="models/gemini-1.5-pro-latest")
  
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'mydatabase',
    'port': 3307
}

def connect_db():
    try:
        cnx = mysql.connector.connect(**DB_CONFIG)
        return cnx
    except mysql.connector.Error as err:
        print(f"Error connecting to MySQL: {err}")
        return None

def close_db(cnx):
    if cnx and cnx.is_connected():
        cnx.close()

@app.route("/")
def splash():
    return render_template("splash.html")

@app.route("/home")
def home():
    return render_template("home.html")

@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            error = "Please enter both username and password."
            return render_template("auth.html", error=error, show_login=True)

        cnx = connect_db()
        if cnx:
            cursor = cnx.cursor()
            query = "SELECT id, username, password FROM users WHERE username = %s"
            cursor.execute(query, (username,))
            user = cursor.fetchone()
            cursor.close()
            close_db(cnx)

            if user:
                user_id, db_username, db_password = user
                if password == db_password:
                    session['user_id'] = user_id
                    session['username'] = db_username
                    return redirect(url_for('index'))
                else:
                    error = "Incorrect password."
            else:
                error = "User not found."
        else:
            error = "Database connection error."

        return render_template("auth.html", error=error, show_login=True)

    return render_template("auth.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if not username or not email or not password:
            error = "All fields are required."
            return render_template("auth.html", error=error, show_signup=True)

        cnx = connect_db()
        if cnx:
            cursor = cnx.cursor()
            check_query = "SELECT id FROM users WHERE username = %s OR email = %s"
            cursor.execute(check_query, (username, email))
            existing_user = cursor.fetchone()

            if existing_user:
                error = "Username or email already exists."
            else:
                insert_query = "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)"
                try:
                    cursor.execute(insert_query, (username, email, password))
                    cnx.commit()
                    cursor.close()
                    close_db(cnx)
                    return redirect(url_for('auth'))
                except mysql.connector.Error as err:
                    error = f"Error registering user: {err}"
            cursor.close()
            close_db(cnx)
        else:
            error = "Database connection error."

        return render_template("auth.html", error=error, show_signup=True)

    return render_template("auth.html")

@app.route("/index")
def index():
    if 'username' in session:
        return render_template("index.html", username=session['username'])
    return redirect(url_for('auth'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('auth'))

@app.route("/process", methods=["POST"])
def process():
    if request.method == "POST":
        name = request.form["name"]
        age = request.form.get("age")
        education = request.form["education"]
        skills = request.form["skills"]
        interests = request.form["interests"]

        prompt = f"""
        I have the following details about a person:
        Name: {name}
        Age: {age}
        Education Level: {education}
        Skills: {skills}
        Interests: {interests}

        Based on this information, what are the top 3 career options that would be the best fit?
        Also briefly explain why each one is a good match.
        """

        try:
            response = model.generate_content(prompt)
            raw_text = response.text
            career_items = re.split(r'\n?\s*\d+\.\s*', raw_text)
            career_items = [item.strip() for item in career_items if item.strip()]

            career_items_formatted = []
            for item in career_items:
                title_match = re.match(r"^(.*?):", item)
                if title_match:
                    title = title_match.group(1)
                    formatted_title = f"<strong><u>{title}</u></strong>:"
                    item = item.replace(title, formatted_title, 1)
                career_items_formatted.append(f"<li>{item}</li>")

            recommendation = "<ol>" + "".join(career_items_formatted) + "</ol>"
            session['recommendation'] = recommendation
            return redirect(url_for('recommendation_page'))
        except Exception as e:
            session['error'] = f"Error: {str(e)}"
            return redirect(url_for('recommendation_page'))

@app.route("/recommendation")
def recommendation_page():
    recommendation = session.get('recommendation')
    error = session.get('error')

    return render_template("recommendation.html", recommendation=recommendation, error=error)

@app.route("/download_pdf")
def download_pdf():
    recommendation = session.get('recommendation', None)
    if not recommendation:
        return redirect(url_for('index'))

    html = render_template("pdf_template.html", recommendation=recommendation)
    pdf_stream = BytesIO()
    result = pisa.CreatePDF(html, dest=pdf_stream)

    if result.err:
        return "Failed to generate PDF", 500

    pdf_stream.seek(0)
    return send_file(
        pdf_stream,
        as_attachment=True,
        download_name="career_recommendation.pdf",
        mimetype='application/pdf'
    )

if __name__ == "__main__":
    app.run(debug=True)
