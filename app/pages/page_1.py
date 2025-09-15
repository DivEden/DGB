import re
import streamlit as st

st.set_page_config(page_title="Arkivnummer-normalisering", page_icon="🗂️", layout="centered")

st.title("🗂️ Arkivnummer-normalisering")
st.write(
    """
Indsæt en liste af numre (ét pr. linje eller adskilt med mellemrum/komma).  
**Regler:**  
- Ved `:` skal der være **5 cifre** før kolonet (bogstaver tæller ikke med).  
- Ved `x`/`X` skal der være **4 cifre på hver side** (bogstaver tæller ikke med).  
- Bogstaver bevares; der pad'es med foranstillede nuller.
"""
)

example = "133:92\n133b:92\n32x342\nAB12x3c4\n00133:92"
inp = st.text_area(
    "Indsæt numre her:",
    value=example,
    height=180,
    help="Du kan skrive ét pr. linje, eller adskille med mellemrum/komma/semikolon.",
)

def pad_left_ignoring_letters(part: str, target_digits: int) -> str:
    """Foranstil nuller, indtil antallet af cifre (0-9) når target_digits. Bogstaver bevares."""
    digit_count = len(re.findall(r"\d", part))
    if digit_count >= target_digits:
        return part
    zeros_needed = target_digits - digit_count
    return "0" * zeros_needed + part

def normalize_token(token: str) -> str:
    s = token.strip()
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
    raw = re.split(r"[,\s;]+", text.strip())
    return [t for t in raw if t]

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
    sara_query = " OR ".join([f'objektnummer = "{n}"' for n in normalized])
    st.text_area("Kopiér til SARA:", value=sara_query, height=120, key="sara")
