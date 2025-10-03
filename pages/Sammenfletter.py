# pages/Sammenfletter.py
import io
import re
from typing import Dict, Optional, List
import pandas as pd
from flask import Blueprint, render_template, request, send_file, redirect, url_for, jsonify

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
    tab = request.args.get('tab', 'excel')  # Standard tab er excel
    
    if request.method == "GET":
        return render_template('sammenfletter.html', 
                             current_page='sammenfletter', 
                             active_tab=tab)
    
    # Handle different tabs
    if tab == 'excel':
        return handle_excel_merge()
    elif tab == 'api':
        return handle_api_integration()
    elif tab == 'manual':
        return handle_manual_input()
    else:
        return handle_excel_merge()  # Default fallback

def handle_excel_merge():
    """Handle the original Excel file merging functionality"""
    # Fil upload og processing
    export_file = request.files.get('export_file')
    other_file = request.files.get('other_file')
    
    if not export_file or not other_file or export_file.filename == '' or other_file.filename == '':
        return render_template('sammenfletter.html', 
                             current_page='sammenfletter',
                             active_tab='excel',
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
                                 active_tab='excel',
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
                                 active_tab='excel',
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
                             active_tab='excel',
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
                             active_tab='excel',
                             error=f"Fejl ved behandling af filer: {str(e)}")

def handle_api_integration():
    """Handle API integration with selectable fields"""
    # Placeholder for future API integration
    available_fields = [
        {'id': 'billeder', 'label': 'Billeder', 'description': 'Produktbilleder i høj opløsning'},
        {'id': 'titel', 'label': 'Titel', 'description': 'Produkttitel og navn'},
        {'id': 'beskrivelse', 'label': 'Beskrivelse', 'description': 'Detaljeret produktbeskrivelse'},
        {'id': 'dimensioner', 'label': 'Dimensioner', 'description': 'Størrelse og mål'},
        {'id': 'materiale', 'label': 'Materiale', 'description': 'Materialetype og sammensætning'},
        {'id': 'datering', 'label': 'Datering', 'description': 'Tidsperiode og alder'},
        {'id': 'provenance', 'label': 'Provenance', 'description': 'Oprindelse og historie'},
        {'id': 'tilstand', 'label': 'Tilstand', 'description': 'Bevaringstilstand'},
        {'id': 'lokation', 'label': 'Lokation', 'description': 'Nuværende placering'},
        {'id': 'inventarnummer', 'label': 'Inventarnummer', 'description': 'Internt nummer'},
    ]
    
    if request.method == 'POST':
        excel_file = request.files.get('excel_file')
        selected_fields = request.form.getlist('selected_fields')
        
        if not excel_file or excel_file.filename == '':
            return render_template('sammenfletter.html',
                                 current_page='sammenfletter',
                                 active_tab='api',
                                 available_fields=available_fields,
                                 error="Excel fil skal uploades")
        
        if not selected_fields:
            return render_template('sammenfletter.html',
                                 current_page='sammenfletter',
                                 active_tab='api',
                                 available_fields=available_fields,
                                 error="Vælg mindst ét felt til sammenfletning")
        
        try:
            # Read Excel file
            df_input = pd.read_excel(excel_file)
            
            # Guess object number column
            obj_col = guess_key_col(df_input)
            obj_col = request.form.get('obj_col', obj_col)
            
            if obj_col not in df_input.columns:
                return render_template('sammenfletter.html',
                                     current_page='sammenfletter',
                                     active_tab='api',
                                     available_fields=available_fields,
                                     error=f"Kolonne '{obj_col}' ikke fundet")
            
            # Extract object numbers
            object_numbers = df_input[obj_col].dropna().astype(str).tolist()
            
            # TODO: Replace with actual API call
            # For now, create mock data
            api_data = []
            for obj_num in object_numbers:
                mock_record = {'objektnummer': obj_num}
                for field_id in selected_fields:
                    field_label = next(f['label'] for f in available_fields if f['id'] == field_id)
                    mock_record[field_label] = f"Mock {field_label} for {obj_num}"
                api_data.append(mock_record)
            
            # Create result DataFrame
            result_df = pd.DataFrame(api_data)
            
            # Store result for download
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                result_df.to_excel(writer, index=False, sheet_name='API_Resultat')
            buffer.seek(0)
            
            file_token = _store_file(buffer.getvalue())
            
            return render_template('sammenfletter.html',
                                 current_page='sammenfletter',
                                 active_tab='api',
                                 step='api_results',
                                 result_preview=result_df.head(20).to_html(classes="table table-striped"),
                                 total_records=len(result_df),
                                 selected_fields_labels=[next(f['label'] for f in available_fields if f['id'] == fid) for fid in selected_fields],
                                 file_token=file_token)
                                 
        except Exception as e:
            return render_template('sammenfletter.html',
                                 current_page='sammenfletter',
                                 active_tab='api',
                                 available_fields=available_fields,
                                 error=f"Fejl ved behandling: {str(e)}")
    
    return render_template('sammenfletter.html',
                         current_page='sammenfletter',
                         active_tab='api',
                         available_fields=available_fields)

def handle_manual_input():
    """Handle manual object number input without Excel upload"""
    available_fields = [
        {'id': 'billeder', 'label': 'Billeder', 'description': 'Produktbilleder i høj opløsning'},
        {'id': 'titel', 'label': 'Titel', 'description': 'Produkttitel og navn'},
        {'id': 'beskrivelse', 'label': 'Beskrivelse', 'description': 'Detaljeret produktbeskrivelse'},
        {'id': 'dimensioner', 'label': 'Dimensioner', 'description': 'Størrelse og mål'},
        {'id': 'materiale', 'label': 'Materiale', 'description': 'Materialetype og sammensætning'},
        {'id': 'datering', 'label': 'Datering', 'description': 'Tidsperiode og alder'},
        {'id': 'provenance', 'label': 'Provenance', 'description': 'Oprindelse og historie'},
        {'id': 'tilstand', 'label': 'Tilstand', 'description': 'Bevaringstilstand'},
        {'id': 'lokation', 'label': 'Lokation', 'description': 'Nuværende placering'},
        {'id': 'inventarnummer', 'label': 'Inventarnummer', 'description': 'Internt nummer'},
    ]
    
    if request.method == 'POST':
        object_numbers_text = request.form.get('object_numbers', '').strip()
        selected_fields = request.form.getlist('selected_fields')
        
        if not object_numbers_text:
            return render_template('sammenfletter.html',
                                 current_page='sammenfletter',
                                 active_tab='manual',
                                 available_fields=available_fields,
                                 error="Indtast mindst ét objektnummer")
        
        if not selected_fields:
            return render_template('sammenfletter.html',
                                 current_page='sammenfletter',
                                 active_tab='manual',
                                 available_fields=available_fields,
                                 error="Vælg mindst ét felt til sammenfletning")
        
        try:
            # Parse object numbers (support comma, semicolon, newline separation)
            import re
            object_numbers = re.split(r'[,;\n]+', object_numbers_text)
            object_numbers = [num.strip() for num in object_numbers if num.strip()]
            
            if not object_numbers:
                return render_template('sammenfletter.html',
                                     current_page='sammenfletter',
                                     active_tab='manual',
                                     available_fields=available_fields,
                                     error="Ingen gyldige objektnumre fundet")
            
            # TODO: Replace with actual API call
            # For now, create mock data
            api_data = []
            for obj_num in object_numbers:
                mock_record = {'objektnummer': obj_num}
                for field_id in selected_fields:
                    field_label = next(f['label'] for f in available_fields if f['id'] == field_id)
                    mock_record[field_label] = f"Mock {field_label} for {obj_num}"
                api_data.append(mock_record)
            
            # Create result DataFrame
            result_df = pd.DataFrame(api_data)
            
            # Store result for download
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                result_df.to_excel(writer, index=False, sheet_name='Manual_Resultat')
            buffer.seek(0)
            
            file_token = _store_file(buffer.getvalue())
            
            return render_template('sammenfletter.html',
                                 current_page='sammenfletter',
                                 active_tab='manual',
                                 step='manual_results',
                                 result_preview=result_df.head(20).to_html(classes="table table-striped"),
                                 total_records=len(result_df),
                                 selected_fields_labels=[next(f['label'] for f in available_fields if f['id'] == fid) for fid in selected_fields],
                                 object_numbers_count=len(object_numbers),
                                 file_token=file_token)
                                 
        except Exception as e:
            return render_template('sammenfletter.html',
                                 current_page='sammenfletter',
                                 active_tab='manual',
                                 available_fields=available_fields,
                                 error=f"Fejl ved behandling: {str(e)}")
    
    return render_template('sammenfletter.html',
                         current_page='sammenfletter',
                         active_tab='manual',
                         available_fields=available_fields)

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
