# pages/Sammenfletter.py
import io
import re
from typing import Dict, Optional
import pandas as pd
from flask import Blueprint, render_template, request, send_file, redirect, url_for

sammenfletter_bp = Blueprint("sammenfletter", __name__)

def norm_cell(v, norm_trim=True, norm_lower=True, norm_remove_punct=True, norm_collapse_ws=True, norm_fix_float=True):
    """Normalize cell value based on settings"""
    if pd.isna(v):
        return ""
    s = str(v)
    if norm_trim:
        s = s.strip().replace("\u00A0", " ")
    if norm_fix_float and re.fullmatch(r"\d+([.,]0+)?", s):
        s = re.split(r"[.,]", s)[0]
    if norm_lower:
        s = s.lower()
    if norm_remove_punct:
        s = re.sub(r"[\W_]+", "", s, flags=re.UNICODE)
    if norm_collapse_ws:
        s = re.sub(r"\s+", " ", s)
    return s

def base_key(s_norm: str) -> str:
    """Extract base key (prefix + first number block)"""
    m = re.match(r"([a-z]+)?(\d+)?", s_norm)
    if not m:
        return s_norm
    return (m.group(1) or "") + (m.group(2) or "")

def guess_key_col(df):
    """Guess the key column (object number)"""
    cols = [c for c in df.columns if re.search(r"objekt|object|obj", str(c), flags=re.I)]
    return cols[0] if cols else df.columns[0]

def guess_title_col(df):
    """Guess the title column"""
    cols = [c for c in df.columns if re.search(r"titel|title|navn|name", str(c), flags=re.I)]
    return cols[0] if cols else (df.columns[1] if len(df.columns) > 1 else df.columns[0])

# Simple in-memory store for file data (use Redis in production)
_FILE_STORE: Dict[str, bytes] = {}

def _store_file(data: bytes) -> str:
    import secrets
    token = secrets.token_urlsafe(24)
    _FILE_STORE[token] = data
    return token

def _pop_file(token: str) -> Optional[bytes]:
    return _FILE_STORE.pop(token, None)

@sammenfletter_bp.route("/", methods=["GET", "POST"])
def view():
    if request.method == "GET":
        return render_template('sammenfletter.html', current_page='sammenfletter')
    
    # Fil upload og processing
    export_file = request.files.get('export_file')
    other_file = request.files.get('other_file')
    
    if not export_file or not other_file or export_file.filename == '' or other_file.filename == '':
        return render_template('sammenfletter.html', 
                             current_page='sammenfletter',
                             error="Begge filer skal uploades")
    
    # Hent form parameters
    norm_trim = request.form.get('norm_trim') == 'on'
    norm_lower = request.form.get('norm_lower') == 'on'
    norm_remove_punct = request.form.get('norm_remove_punct') == 'on'
    norm_collapse_ws = request.form.get('norm_collapse_ws') == 'on'
    norm_fix_float = request.form.get('norm_fix_float') == 'on'
    use_base_key = request.form.get('use_base_key') == 'on'
    
    try:
        # Read Excel files
        df_export = pd.read_excel(export_file)
        df_other = pd.read_excel(other_file)
        
        if df_export.empty or df_other.empty:
            return render_template('sammenfletter.html',
                                 current_page='sammenfletter',
                                 error="En eller begge filer er tomme")
        
        # Gætteleg (prøver at finde de rigtige kolonner)
        exp_key_col = guess_key_col(df_export)
        exp_title_col = guess_title_col(df_export)
        oth_key_col = guess_key_col(df_other)
        
        # Brugere skal have mulighed for at tilsidesætte kolonnevalg
        exp_key_col = request.form.get('exp_key_col', exp_key_col)
        exp_title_col = request.form.get('exp_title_col', exp_title_col)
        oth_key_col = request.form.get('oth_key_col', oth_key_col)
        
        # Store dataframes temporarily for multi-step process
        # In production, use Redis or session storage
        import pickle
        import base64
        
        export_data = base64.b64encode(pickle.dumps(df_export)).decode('utf-8')
        other_data = base64.b64encode(pickle.dumps(df_other)).decode('utf-8')
        
        # Preview data
        if request.form.get('action') == 'select_columns':
            return render_template('sammenfletter.html',
                                 current_page='sammenfletter',
                                 step='column_selection',
                                 df_export_preview=df_export.head(5).to_html(classes="table table-striped"),
                                 df_other_preview=df_other.head(5).to_html(classes="table table-striped"),
                                 export_columns=df_export.columns.tolist(),
                                 other_columns=df_other.columns.tolist(),
                                 exp_key_col=exp_key_col,
                                 exp_title_col=exp_title_col,
                                 oth_key_col=oth_key_col,
                                 export_data=export_data,
                                 other_data=other_data,
                                 settings={
                                     'norm_trim': norm_trim,
                                     'norm_lower': norm_lower,
                                     'norm_remove_punct': norm_remove_punct,
                                     'norm_collapse_ws': norm_collapse_ws,
                                     'norm_fix_float': norm_fix_float,
                                     'use_base_key': use_base_key
                                 })
        
        # If processing step, handle data from hidden fields
        if request.form.get('action') == 'process':
            export_data = request.form.get('export_data')
            other_data = request.form.get('other_data')
            
            if export_data and other_data:
                df_export = pickle.loads(base64.b64decode(export_data.encode('utf-8')))
                df_other = pickle.loads(base64.b64decode(other_data.encode('utf-8')))
        
        # Process sammenfletning
        mapping_full = {}
        mapping_base = {}
        
        for _, row in df_export[[exp_key_col, exp_title_col]].dropna(subset=[exp_key_col]).iterrows():
            key = norm_cell(row[exp_key_col], norm_trim, norm_lower, norm_remove_punct, norm_collapse_ws, norm_fix_float)
            title = row[exp_title_col]
            if key and pd.notna(title):
                mapping_full.setdefault(key, str(title))
                if use_base_key:
                    mapping_base.setdefault(base_key(key), str(title))
        
        # Mapping
        result = df_other.copy()
        normalized_keys = df_other[oth_key_col].apply(
            lambda x: norm_cell(x, norm_trim, norm_lower, norm_remove_punct, norm_collapse_ws, norm_fix_float)
        )
        title_series = normalized_keys.map(mapping_full)
        
        # Key fallback
        if use_base_key:
            missing_mask = title_series.isna()
            if missing_mask.any():
                title_series.loc[missing_mask] = normalized_keys[missing_mask].apply(
                    lambda x: mapping_base.get(base_key(x), None)
                )
        
        # indsæt titler i resultat
        insert_at = result.columns.get_loc(oth_key_col) + 1
        result.insert(insert_at, "Titel (fra export)", title_series)
        
        # stats
        total = len(result)
        matched = result["Titel (fra export)"].notna().sum()
        unmatched = total - matched
        
        # Gem resultat til download
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            result.to_excel(writer, index=False, sheet_name='Flettet')
        buffer.seek(0)
        
        file_token = _store_file(buffer.getvalue())
        
        return render_template('sammenfletter.html',
                             current_page='sammenfletter',
                             step='results',
                             result_preview=result.head(20).to_html(classes="table table-striped"),
                             unmatched_preview=result[result["Titel (fra export)"].isna()].head(10).to_html(classes="table table-striped") if unmatched > 0 else "",
                             total=total,
                             matched=matched,
                             unmatched=unmatched,
                             file_token=file_token)
                             
    except Exception as e:
        return render_template('sammenfletter.html',
                             current_page='sammenfletter',
                             error=f"Fejl ved behandling af filer: {str(e)}")

@sammenfletter_bp.route("/download")
def download():
    token = request.args.get('token')
    if not token:
        return "Mangler token", 400
    
    data = _pop_file(token)
    if data is None:
        return "Token udløbet eller ugyldigt", 410
        
    return send_file(
        io.BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='flettet_resultat.xlsx'
    )
