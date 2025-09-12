# pip install streamlit transformers torch pillow sentencepiece

import io
import streamlit as st
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
import torch

@st.cache_resource(show_spinner=False)
def load_blip():
    model_name = "Salesforce/blip-image-captioning-large"  # eller "...-base" for mindre model
    processor = BlipProcessor.from_pretrained(model_name)
    model = BlipForConditionalGeneration.from_pretrained(
        model_name,
        torch_dtype=torch.float32
    )
    return processor, model

def describe_image_blip_dk(pil_img: Image.Image) -> str:
    processor, model = load_blip()
    prompt = (
        "Beskriv billedet meget detaljeret på dansk: farver, personer, tøj (hat, sko, snørebånd), "
        "tilbehør, kropsholdning, baggrund, lys/stemning, små detaljer."
    )
    inputs = processor(pil_img, prompt, return_tensors="pt")
    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=220)
    return processor.decode(out[0], skip_special_tokens=True).strip()

st.subheader("🖼️ Detaljeret billedbeskrivelse (BLIP)")
uploaded2 = st.file_uploader("Upload billede (BLIP)", type=["jpg","jpeg","png","webp"], key="blip_up")
if uploaded2:
    img2 = Image.open(io.BytesIO(uploaded2.read())).convert("RGB")
    st.image(img2, caption="Forhåndsvisning", use_column_width=True)
    with st.spinner("Genererer beskrivelse..."):
        st.text_area("Beskrivelse (dansk):", describe_image_blip_dk(img2), height=200)
