# join_sara_simple.py
import io
import re
import csv
import unicodedata
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Sara → Måltabel (ultra-simpel)", page_icon="📄", layout="centered")
st.title("📄 Tildel titel fra Sara-eksport til alle numre i Legetøj")

# ---------------- Hjælpere ----------------
def _buffer_file(uploaded_file):
    if uploaded_file is None:
        return None
    return io.BytesIO(uploaded_file.read())

def sanitize_colname(c: str) -> str:
    return re.sub(r"[\s;:.,]+$", "", str(c)).strip()

def make_unique_columns(cols):
    counts, out = {}, []
    for c in cols:
        name = str(c).strip()
        if name in counts:
            counts[name] += 1
            out.append(f"{name}.{counts[name]}")
        else:
            counts[name] = 0
            out.append(name)
    return out

def ensure_unique_columns(df: pd.DataFrame) -> pd.DataFrame:
    seen = {}
    new_cols = []
    for c in list(df.columns):
        if c not in seen:
            seen[c] = 0
            new_cols.append(c)
        else:
            seen[c] += 1
            new_cols.append(f"{c}.{seen[c]}")
    df.columns = new_cols
    return df

def _sniff_delimiter_from_text(txt: str) -> str:
    lines = [ln for ln in txt.splitlines() if ln.strip()][:50]
    if not lines:
        return ";"
    candidates = [";", "\t", ","]
    from statistics import median
    best, best_score = ";", (-1, -1)
    for cand in candidates:
        counts = [ln.count(cand) for ln in lines]
        nonzero = [c for c in counts if c > 0]
        if not nonzero:
            score = (0, 0)
        else:
            avg = sum(nonzero) / len(nonzero)
            med = median(nonzero)
            consistency = sum(1 for c in nonzero if c == med) / len(nonzero)
            score = (avg, consistency)
        if score > best_score:
            best_score, best = score, cand
    return best

def read_csv_auto(uploaded_file):
    buf = _buffer_file(uploaded_file)
    if buf is None:
        return None, None
    buf.seek(0)
    raw = buf.read().decode("utf-8-sig", errors="replace")
    sep = _sniff_delimiter_from_text(raw)

    df = None
    for quoting in (csv.QUOTE_MINIMAL, csv.QUOTE_NONE):
        try:
            b2 = io.BytesIO(raw.encode("utf-8"))
            d = pd.read_csv(
                b2, dtype=str, sep=sep, quoting=quoting, escapechar="\\",
                on_bad_lines="skip", engine="python"
            )
            d = d.rename(columns=lambda c: sanitize_colname(str(c)))
            d.columns = make_unique_columns(d.columns)
            d = ensure_unique_columns(d)
            df = d
            break
        except Exception:
            continue

    if df is None:
        st.error("Kunne ikke læse CSV. Tjek separator/encoding.")
        return None, None

    return df, (sep if sep in [",", ";", "\t"] else ";")

# ---------- Normalisering ----------
SEP_ALIASES = r"[.\-／⁄/：∶﹕︰]"  # alt der skal blive til ":"

def _normalize_key_one(x: str) -> str:
    if x is None:
        return ""
    s = str(x)
    if not s.strip():
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\u200B-\u200D\u2060\uFEFF\u00A0]", "", s)  # skjulte tegn
    s = s.strip().strip('"').strip("'")
    s = re.sub(SEP_ALIASES, ":", s)
    s = s.strip(";.,").upper()  # <- fjerner evt. trailing semikolon inde i feltet
    if ":" in s:
        left, right = s.split(":", 1)
    else:
        left, right = s, ""
    m = re.match(r"^0*(\d+)([A-Z]*)$", left)
    if m:
        digits = m.group(1) or "0"; suffix = m.group(2) or ""
        left = digits.zfill(5) + suffix
    else:
        m2 = re.match(r"^0*(\d+)(.*)$", left)
        if m2:
            left = (m2.group(1) or "0").zfill(5) + (m2.group(2) or "")
    return left + (":" + right if right else "")

def normalize_key_series(series: pd.Series) -> pd.Series:
    return series.fillna("").map(_normalize_key_one)

# ---------- Split af sammensat Sara-kolonne (titel + nummer i samme felt) ----------
def force_split_title_object(df: pd.DataFrame):
    """
    Finder den kolonne hvor der forekommer '...,[KEY][;?]' (KEY ~ ddd..:dd.. eller tal)
    og splitter ALTID ved SIDSTE komma til kolonnerne 'Titel' og 'Objektnummer'.
    Fjerner trailing semikolon i 'Objektnummer'.
    """
    # match "…,[noget med tal eller nøgle] evt. semikolon til sidst"
    pat_tail_key = re.compile(r".+,[^,]*\d+;?$")
    best_col = None
    best_hits = 0
    for c in df.columns:
        s = df[c].dropna().astype(str)
        hits = s.head(100000).str.contains(pat_tail_key, na=False).sum()
        if hits > best_hits:
            best_hits = hits
            best_col = c

    if best_col is None or best_hits == 0:
        return df  # intet at splitte

    parts = df[best_col].astype(str).str.rsplit(",", n=1, expand=True)
    if parts is None or parts.shape[1] != 2:
        return df

    title_col = "Titel"
    obj_col = "Objektnummer"
    while title_col in df.columns: title_col += ".1"
    while obj_col in df.columns:   obj_col   += ".1"

    df[title_col] = parts.iloc[:, 0].astype(str).str.strip()
    # fjern trailing ; og whitespace fra nummerdelen
    df[obj_col]   = parts.iloc[:, 1].astype(str).str.strip().str.replace(r";+$", "", regex=True).str.strip()
    return df

# ---------------- UI: upload ----------------
col1, col2 = st.columns(2)
with col1:
    sara_up = st.file_uploader("🔎 Sara-eksport (kildetabel)", type=["csv"], key="sara")
with col2:
    toy_up  = st.file_uploader("🎯 Legetøj (måltabel)", type=["csv"], key="toy")

if sara_up is not None and toy_up is not None:
    sara_df, sara_sep = read_csv_auto(sara_up)
    toy_df, toy_sep   = read_csv_auto(toy_up)
    if sara_df is None or toy_df is None:
        st.stop()

    # Legetøj: find nøglekolonne
    key_candidates = ["genstandsnummer", "nummer", "objektnummer", "objectnumber"]
    toy_key_col = None
    lowcols = [c.lower() for c in toy_df.columns]
    for k in key_candidates:
        if k in lowcols:
            toy_key_col = toy_df.columns[lowcols.index(k)]
            break
    if toy_key_col is None:
        pat = re.compile(r"\d{3,5}[A-Z]?:\d+")
        hits = sorted(((toy_df[c].astype(str).str.contains(pat, na=False).sum(), c) for c in toy_df.columns), reverse=True)
        toy_key_col = hits[0][1]

    # Sara: split hvis nødvendig (håndterer fx "Modeljernbanetilbehør, personvogn,02137:92;")
    sara_df = force_split_title_object(sara_df)

    # Find objektnummer- og titel-kolonne efter split
    sara_obj_col = None
    sara_title_col = None
    low_s = [c.lower() for c in sara_df.columns]

    for k in ["objektnummer", "objectnumber", "genstandsnummer", "nummer", "id", "nr"]:
        if k in low_s:
            sara_obj_col = sara_df.columns[low_s.index(k)]
            break
    if sara_obj_col is None:
        # vælg kolonnen med flest nøgle-lignende værdier
        pat = re.compile(r"\d{3,5}[A-Z]?:\d+")
        hits = sorted(((sara_df[c].astype(str).str.contains(pat, na=False).sum(), c) for c in sara_df.columns), reverse=True)
        sara_obj_col = hits[0][1]

    for k in ["titel", "title", "benævnelse", "betegnelse", "navn"]:
        if k in low_s:
            sara_title_col = sara_df.columns[low_s.index(k)]
            break
    if sara_title_col is None:
        # vælg mest tekstagtige
        best_c, best_score = None, -1.0
        for c in sara_df.columns:
            if c == sara_obj_col: 
                continue
            s = sara_df[c].fillna("").astype(str)
            nonempty = s[s.str.strip() != ""]
            if nonempty.empty:
                continue
            has_alpha = nonempty.str.contains(r"[A-Za-zÆØÅæøå]", regex=True, na=False).mean()
            avg_len = nonempty.str.len().clip(upper=200).mean()
            score = float(0.6*has_alpha + 0.3*(avg_len/50.0))
            if score > best_score:
                best_c, best_score = c, score
        sara_title_col = best_c or sara_df.columns[0]

    st.caption(
        f"Legetøj nøgle: **{toy_key_col}** · Sara nøgle: **{sara_obj_col}** · Titel: **{sara_title_col}**"
    )

    # ---------------- Merge ----------------
    toy_df["_key_norm"]  = normalize_key_series(toy_df[toy_key_col])
    sara_df["_key_norm"] = normalize_key_series(sara_df[sara_obj_col])

    out_title = sara_title_col if sara_title_col not in toy_df.columns else f"sara_{sara_title_col}"
    left_sub = (
        sara_df[["_key_norm", sara_title_col]]
        .drop_duplicates(subset="_key_norm", keep="first")
        .rename(columns={sara_title_col: out_title})
    )

    merged = pd.merge(toy_df, left_sub, on="_key_norm", how="left").drop(columns=["_key_norm"])

    matched = merged[out_title].notna().sum()
    total = merged.shape[0]
    st.success(f"Færdig! Match: {matched}/{total}")

    # Download
    eff_sep = toy_sep if toy_sep in [",", ";", "\t"] else ";"
    out_buffer = io.StringIO()
    merged.to_csv(out_buffer, index=False, sep=eff_sep)
    data_bytes = ("\ufeff" + out_buffer.getvalue()).encode("utf-8")
    st.download_button("⬇️ Download resultat (CSV)", data=data_bytes, file_name="resultat.csv", mime="text/csv")

    # Debug: vis netop den linje du nævner
    with st.expander("Tjek: linje med 02137:92 fundet i Sara?"):
        mask = sara_df[sara_obj_col].fillna("").astype(str).str.contains(r"\b02137\s*[:：]\s*92\b", regex=True)
        st.write(sara_df.loc[mask, [sara_title_col, sara_obj_col]].head(10))

    # Eksempler uden match
    with st.expander("Se eksempler på rækker uden match (op til 50)"):
        nohit = merged[merged[out_title].isna()][[toy_key_col]].head(50)
        st.dataframe(nohit)

    # Preview
    with st.expander("Se første 10 rækker (valgfrit)"):
        st.write("**Legetøj (første 10)**")
        st.dataframe(toy_df.head(10))
        st.write("**Sara – nøgle + titel (første 10)**")
        st.dataframe(sara_df[[sara_obj_col, sara_title_col]].head(10))

else:
    st.info("Træk begge CSV-filer ind for at flette titler ind i din Legetøj-fil.")
