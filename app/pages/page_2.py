import pandas as pd
import streamlit as st
import re
from io import BytesIO

st.set_page_config(page_title="Flet objektnumre med titler", layout="wide")
st.title("🔗 Flet objektnumre med titler — én side (forbedret)")
st.caption("Denne version matcher robustere: ignorerer mellemrum/tegnsætning/case og kan matche på 'basis-nøgle' (prefix + første tal-blok).")

with st.sidebar:
    st.header("⚙️ Normalisering")
    norm_trim = st.checkbox("Trim mellemrum", True)
    norm_lower = st.checkbox("Lowercase", True)
    norm_remove_punct = st.checkbox("Fjern tegnsætning", True, help="Fjerner fx .,;:/- mv. fra nøglen.")
    norm_collapse_ws = st.checkbox("Sammenflet flere mellemrum", True)
    norm_fix_float = st.checkbox("Fjern .0 / ,0 fra heltal", True)
    use_base_key = st.checkbox("Fallback: 'basis-nøgle' (prefix + første tal-blok)", True,
                               help="Hjælper ved delnumre som -1, .1, a, etc.")

def norm_cell(v):
    if pd.isna(v):
        return ""
    s = str(v)
    if norm_trim:
        s = s.strip().replace("\u00A0"," ")
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
    m = re.match(r"([a-z]+)?(\d+)?", s_norm)
    if not m:
        return s_norm
    return (m.group(1) or "") + (m.group(2) or "")

def guess_key_col(df):
    cols = [c for c in df.columns if re.search(r"objekt|object|obj", str(c), flags=re.I)]
    return cols[0] if cols else df.columns[0]

def guess_title_col(df):
    cols = [c for c in df.columns if re.search(r"titel|title|navn|name", str(c), flags=re.I)]
    return cols[0] if cols else (df.columns[1] if len(df.columns)>1 else df.columns[0])

left, right = st.columns(2, gap="large")
with left:
    st.subheader("1) Upload *export.xlsx* (arkiv)")
    fe = st.file_uploader("Vælg fil", type=["xlsx"], key="export")
    df_e = None
    if fe:
        try:
            xe = pd.ExcelFile(fe)
            se = st.selectbox("Vælg ark (sheet) i export", xe.sheet_names, index=0)
            df_e = pd.read_excel(xe, sheet_name=se)
            st.caption(f"Export: {df_e.shape[0]} rækker, {df_e.shape[1]} kolonner")
            st.dataframe(df_e.head(10), use_container_width=True)
        except Exception as ex:
            st.error(f"Kunne ikke læse export: {ex}")

with right:
    st.subheader("2) Upload *andet dokument* (objektnumre)")
    fo = st.file_uploader("Vælg fil", type=["xlsx"], key="other")
    df_o = None
    if fo:
        try:
            xo = pd.ExcelFile(fo)
            so = st.selectbox("Vælg ark (sheet) i andet dokument", xo.sheet_names, index=0)
            df_o = pd.read_excel(xo, sheet_name=so)
            st.caption(f"Andet: {df_o.shape[0]} rækker, {df_o.shape[1]} kolonner")
            st.dataframe(df_o.head(10), use_container_width=True)
        except Exception as ex:
            st.error(f"Kunne ikke læse andet dokument: {ex}")

if df_e is not None and df_o is not None and len(df_e.columns)>0 and len(df_o.columns)>0:
    st.subheader("3) Vælg kolonner")
    ek = guess_key_col(df_e) or df_e.columns[0]
    et = guess_title_col(df_e) or (df_e.columns[1] if len(df_e.columns)>1 else df_e.columns[0])
    ok = guess_key_col(df_o) or df_o.columns[0]

    exp_key = st.selectbox("EXPORT — objektnummer", df_e.columns.tolist(), index=df_e.columns.tolist().index(ek))
    exp_title = st.selectbox("EXPORT — titel", df_e.columns.tolist(), index=df_e.columns.tolist().index(et))
    oth_key = st.selectbox("ANDET — objektnummer", df_o.columns.tolist(), index=df_o.columns.tolist().index(ok))

    # Build mappings
    mapping_full = {}
    mapping_base = {}
    for _, r in df_e[[exp_key, exp_title]].dropna(subset=[exp_key]).iterrows():
        k = norm_cell(r[exp_key])
        t = r[exp_title]
        if k and pd.notna(t):
            mapping_full.setdefault(k, str(t))
            if use_base_key:
                mapping_base.setdefault(base_key(k), str(t))

    res = df_o.copy()
    kn = df_o[oth_key].map(norm_cell)
    title_series = kn.map(mapping_full)

    if use_base_key:
        miss = title_series.isna()
        if miss.any():
            title_series.loc[miss] = kn[miss].map(lambda x: mapping_base.get(base_key(x), None))

    # Insert column after key
    insert_at = res.columns.get_loc(oth_key) + 1
    res.insert(insert_at, "Titel (fra export)", title_series)

    st.subheader("4) Resultat")
    total = len(res)
    matched = res["Titel (fra export)"].notna().sum()
    unmatched = total - matched
    st.success(f"Matchede {matched} af {total} rækker. {unmatched} uden match.")

    st.dataframe(res, use_container_width=True)

    with st.expander("Vis kun uden match"):
        st.dataframe(res[res["Titel (fra export)"].isna()], use_container_width=True)

    # Downloads
    def to_excel_bytes(df, sheet="Merged"):
        bio = BytesIO()
        with pd.ExcelWriter(bio, engine="xlsxwriter") as wr:
            df.to_excel(wr, index=False, sheet_name=sheet)
        return bio.getvalue()

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Download — Excel", to_excel_bytes(res), "flettet_resultat.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with c2:
        st.download_button("⬇️ Download — CSV", res.to_csv(index=False).encode("utf-8-sig"),
            "flettet_resultat.csv", "text/csv")
else:
    st.info("Upload begge filer og vælg kolonner.")
