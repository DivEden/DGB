# Home.py
import streamlit as st
import time

st.set_page_config(page_title="DGB Hjemmeside", page_icon="🐟")

st.title("DGB")
st.write("Nu er siden klar 🐟")

if "ready" not in st.session_state:
    st.image("Fish.gif", use_container_width=False)
    with st.spinner("Starter app..."):
        time.sleep(3)  # tung opgave
    st.session_state.ready = True
    st.experimental_rerun()

