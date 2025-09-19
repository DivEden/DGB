from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import pandas as pd
from PIL import Image, ImageOps
import streamlit as st

# ---------- Forsøg at importere drag&drop-komponent ----------
try:
    # pip install streamlit-sortables
    from streamlit_sortables import sort_items  # type: ignore
    HAS_SORTABLES = True
except Exception:
    HAS_SORTABLES = False

# ---------- Sideopsætning ----------
st.set_page_config(
    page_title="Arkiv-Upload: Drag & Drop Grupper, Omdøb & Maks KB",
    page_icon="🖼️",
    layout="wide",
)

st.title("🖼️ Arkiv-Upload: grupper med drag & drop, omdøb & komprimer til maks KB")

# ---------- Konstanter ----------
SUPPORTED_TYPES = ("jpg", "jpeg", "png", "bmp", "webp", "tiff")
FORMAT_MAP = {"jpg":"JPEG","jpeg":"JPEG","png":"PNG","webp":"WEBP","tiff":"TIFF","bmp":"BMP"}
LOSSY_FORMATS = {"jpeg","jpg","webp"}

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS

# ---------- Hjælpere ----------
def human_size(num: int) -> str:
    for unit in ["B","KB","MB","GB"]:
        if num < 1024.0:
            return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"

def safe_open_image(file) -> Image.Image:
    try:
        file.seek(0)
    except Exception:
        pass
    img = Image.open(file)
    img = ImageOps.exif_transpose(img)
    return img

def normalize_mode_for_format(img: Image.Image, fmt_ext: str) -> Image.Image:
    if fmt_ext.upper() in {"JPEG","JPG"}:
        if img.mode in ("RGBA","LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            return bg
        return img.convert("RGB")
    return img

def save_image_bytes(img: Image.Image, ext: str, quality: Optional[int] = None) -> bytes:
    fmt = FORMAT_MAP.get(ext.lower(), ext.upper())
    out = BytesIO()
    params = {}
    if ext.lower() in {"jpeg","jpg"}:
        if quality is not None:
            params["quality"] = int(quality)
        params["optimize"] = True
        params["progressive"] = True
    elif ext.lower() == "webp":
        if quality is not None:
            params["quality"] = int(quality)
        params["method"] = 6
    img = normalize_mode_for_format(img, fmt)
    img.save(out, format=fmt, **params)
    return out.getvalue()

def compress_to_max_kb(img: Image.Image, orig_ext: str, max_kb: int, allow_convert_to_jpeg: bool = True):
    """
    Komprimer img, samme opløsning, til <= max_kb hvis muligt.
    Returnerer: (bytes, out_ext, valgt_quality, under_grænse_bool)
    """
    target_bytes = max_kb * 1024
    ext = orig_ext.lower()

    # Tabsformater: binærsøgning i kvalitet
    if ext in {"jpeg","jpg","webp"}:
        low, high = 30, 95
        best_bytes = None
        best_q = None
        under = False

        initial = save_image_bytes(img, ext, quality=high)
        if len(initial) <= target_bytes:
            return initial, ext, high, True

        while low <= high:
            mid = (low + high) // 2
            trial = save_image_bytes(img, ext, quality=mid)
            if len(trial) <= target_bytes:
                best_bytes, best_q, under = trial, mid, True
                low = mid + 1
            else:
                high = mid - 1

        if best_bytes is not None:
            return best_bytes, ext, best_q, under

        lowest = save_image_bytes(img, ext, quality=low)
        return lowest, ext, low, False

    # Tabsløse formater: konverter evt. til JPEG
    if ext in {"png","tiff","bmp"} and allow_convert_to_jpeg:
        conv_ext = "jpeg"
        low, high = 30, 95
        best_bytes = None
        best_q = None
        under = False

        initial = save_image_bytes(img, conv_ext, quality=high)
        if len(initial) <= target_bytes:
            return initial, conv_ext, high, True

        while low <= high:
            mid = (low + high) // 2
            trial = save_image_bytes(img, conv_ext, quality=mid)
            if len(trial) <= target_bytes:
                best_bytes, best_q, under = trial, mid, True
                low = mid + 1
            else:
                high = mid - 1

        if best_bytes is not None:
            return best_bytes, conv_ext, best_q, under

        lowest = save_image_bytes(img, conv_ext, quality=low)
        return lowest, conv_ext, low, False

    # Ellers: gem som originalt (kan være over grænsen)
    raw = save_image_bytes(img, ext, quality=None)
    return raw, ext, -1, (len(raw) <= target_bytes)

def build_archive_name(prefix_aab: bool, objektnr: str, letter: Optional[str], ext: str) -> str:
    base = objektnr.strip()
    if letter:
        base = f"{base} {letter}"
    if prefix_aab:
        base = f"AAB {base}"
    if not base.lower().endswith(f".{ext.lower()}"):
        base = f"{base}.{ext.lower()}"
    return base

def letters_for_group(items: List[str]) -> Dict[str, Optional[str]]:
    """
    a/b/c… i rækkefølge. Hvis kun 1 item i gruppen -> None
    """
    if len(items) <= 1:
        return {items[0]: None} if items else {}
    return {fn: chr(ord('a') + i) for i, fn in enumerate(items)}

# ---------- Session state: grupper & bank ----------
if "groups" not in st.session_state:
    # Hver gruppe: {"id": "G1", "name": "Objektnr her", "items": [filnavne]}
    st.session_state.groups: List[Dict] = []

if "bank" not in st.session_state:
    # "Ufordelte" filnavne
    st.session_state.bank: List[str] = []

def reset_bank_with(files):
    st.session_state.bank = [f.name for f in files]
    # fjern fra grupper alt der ikke længere findes
    existing = set(st.session_state.bank)
    for g in st.session_state.groups:
        g["items"] = [x for x in g["items"] if x in existing]

def add_group():
    idx = len(st.session_state.groups) + 1
    st.session_state.groups.append({"id": f"G{idx}", "name": "", "items": []})

def clear_groups():
    st.session_state.groups = []

def assign_from_sortables(columns_lists: List[List[str]]):
    """
    columns_lists: [bank_list, group1_list, group2_list, ...]
    Opdaterer session_state.bank og .groups[*]['items'] i samme rækkefølge.
    """
    st.session_state.bank = columns_lists[0]
    for i, g in enumerate(st.session_state.groups, start=1):
        g["items"] = columns_lists[i]

# ---------- Sidebar: indstillinger ----------
with st.sidebar:
    st.header("Indstillinger")
    max_kb = st.number_input("Maks filstørrelse for 'lille' (KB)", min_value=10, max_value=20000, value=400, step=10)
    add_aab_prefix = st.checkbox("Sæt 'AAB ' foran filnavnet", value=True)
    allow_jpeg = st.checkbox("Tillad konvertering til JPEG (for at nå maks KB)", value=True)
    st.markdown("---")
    st.caption("‘Stor/’ bevarer opløsning og bytes (kun omdøbt). ‘Lille/’ komprimeres til maks KB – opløsning ændres ikke.")

# ---------- Midterlayout ----------
left_spacer, center, right_spacer = st.columns([1, 2.5, 1])

with center:
    st.subheader("1) Upload billeder")
    files = st.file_uploader("Træk og slip eller vælg filer", type=SUPPORTED_TYPES, accept_multiple_files=True)
    if files:
        reset_bank_with(files)
    else:
        st.info("Upload billeder for at komme i gang.")

    st.subheader("2) Opret grupper (ét objektnummer pr. gruppe)")
    add_cols = st.columns([1,1,6])
    with add_cols[0]:
        if st.button("➕ Tilføj gruppe"):
            add_group()
    with add_cols[1]:
        if st.button("🗑️ Ryd grupper"):
            clear_groups()

    # Navnefelter til grupper (objektnumre)
    if st.session_state.groups:
        name_cols = st.columns(len(st.session_state.groups))
        for i, g in enumerate(st.session_state.groups):
            with name_cols[i]:
                st.text_input(f"Objektnr for {g['id']}", key=f"group_name_{g['id']}", value=g["name"])
                # sync tilbage
                st.session_state.groups[i]["name"] = st.session_state.get(f"group_name_{g['id']}", "")

    st.subheader("3) Fordel billeder til grupper")
    if files:
        file_map = {f.name: f for f in files}

        if HAS_SORTABLES and st.session_state.groups:
            st.caption("Træk billeder fra **Ufordelte** over i de rigtige kasser. Rækkefølgen bestemmer a/b/c …")
            # Forbered lister i samme rækkefølge: bank, G1, G2, ...
            columns_data = [st.session_state.bank] + [g["items"] for g in st.session_state.groups]
            labels = ["Ufordelte"] + [g["id"] for g in st.session_state.groups]
            sorted_lists = sort_items(columns_data, labels=labels, direction="horizontal", key="dnd1")
            # Opdater session state efter drag
            assign_from_sortables(sorted_lists)

            # Thumbnail preview under hver kolonne (overblik)
            st.markdown("—")
            prev_cols = st.columns(len(sorted_lists))
            for idx, lst in enumerate(sorted_lists):
                with prev_cols[idx]:
                    st.write(f"**{labels[idx]}**")
                    if idx > 0:
                        st.caption(f"Objektnr: {st.session_state.groups[idx-1]['name'] or '—'}")
                    for fn in lst:
                        f = file_map[fn]
                        try:
                            f.seek(0)
                            img = safe_open_image(f)
                            st.image(img, caption=fn, use_container_width=True)
                        except Exception as ex:
                            st.error(f"Kan ikke vise {fn}: {ex}")
        else:
            # Fallback: vælg gruppe under hvert preview (ingen ekstern komponent nødvendig)
            if not st.session_state.groups:
                st.info("Tilføj mindst én gruppe for at fordele billeder.")
            else:
                st.caption("Din installation har ikke drag-&-drop-komponenten. Vælg i stedet gruppe under hvert billede.")
                options = ["Ufordelte"] + [g["id"] for g in st.session_state.groups]

                # DEDUP: én samlet liste i visningsrækkefølge
                seen = set()
                ordered_files = []
                for fn in st.session_state.bank:
                    if fn not in seen:
                        seen.add(fn)
                        ordered_files.append(fn)
                for g in st.session_state.groups:
                    for fn in g["items"]:
                        if fn not in seen:
                            seen.add(fn)
                            ordered_files.append(fn)

                cols = st.columns(4)
                for i, fn in enumerate(ordered_files):
                    f = file_map[fn]
                    with cols[i % 4]:
                        try:
                            f.seek(0)
                            img = safe_open_image(f)
                            st.image(img, caption=fn, use_container_width=True)
                        except Exception:
                            st.write(fn)

                        # Nuværende gruppe for filen
                        current_group = "Ufordelte"
                        for g in st.session_state.groups:
                            if fn in g["items"]:
                                current_group = g["id"]
                                break

                        # Stabil og unik key pr. widget
                        safe_key = fn.replace(" ", "_").replace("/", "_").replace("\\", "_")
                        try:
                            default_idx = options.index(current_group)
                        except ValueError:
                            default_idx = 0  # fallback hvis gruppen ikke findes

                        choice = st.selectbox(
                            "Gruppe",
                            options,
                            index=default_idx,
                            key=f"sel_{i}_{safe_key}",
                        )

                        if choice != current_group:
                            # Fjern filen fra ALLE containere først (undgå dobbeltforekomst)
                            st.session_state.bank = [x for x in st.session_state.bank if x != fn]
                            for g in st.session_state.groups:
                                g["items"] = [x for x in g["items"] if x != fn]

                            # Tilføj til nyt valg
                            if choice == "Ufordelte":
                                st.session_state.bank.append(fn)
                            else:
                                for g in st.session_state.groups:
                                    if g["id"] == choice:
                                        g["items"].append(fn)
                                        break

    st.subheader("4) Kør")
    run = st.button("Upload & behandl", type="primary", use_container_width=True)

# ---------- Behandling ----------
results: List[Dict[str, str]] = []
zip_buffer = BytesIO()

if run:
    if "files" not in locals() or not files:
        st.error("Upload billeder først.")
    else:
        file_names = [f.name for f in files]
        grouped_items = set(x for g in st.session_state.groups for x in g["items"])
        # NY validering: tjek faktiske uallokerede ud fra grupper, ikke kun 'bank'
        unassigned = [fn for fn in file_names if fn not in grouped_items]

        if not st.session_state.groups or any(g["name"].strip() == "" for g in st.session_state.groups):
            st.error("Hver gruppe skal have et objektnummer.")
        elif unassigned:
            st.error("Der er stadig ufordelte billeder:\n- " + "\n- ".join(unassigned))
        else:
            # Lav bogstaver for hver gruppe og byg navne
            file_map = {f.name: f for f in files}
            with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as zipf:
                for g in st.session_state.groups:
                    objektnr = g["name"].strip()
                    items = g["items"]

                    # a/b/c pr. gruppens rækkefølge
                    if len(items) <= 1:
                        letters = {items[0]: None} if items else {}
                    else:
                        letters = {fn: chr(ord('a') + i) for i, fn in enumerate(items)}

                    for fn in items:
                        f = file_map[fn]
                        letter = letters.get(fn)
                        original_name = Path(f.name)
                        orig_ext = (original_name.suffix or ".jpg").lstrip(".").lower()

                        # --- STOR: behold original bytes, kun omdøb ---
                        f.seek(0)
                        big_bytes = f.read()
                        big_name = build_archive_name(add_aab_prefix, objektnr, letter, orig_ext)
                        zipf.writestr(f"stor/{big_name}", big_bytes)

                        # --- LILLE: komprimer til maks KB ---
                        f.seek(0)
                        img = safe_open_image(f)
                        w0, h0 = img.size
                        small_bytes, out_ext, used_q, under = compress_to_max_kb(
                            img, orig_ext, int(max_kb), allow_convert_to_jpeg=allow_jpeg
                        )
                        small_name = build_archive_name(add_aab_prefix, objektnr, letter, out_ext)
                        zipf.writestr(f"lille/{small_name}", small_bytes)

                        results.append(
                            {
                                "Gruppe": g["id"],
                                "Objektnr": objektnr,
                                "Fil": fn,
                                "Bogstav": letter if letter else "-",
                                "Original (BxH)": f"{w0}×{h0}",
                                "Stor (navn)": big_name,
                                "Lille (navn)": small_name,
                                "Lille ≤ maks KB": "Ja" if under else "Nej",
                                "Kvalitet/Format": f"{('q='+str(used_q)) if used_q!=-1 else 'n/a'}/{out_ext}",
                                "Lille størrelse": human_size(len(small_bytes)),
                            }
                        )

# ---------- Output ----------
if results:
    st.subheader("Resultat")
    st.dataframe(pd.DataFrame(results), use_container_width=True)

    zip_buffer.seek(0)
    st.download_button(
        label="Download ZIP (stor/ & lille/)",
        data=zip_buffer,
        file_name="arkiv_billeder.zip",
        mime="application/zip",
        use_container_width=True,
    )

# ---------- Hjælp ----------
with center:
    st.caption(
        "Træk billeder til en gruppe (eller vælg i dropdown i fallback). Rækkefølgen i hver gruppe afgør a, b, c… "
        "Navne skabes som “(AAB )?Objektnr [a|b|c]” med original eller konverteret extension. "
        "‘Stor/’ bevarer opløsning (kun omdøbt). ‘Lille/’ komprimeres til maks KB uden at ændre opløsning."
    )
