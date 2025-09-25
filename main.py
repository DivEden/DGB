# main.py
from flask import Flask, render_template  
from pages.tekstnormalisering import tekstnormalisering_bp
from pages.resizer import resizer_bp
from pages.Sammenfletter import sammenfletter_bp

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
app.config["SECRET_KEY"] = "your-secret-key-here-change-in-production"  
app.register_blueprint(tekstnormalisering_bp, url_prefix="/tekstnormalisering")
app.register_blueprint(resizer_bp, url_prefix="/resizer")
app.register_blueprint(sammenfletter_bp, url_prefix="/sammenfletter")

@app.route("/")
def home():
    return render_template("home.html", current_page="home")

if __name__ == "__main__":
    app.run(debug=True)