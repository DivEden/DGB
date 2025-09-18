# pip install streamlit transformers torch pillow sentencepiece

from pathlib import Path
from PIL import Image
import streamlit as st

st.set_page_config(
    page_title="TEST",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Test")

st.sidebar.header("ML Model Config")

model_type = st.sidebar.radio(
    "Select Task", ['Detection', 'Segmentation'])

confidence = float(st.sidebar.slider(
    "Select Model Confidence", 25, 100, 40)) / 100

# You must set model_path manually since helper is removed
model_path = None
if model_type == 'Detection':
    model_path = Path("path/to/detection/model.pt")
elif model_type == 'Segmentation':
    model_path = Path("path/to/segmentation/model.pt")

# Remove model loading since helper is missing
# try:
#     model = helper.load_model(model_path)
# except Exception as ex:
#     st.error(f"Unable to load model. Check the specified path: {model_path}")
#     st.error(ex)
model = None  # Placeholder

st.sidebar.header("Image/Video Config")
source_radio = st.sidebar.radio(
    "Select Source", ['Image', 'Video', 'Webcam', 'RTSP', 'YouTube'])

source_img = None
if source_radio == 'Image':
    source_img = st.sidebar.file_uploader(
        "Choose an image...", type=("jpg", "jpeg", "png", 'bmp', 'webp'))

    col1, col2 = st.columns(2)

    uploaded_image = None
    with col1:
        try:
            if source_img is None:
                st.info("No image uploaded.")
            else:
                uploaded_image = Image.open(source_img)
                st.image(source_img, caption="Uploaded Image",
                         use_container_width=True)
        except Exception as ex:
            st.error("Error occurred while opening the image.")
            st.error(ex)

    with col2:
        # Remove detection since model is not loaded
        st.info("Detection results will appear here.")

elif source_radio == 'Video':
    st.info("Video functionality is not available (missing helper).")

elif source_radio == 'Webcam':
    st.info("Webcam functionality is not available (missing helper).")

elif source_radio == 'RTSP':
    st.info("RTSP functionality is not available (missing helper).")

elif source_radio == 'YouTube':
    st.info("YouTube functionality is not available (missing helper).")

else:
    st.error("Please select a valid source type!")