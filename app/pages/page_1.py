import re
import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Arkivnummer-normalisering", page_icon="🗂️", layout="centered")

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

    # x/X-regel: 4 cifre på hver side
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


def split_tokens(text: str):
    # Split på linjer, mellemrum, komma og semikolon
    if text is None:
        return []
    raw = re.split(r"[,\s;]+", text.strip())
    return [t for t in raw if t]


# ---------- UI ----------
st.title("🗂️ Arkivnummer-normalisering")
st.write(
    """
Indsæt en liste af numre (ét pr. linje eller adskilt med mellemrum/komma), **eller** brug fanen *Excel* for at køre det samme direkte på en regnearkskolonne.
**Regler:**  
- Ved `:` skal der være **5 cifre** før kolonet (bogstaver tæller ikke med).  
- Ved `x`/`X` skal der være **4 cifre på hver side** (bogstaver tæller ikke med).  
- Bogstaver bevares; der pad'es med foranstillede nuller.
"""
)

faner = st.tabs(["Tekst", "Excel"])

# ---------- Fane 1: Tekst ----------
with faner[0]:
    example = ""
    inp = st.text_area(
        "Indsæt numre her:",
        value=example,
        height=180,
        help="Du kan skrive ét pr. linje, eller adskille med mellemrum/komma/semikolon.",
    )

    tokens = split_tokens(inp)
    normalized = [normalize_token(t) for t in tokens]

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Resultat (én pr. linje)")
        st.text_area("Normaliserede numre", value="\n".join(normalized), height=220, key="out1")

    with col2:
        st.subheader("Opslag (før → efter)")
        mapping = "\n".join(f"{a} → {b}" for a, b in zip(tokens, normalized))
        st.text_area("Mapping", value=mapping, height=220, key="out2")

    # --- SARA-søgestreng ---
    if normalized:
        st.subheader("🔎 SARA-søgning")
        sara_query = "objektnummer = " + ", ".join([n for n in normalized if str(n).strip()])
        st.text_area("Kopiér til SARA:", value=sara_query, height=120, key="sara")


# ---------- Fane 2: Excel ----------
with faner[1]:
    st.markdown("#### Normalisér direkte i et Excel-ark")
    uploaded = st.file_uploader("Upload Excel-fil (.xlsx eller .xls)", type=["xlsx", "xls"]) 

    if uploaded is not None:
        try:
            xls = pd.ExcelFile(uploaded)
            sheet = st.selectbox("Vælg ark (sheet)", xls.sheet_names, index=0)
            df = xls.parse(sheet)
        except Exception as e:
            st.error(f"Kunne ikke læse Excel-filen: {e}")
            df = None

        if df is not None:
            st.markdown("**Forhåndsvisning (før):**")
            st.dataframe(df.head(20))

            # Forsøg at gætte en relevant kolonne
            default_idx = 0
            if len(df.columns) > 0:
                candidates = [i for i, c in enumerate(df.columns) if any(k in str(c).lower() for k in ["nummer", "objekt", "id", "arkiv"]) ]
                if candidates:
                    default_idx = candidates[0]

            colname = st.selectbox("Vælg kolonnen der skal normaliseres", df.columns.tolist(), index=default_idx)

            if colname:
                # Konverter til str hvor muligt, bevar NaN
                original_series = df[colname]
                str_series = original_series.astype("string")
                normalized_series = str_series.map(lambda x: normalize_token(x) if x is not pd.NA else x)

                # Vis mapping
                show_map = st.checkbox("Vis mapping (før → efter)", value=True)
                if show_map:
                    map_df = pd.DataFrame({
                        "Før": original_series.astype("string"),
                        "Efter": normalized_series.astype("string"),
                    })
                    st.dataframe(map_df.head(200))

                # Tilføj ny kolonne
                new_col_name = st.text_input("Navn på ny kolonne med normaliserede værdier", value=f"{colname}_normaliseret")
                df_out = df.copy()
                df_out[new_col_name] = normalized_series

                # SARA-søgning
                st.markdown("**🔎 SARA-søgning**")
                normalized_nonempty = [str(v).strip() for v in normalized_series.dropna().tolist() if str(v).strip()]
                sara_query = "objektnummer = " + ", ".join(normalized_nonempty)
                st.text_area("Kopiér til SARA:", value=sara_query, height=120, key="sara_excel")

                # Download som ny Excel-fil (med ét ark)
                buffer = io.BytesIO()
                try:
                    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                        df_out.to_excel(writer, sheet_name=sheet, index=False)
                        # Tilføj evt. mapping som ekstra ark
                        if show_map:
                            map_full = pd.DataFrame({
                                "Før": original_series,
                                "Efter": normalized_series,
                            })
                            map_full.to_excel(writer, sheet_name="Mapping", index=False)
                    st.download_button(
                        label="⬇️ Download opdateret Excel",
                        data=buffer.getvalue(),
                        file_name="arkivnummer_normaliseret.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                except Exception as e:
                    st.error(f"Kunne ikke generere download-fil: {e}")

    else:
        st.info("Upload en Excel-fil for at komme i gang.")
