# Home.py
import streamlit as st

st.set_page_config(page_title="CSV Title Merger", page_icon="📄")
st.title("📄 CSV Title Merger")
st.markdown("Vælg en side i menuen til venstre for at starte.")

# Valgfrit: knap der hopper til en anden side (kræver nyere Streamlit)
if st.button("Gå til fletning"):
    st.switch_page("pages/Merger.py")