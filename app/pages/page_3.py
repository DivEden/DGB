from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

from PIL import Image, ImageOps
import streamlit as st

# ---------- Page setup ----------
st.set_page_config(
    page_title="Image Resizer & Renamer",
    page_icon="🖼️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🖼️ Batch Image Resizer & Renamer")
st.caption("Upload a bunch of images, scale them down, and rename them in one go.")

# ---------- Helpers ----------
SUPPORTED_TYPES = ("jpg", "jpeg", "png", "bmp", "webp", "tiff")


def human_size(num: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024.0:
            return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"


def compute_new_size(
    w: int,
    h: int,
    mode: str,
    max_w: Optional[int],
    max_h: Optional[int],
    percent: Optional[int],
) -> Tuple[int, int]:
    if mode == "By longest side":
        longest = max(w, h)
        target = max(max_w or 0, max_h or 0)
        if target <= 0 or longest <= target:
            return w, h
        scale = target / float(longest)
        return max(1, int(round(w * scale))), max(1, int(round(h * scale)))

    if mode == "Max width/height":
        # Fit into a bounding box (max_w x max_h)
        mw = max_w or w
        mh = max_h or h
        scale = min(mw / w, mh / h)
        if scale >= 1:
            return w, h
        return max(1, int(round(w * scale))), max(1, int(round(h * scale)))

    if mode == "By percentage":
        pct = (percent or 100) / 100.0
        return max(1, int(round(w * pct))), max(1, int(round(h * pct)))

    return w, h


def safe_open_image(file) -> Image.Image:
    img = Image.open(file)
    # Respect EXIF orientation
    img = ImageOps.exif_transpose(img)
    return img


def normalize_mode_for_format(img: Image.Image, fmt: str) -> Image.Image:
    """Ensure compatible mode for chosen output format."""
    if fmt.upper() in {"JPEG", "JPG"}:
        # JPEG doesn't support alpha
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            return bg
        return img.convert("RGB")
    return img


def build_filename(
    pattern: str,
    index: int,
    pad: int,
    orig_stem: str,
    ext: str,
    now: datetime,
) -> str:
    # Supported placeholders: {n}, {orig}, {ext}, {date}, {time}
    n_str = str(index).zfill(pad)
    out = pattern
    out = out.replace("{n}", n_str)
    out = out.replace("{orig}", orig_stem)
    out = out.replace("{ext}", ext)
    out = out.replace("{date}", now.strftime("%Y%m%d"))
    out = out.replace("{time}", now.strftime("%H%M%S"))
    # Ensure extension present once
    if not out.lower().endswith(f".{ext.lower()}"):
        out = f"{out}.{ext}"
    return out


# ---------- Sidebar controls ----------
st.sidebar.header("Source")
files = st.sidebar.file_uploader(
    "Upload images (multiple)", type=SUPPORTED_TYPES, accept_multiple_files=True
)

st.sidebar.header("Resize Options")
resize_mode = st.sidebar.radio(
    "How to resize?", ["By longest side", "Max width/height", "By percentage"],
)

col_rs1, col_rs2 = st.sidebar.columns(2)
max_width = None
max_height = None
percent = None

if resize_mode == "By longest side":
    max_width = col_rs1.number_input("Longest side (px)", min_value=1, value=1600)
elif resize_mode == "Max width/height":
    max_width = col_rs1.number_input("Max width (px)", min_value=1, value=1600)
    max_height = col_rs2.number_input("Max height (px)", min_value=1, value=1200)
else:
    percent = col_rs1.slider("Scale %", min_value=1, max_value=100, value=50)

st.sidebar.header("Output")
output_format = st.sidebar.selectbox(
    "Format",
    ["Keep original", "JPEG", "PNG", "WEBP"],
    index=0,
)

quality = st.sidebar.slider("Quality (JPEG/WebP)", 10, 100, 85)
strip_exif = st.sidebar.checkbox("Strip EXIF/metadata", value=True)

st.sidebar.header("Renaming")
rename_enabled = st.sidebar.checkbox("Enable renaming", value=True)

default_pattern = "img_{n}_{orig}"
pattern = st.sidebar.text_input(
    "Filename pattern",
    value=default_pattern,
    help=(
        "Use placeholders: {n} (number), {orig} (original name without ext), "
        "{ext} (extension), {date} (YYYYMMDD), {time} (HHMMSS). Extension is appended if missing."
    ),
    disabled=not rename_enabled,
)
start_num = st.sidebar.number_input("Start number", min_value=0, value=1, disabled=not rename_enabled)
pad_width = st.sidebar.number_input("Zero padding", min_value=1, max_value=6, value=3, disabled=not rename_enabled)

st.sidebar.header("Run")
process_btn = st.sidebar.button("Process images", type="primary", use_container_width=True)

# ---------- Main area ----------
left, right = st.columns([1, 1])

with left:
    st.subheader("Uploads")
    if not files:
        st.info("No images uploaded yet.")
    else:
        st.write(f"{len(files)} file(s) selected:")
        for f in files:
            st.write(f"• {f.name} ({human_size(f.size)})")

with right:
    st.subheader("Preview")
    if files:
        thumbs = st.container()
        grid_cols = st.columns(4)
        for i, f in enumerate(files):
            try:
                img = safe_open_image(f)
                grid_cols[i % 4].image(img, caption=f.name, use_container_width=True)
            except Exception as ex:
                grid_cols[i % 4].error(f"Failed to open {f.name}: {ex}")

st.divider()

# ---------- Processing ----------
results = []  # list of dicts with info for table
zip_buffer = BytesIO()

if process_btn and files:
    now = datetime.now()
    with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as zipf:
        idx = start_num
        for f in files:
            try:
                orig_name = Path(f.name)
                orig_ext = (orig_name.suffix or ".jpg").lstrip(".")
                out_ext = orig_ext if output_format == "Keep original" else output_format.lower()
                img = safe_open_image(f)
                w0, h0 = img.size

                # Compute new size
                new_w, new_h = compute_new_size(w0, h0, resize_mode, max_width, max_height, percent)
                if (new_w, new_h) != (w0, h0):
                    img = img.resize((new_w, new_h), Image.LANCZOS)

                # Metadata handling
                save_params = {}
                
                # Strip or preserve EXIF
                if strip_exif:
                    exif_bytes = None
                else:
                    exif_bytes = img.getexif()
                    if exif_bytes:
                        save_params["exif"] = exif_bytes.tobytes()

                # Normalize for format and set options
                img = normalize_mode_for_format(img, out_ext)
                if out_ext in ("jpeg", "jpg"):
                    save_params["quality"] = int(quality)
                    save_params["optimize"] = True
                elif out_ext == "webp":
                    save_params["quality"] = int(quality)
                
                # Build filename
                if rename_enabled:
                    out_name = build_filename(pattern, idx, int(pad_width), orig_name.stem, out_ext, now)
                else:
                    # Keep original stem, change ext if needed
                    out_name = orig_name.with_suffix(f".{out_ext}").name

                # Save into the zip
                out_bytes = BytesIO()
                img.save(out_bytes, format=out_ext.upper(), **save_params)
                out_bytes.seek(0)
                zipf.writestr(out_name, out_bytes.read())

                results.append(
                    {
                        "Original name": orig_name.name,
                        "New name": out_name,
                        "Original size": f"{w0}×{h0}",
                        "New size": f"{new_w}×{new_h}",
                    }
                )
                idx += 1
            except Exception as ex:
                results.append(
                    {
                        "Original name": f.name,
                        "New name": "(failed)",
                        "Original size": "-",
                        "New size": str(ex),
                    }
                )

if results:
    st.subheader("Results")
    st.dataframe(results, use_container_width=True)

    zip_buffer.seek(0)
    st.download_button(
        label="Download processed images (ZIP)",
        data=zip_buffer,
        file_name="resized_renamed_images.zip",
        mime="application/zip",
        use_container_width=True,
    )

st.caption(
    "Tip: Use a pattern like `project_{date}_img-{n}` to get names like `project_20250101_img-001.jpg`."
)