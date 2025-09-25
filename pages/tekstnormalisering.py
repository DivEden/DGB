# pages/tekstnormalisering.py
import io
import re
from typing import List, Dict, Optional

import pandas as pd
from flask import Blueprint, request, render_template_string, send_file, redirect, url_for

tekstnormalisering_bp = Blueprint("tekstnormalisering", __name__)

# ---------- Hjælpefunktioner ----------
def pad_left_ignoring_letters(part: str, target_digits: int) -> str:
    """Foranstil nuller, indtil antallet af cifre (0-9) når target_digits. Bogstaver bevares."""
    if part is None:
        return part
    digit_count = len(re.findall(r"\d", str(part)))
    if digit_count >= target_digits:
        return str(part)
    zeros_needed = target_digits - digit_count
    return "0" * zeros_needed + str(part)

def normalize_token(token: str) -> str:
    if token is None:
        return token
    s = str(token).strip()
    if not s:
        return s

    # x/X-regel: 4 cifre på hver side (ingen kolon til stede)
    if ("x" in s or "X" in s) and ":" not in s:
        parts = re.split(r"[xX]", s, maxsplit=1)
        if len(parts) == 2:
            left, right = parts
            left_padded = pad_left_ignoring_letters(left, 4)
            right_padded = pad_left_ignoring_letters(right, 4)
            sep_match = re.search(r"[xX]", s)
            sep = sep_match.group(0) if sep_match else "x"
            return f"{left_padded}{sep}{right_padded}"

    # Kolon-regel: 5 cifre før :
    if ":" in s:
        left, right = s.split(":", 1)
        left_padded = pad_left_ignoring_letters(left, 5)
        return f"{left_padded}:{right}"

    # Hvis ingen regel passer, returnér uændret
    return s

def split_tokens(text: str) -> List[str]:
    if text is None:
        return []
    raw = re.split(r"[,\s;]+", text.strip())
    return [t for t in raw if t]

def guess_column(df: pd.DataFrame) -> Optional[str]:
    if df is None or df.empty:
        return None
    lowered = {c: str(c).lower() for c in df.columns}
    for key in ("nummer", "objekt", "id", "arkiv"):
        for col, low in lowered.items():
            if key in low:
                return col
    return df.columns[0]

# ---------- HTML-skabelon ----------
PAGE_HTML = r"""
<!doctype html>
<html lang="da">
<head>
  <meta charset="utf-8" />
  <title>Arkivnummer-normalisering</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root{
      --bg:#f8fafc; --panel:#fff; --muted:#475569; --border:#e2e8f0; --accent:#2563eb;
    }
    html, body { background: var(--bg); color:#0f172a; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
    .wrap { max-width: 980px; margin: 24px auto; padding: 0 16px; }
    .card { background: var(--panel); border:1px solid var(--border); border-radius:12px; box-shadow: 0 4px 10px rgba(0,0,0,.05); padding:16px; margin-bottom:16px; }
    h1,h2,h3 { margin: 0 0 8px 0; }
    .tabs { display:flex; gap:8px; margin-bottom:12px; }
    .tab a { display:inline-block; padding:8px 12px; border:1px solid var(--border); border-radius:999px; text-decoration:none; color:#0f172a; background:#f1f5f9; }
    .tab a.active { background:#e0e7ff; border-color:#c7d2fe; color:#1d4ed8; }
    .row { display:flex; gap:16px; flex-wrap: wrap; }
    .col { flex: 1 1 0; min-width: 280px; }
    textarea, input[type="text"], select { width:100%; box-sizing:border-box; padding:8px; border:1px solid var(--border); border-radius:8px; font: inherit; }
    button { background:linear-gradient(#3b82f6,#2563eb); color:#fff; border:1px solid #2563eb; border-radius:10px; padding:8px 12px; cursor:pointer; font-weight:600; }
    button.secondary { background:#f8fafc; color:#0f172a; border:1px solid var(--border); }
    .muted{ color:#64748b; font-size: 0.95rem; }
    table { border-collapse: collapse; width:100%; }
    th, td { border:1px solid var(--border); padding:6px 8px; text-align:left; }
    .pill { display:inline-block; background:#f1f5f9; border:1px solid var(--border); border-radius:999px; padding:3px 8px; font-size:12px; color:#475569; }
    .spacer{ height:8px; }
    .alert{ padding:10px 12px; background:#fff7ed; border:1px solid #ffedd5; color:#9a3412; border-radius:8px; }
    .success{ padding:10px 12px; background:#ecfdf5; border:1px solid #bbf7d0; color:#065f46; border-radius:8px; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>🗂️ Arkivnummer-normalisering</h1>
    <p class="muted">Vælg fanen <b>Tekst</b> eller <b>Excel</b> herunder. Regler:
      <span class="pill">":" → 5 cifre før kolon (bogstaver tæller ikke)</span>
      <span class="pill">"x/X" → 4 cifre på hver side</span>
    </p>

    <div class="tabs">
      <div class="tab"><a href="{{ url_for('tekstnormalisering.view', tab='text') }}" class="{{ 'active' if tab=='text' else '' }}">Tekst</a></div>
      <div class="tab"><a href="{{ url_for('tekstnormalisering.view', tab='excel') }}" class="{{ 'active' if tab=='excel' else '' }}">Excel</a></div>
    </div>

    {% if tab == 'text' %}
    <div class="card">
      <h2>Tekst</h2>
      <form method="post" action="{{ url_for('tekstnormalisering.view', tab='text') }}">
        <div class="row">
          <div class="col">
            <label for="inp">Indsæt numre her:</label>
            <textarea id="inp" name="inp" rows="10" placeholder="Ét pr. linje eller adskilt med mellemrum/komma/semikolon">{{ inp or '' }}</textarea>
          </div>
          <div class="col">
            <div><span class="muted">Tip: Indsæt rå data til venstre og klik <b>Normalisér</b>.</span></div>
          </div>
        </div>
        <div class="spacer"></div>
        <button type="submit">Normalisér</button>
      </form>
    </div>

    {% if tokens is not none %}
    <div class="card">
      <h3>Resultat (én pr. linje)</h3>
      <textarea rows="10" readonly>{{ normalized | join('\n') }}</textarea>
    </div>
    <div class="card">
      <h3>Opslag (før → efter)</h3>
      <textarea rows="10" readonly>{% for a,b in pairs %}{{ a }} → {{ b }}
{% endfor %}</textarea>
    </div>
    <div class="card">
      <h3>🔎 SARA-søgning</h3>
      <textarea rows="4" readonly>{{ sara_query }}</textarea>
    </div>
    {% endif %}
    {% endif %}

    {% if tab == 'excel' %}
    <div class="card">
      <h2>Excel</h2>
      <form method="post" action="{{ url_for('tekstnormalisering.view', tab='excel') }}" enctype="multipart/form-data">
        <div class="row">
          <div class="col">
            <label for="excel">Upload Excel-fil (.xlsx/.xls)</label>
            <input type="file" id="excel" name="excel" accept=".xlsx,.xls" />
          </div>
          <div class="col">
            <label for="add_mapping">Ekstra "Mapping"-ark (før/efter)?</label>
            <select id="add_mapping" name="add_mapping">
              <option value="yes" {% if add_mapping=='yes' %}selected{% endif %}>Ja</option>
              <option value="no" {% if add_mapping=='no' %}selected{% endif %}>Nej</option>
            </select>
          </div>
        </div>
        <div class="spacer"></div>
        <button type="submit">Normalisér Excel</button>
      </form>
      <p class="muted">Vi læser første ark og gætter en relevant kolonne (kan ændres i næste trin, hvis nødvendigt).</p>
    </div>

    {% if preview is not none %}
      <div class="card">
        <h3>Forhåndsvisning (før)</h3>
        {{ preview|safe }}
      </div>

      {% if guessed_col %}
      <div class="card">
        <div class="success">Foreslået kolonne: <b>{{ guessed_col }}</b></div>
      </div>
      {% else %}
      <div class="card">
        <div class="alert">Kunne ikke gætte kolonne – vi brugte første kolonne i arket.</div>
      </div>
      {% endif %}

      <div class="card">
        <form method="post" action="{{ url_for('tekstnormalisering.download') }}">
          <input type="hidden" name="payload_token" value="{{ payload_token }}" />
          <button type="submit">⬇️ Download opdateret Excel</button>
        </form>
        <p class="muted">Den downloadede fil indeholder en ny kolonne med normaliserede værdier{% if add_mapping=='yes' %} og et ekstra “Mapping”-ark{% endif %}.</p>
      </div>
    {% endif %}
    {% endif %}

  </div>
</body>
</html>
"""

# Lille in-memory payload store (single-process). Brug Redis etc. hvis du skal skalere.
_PAYLOAD_STORE: Dict[str, bytes] = {}

def _store_payload(data: bytes) -> str:
    import secrets
    token = secrets.token_urlsafe(24)
    _PAYLOAD_STORE[token] = data
    return token

def _pop_payload(token: str) -> Optional[bytes]:
    return _PAYLOAD_STORE.pop(token, None)

# ---------- Routes ----------
@tekstnormalisering_bp.route("/", methods=["GET", "POST"])
def view():
    tab = request.args.get("tab", "text")
    if tab not in ("text", "excel"):
        return redirect(url_for("tekstnormalisering.view", tab="text"))

    # --- Tekst-fanen ---
    if tab == "text":
        tokens = None
        normalized = []
        pairs = []
        sara_query = ""
        inp = ""
        if request.method == "POST":
            inp = request.form.get("inp", "")
            tokens = split_tokens(inp)
            normalized = [normalize_token(t) for t in tokens]
            pairs = list(zip(tokens, normalized))
            # Byg SARA-søgning i Python (ikke i Jinja)
            normalized_clean = [n for n in normalized if str(n).strip()]
            if normalized_clean:
                sara_query = "objektnummer = " + ", ".join(normalized_clean)

        return render_template_string(
            PAGE_HTML,
            tab="text",
            inp=inp,
            tokens=tokens,
            normalized=normalized,
            pairs=pairs,
            sara_query=sara_query,
        )

    # --- Excel-fanen ---
    if tab == "excel":
        preview_html = None
        payload_token = None
        guessed_col = None
        add_mapping = "yes"

        if request.method == "POST":
            add_mapping = request.form.get("add_mapping", "yes")
            file = request.files.get("excel")
            if not file or file.filename == "":
                return render_template_string(
                    PAGE_HTML, tab="excel", preview=None, add_mapping=add_mapping, guessed_col=None, payload_token=None
                )

            # Læs Excel
            try:
                xls = pd.ExcelFile(file)
                sheet_name = xls.sheet_names[0]
                df = xls.parse(sheet_name)
            except Exception as e:
                return render_template_string(
                    PAGE_HTML,
                    tab="excel",
                    preview=f'<div class="alert">Kunne ikke læse Excel: {e}</div>',
                    add_mapping=add_mapping,
                    guessed_col=None,
                    payload_token=None,
                )

            if df is None or df.empty:
                return render_template_string(
                    PAGE_HTML,
                    tab="excel",
                    preview='<div class="alert">Arket ser tomt ud.</div>',
                    add_mapping=add_mapping,
                    guessed_col=None,
                    payload_token=None,
                )

            # Gæt kolonne og normalisér
            colname = guess_column(df)
            guessed_col = colname
            ser = df[colname].astype("string")
            normalized_ser = ser.map(lambda x: normalize_token(x) if pd.notna(x) and x != '<NA>' else x)

            out = df.copy()
            new_col = f"{colname}_normaliseret"
            out[new_col] = normalized_ser

            # Skriv Excel til hukommelsen
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                out.to_excel(writer, sheet_name=sheet_name, index=False)
                if add_mapping == "yes":
                    map_df = pd.DataFrame({"Før": ser, "Efter": normalized_ser})
                    map_df.to_excel(writer, sheet_name="Mapping", index=False)
            buffer.seek(0)

            payload_token = _store_payload(buffer.getvalue())
            preview_html = df.head(20).to_html(index=False)

        return render_template_string(
            PAGE_HTML,
            tab="excel",
            preview=preview_html,
            payload_token=payload_token,
            guessed_col=guessed_col,
            add_mapping=add_mapping,
        )

    return redirect(url_for("tekstnormalisering.view", tab="text"))

@tekstnormalisering_bp.route("/download", methods=["POST"])
def download():
    token = request.form.get("payload_token")
    if not token:
        return "Mangler payload token", 400
    data = _pop_payload(token)
    if data is None:
        return "Token udløbet eller ugyldigt", 410
    return send_file(
        io.BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="arkivnummer_normaliseret.xlsx",
    )
