# main.py
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import sqlite3
import os
from pages.tekstnormalisering import tekstnormalisering_bp
from pages.resizer import resizer_bp
from pages.Sammenfletter import sammenfletter_bp

app = Flask(__name__)
# Ingen fil størrelse begrænsning - lad brugeren uploade så meget som de vil
# app.config["MAX_CONTENT_LENGTH"] = None  # Unlimited
app.config["SECRET_KEY"] = "your-secret-key-here-change-in-production"

# Initialize database for feedback
def init_database():
    try:
        # Use absolute path for database
        db_path = os.path.join(os.getcwd(), 'feedback.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                email TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        print(f"Database initialized at: {db_path}")
    except Exception as e:
        print(f"Database initialization error: {e}")

# Initialize database when app starts
init_database()

app.register_blueprint(tekstnormalisering_bp, url_prefix="/tekstnormalisering")
app.register_blueprint(resizer_bp, url_prefix="/resizer")
app.register_blueprint(sammenfletter_bp, url_prefix="/sammenfletter")

@app.route("/")
def home():
    return render_template("home.html", current_page="home")

@app.route("/test")
def test():
    return render_template("Test.html", current_page="test")

@app.route("/health")
def health_check():
    """Simple health check for debugging on Render"""
    try:
        import sqlite3
        db_path = os.path.join(os.getcwd(), 'feedback.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM feedback")
        count = cursor.fetchone()[0]
        conn.close()
        
        return f"""
        <h2>Health Check</h2>
        <p>✅ App is running</p>
        <p>✅ Database accessible</p>
        <p>✅ Feedback count: {count}</p>
        <p>✅ Database path: {db_path}</p>
        <p>✅ Current directory: {os.getcwd()}</p>
        <p><a href="/">Back to Home</a> | <a href="/admin/feedback">View Feedback</a></p>
        """
    except Exception as e:
        return f"""
        <h2>Health Check</h2>
        <p>❌ Error: {str(e)}</p>
        <p>📁 Current directory: {os.getcwd()}</p>
        <p>📁 Files: {os.listdir('.')}</p>
        <p><a href="/">Back to Home</a></p>
        """

@app.route("/admin/feedback")
def view_feedback():
    try:
        db_path = os.path.join(os.getcwd(), 'feedback.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT type, message, email, timestamp 
            FROM feedback 
            ORDER BY timestamp DESC
        ''')
        feedback_list = cursor.fetchall()
        conn.close()
        
        # Format for display
        formatted_feedback = []
        for row in feedback_list:
            formatted_feedback.append({
                'type': row[0],
                'message': row[1],
                'email': row[2] if row[2] else 'Anonymous',
                'timestamp': row[3]
            })
        
        return render_template('feedback_admin.html', feedback=formatted_feedback)
    except Exception as e:
        return f"Error reading feedback: {e}"

@app.route("/feedback", methods=["POST"])
def feedback():
    try:
        # Get form data
        feedback_type = request.form.get('type', '')
        message = request.form.get('message', '')
        user_email = request.form.get('email', 'Anonymous')
        
        # Validate required fields
        if not feedback_type or not message.strip():
            return redirect(request.referrer + '?error=missing_fields')
        
        # Feedback type labels
        type_labels = {
            'bug': 'Bug Report',
            'feature': 'Feature Request', 
            'improvement': 'Improvement',
            'other': 'Other Feedback'
        }
        
        # Save to database (works on Render and locally)
        try:
            db_path = os.path.join(os.getcwd(), 'feedback.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO feedback (type, message, email) 
                VALUES (?, ?, ?)
            ''', (feedback_type, message, user_email))
            conn.commit()
            conn.close()
            print(f"Feedback saved to database: {type_labels.get(feedback_type, feedback_type)} from {user_email}")
        except Exception as db_error:
            print(f"Database error: {db_error}")
            # If database fails, still log the feedback in console
            print(f"FEEDBACK: {feedback_type} from {user_email}: {message}")
        
        # Also save to text file for local development
        try:
            log_entry = f"""
{'='*70}
FEEDBACK RECEIVED: {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}
{'='*70}
Type: {type_labels.get(feedback_type, feedback_type)}
From: {user_email}
Message:
{message}
{'='*70}

"""
            with open('feedback_messages.txt', 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as file_error:
            print(f"File write error (normal on Render): {file_error}")
        
        return redirect(request.referrer + '?success=sent')
        
    except Exception as e:
        print(f"Feedback error: {e}")
        return redirect(request.referrer + '?error=send_failed')

if __name__ == "__main__":
    app.run(debug=True)