# main.py
from flask import Flask
from pages.tekstnormalisering import tekstnormalisering_bp

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB uploads (juster efter behov)
app.config["SECRET_KEY"] = "your-secret-key-here-change-in-production"  # Tilføj secret key
app.register_blueprint(tekstnormalisering_bp, url_prefix="/tekstnormalisering")

@app.route("/", methods=["GET"])
def home():
    return """\
    <html>
      <head><title>Flask app</title></head>
      <body style="font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; padding: 24px;">
        <h1>Flask app</h1>
        <p>Værktøjer:</p>
        <ul>
          <li><a href="/tekstnormalisering">🗂️ Arkivnummer-normalisering</a></li>
        </ul>
      </body>
    </html>
    """

if __name__ == "__main__":
    # Brug host="0.0.0.0" hvis du vil kunne tilgå den fra andre enheder på netværket
    app.run(debug=True)
