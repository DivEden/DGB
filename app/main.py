# Home.py
import streamlit as st

st.set_page_config(
    page_title="DGB Hjemmeside",
    page_icon="🐟",
    layout="centered"
)

# --- Custom CSS ---
st.markdown(
    """
    <style>
    /* Centrer alt indhold */
    .block-container {
        padding-top: 2rem;True
        padding-bottom: 2rem;
        text-align: center;
    }
    h1 {
        font-size: 3rem !important;
        color: #1E3D59;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        font-size: 1.3rem;
        color: #555;
        margin-bottom: 2rem;
    }
    .stButton>button {
        background-color: #1E3D59;
        color: white;
        border-radius: 12px;
        padding: 0.6rem 2rem;
        font-size: 1rem;
        transition: 0.3s;
    }
    .stButton>button:hover {
        background-color: #28527a;
        transform: scale(1.05);
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- Page content ---
st.title("🐟 DGB")

st.write("")
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Billedredigering"):
        st.write("Yap yap")

with col2:
    if st.button("sammenfletter"):
        st.write("Yap yap")

with col3:
    if st.button("Titelrenser"):
        st.write("yap yap")

st.write("---")
st.caption("© 2025 DGB – lavet med Streamlit 🐟")

if "ready" not in st.session_state:
    st.image("Fish.gif", use_container_width=False)
    with st.spinner("Starter app..."):
        time.sleep(3)  # tung opgave
    st.session_state.ready = True
    st.experimental_rerun()

