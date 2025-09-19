from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import base64

import pandas as pd
from PIL import Image, ImageOps
import streamlit as st

# --- streamlit-elements (draggable dashboard) ---
from streamlit_elements import elements, mui, dashboard  # pip install streamlit-elements==0.1.*

# =========================
# Basal opsætning & konstanter
# =========================
st.set_page_config(page_title="Arkiv-Upload (drag thumbnails)", page_icon="🖼️", layout="wide")
st.title("🖼️ Arkiv-Upload — træk thumbnails mellem kolonner")

SUPPORTED = ("jpg", "jpeg", "png", "bmp", "webp", "tiff")
FORMAT_MAP = {"jpg":"JPEG","jpeg":"JPEG","png":"PNG","webp":"WEBP","tiff":"TIFF","bmp":"BMP"}
LOSSY = {"jpeg","jpg","webp"}

TOTAL_COLS = 48            # dashboard grid kolonner (vandret)
ROW_H = 50                 # højere rækker for mere luft
CARD_W = 6                 # grid-bredde for hvert billed-kort
CARD_H = 8                 # grid-højde for kortet
HEADER_H = 2               # grid-højde for kolonne-header

# =========================
# Hjælpere
# =========================
def human_size(num: int) -> str:
    for unit in ["B","KB","MB","GB"]:
        if num < 1024.0: return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"

def safe_open_image(file) -> Image.Image:
    try: file.seek(0)
    except Exception: pass
    img = Image.open(file)
    return ImageOps.exif_transpose(img)

def normalize_mode(img: Image.Image, ext_like: str) -> Image.Image:
    if ext_like.upper() in {"JPEG","JPG"}:
        if img.mode in ("RGBA","LA"):
            from PIL import Image as PILImage
            bg = PILImage.new("RGB", img.size, (255,255,255))
            bg.paste(img, mask=img.split()[-1])
            return bg
        return img.convert("RGB")
    return img

def save_bytes(img: Image.Image, ext: str, quality: Optional[int] = None) -> bytes:
    fmt = FORMAT_MAP.get(ext.lower(), ext.upper())
    buf = BytesIO()
    params = {}
    if ext.lower() in {"jpeg","jpg"}:
        if quality is not None: params["quality"] = int(quality)
        params["optimize"] = True; params["progressive"] = True
    elif ext.lower() == "webp":
        if quality is not None: params["quality"] = int(quality)
        params["method"] = 6
    img = normalize_mode(img, fmt)
    img.save(buf, format=fmt, **params)
    return buf.getvalue()

def compress_to_max_kb(img: Image.Image, orig_ext: str, max_kb: int, allow_convert_to_jpeg: bool = True):
    """Return (bytes, out_ext, chosen_quality, under_limit_bool) — opløsning ændres ikke."""
    target = max_kb * 1024
    ext = orig_ext.lower()

    def try_binary(ext_try: str):
        low, high = 30, 95
        best = None; best_q = None; under = False
        first = save_bytes(img, ext_try, quality=high)
        if len(first) <= target: return first, ext_try, high, True
        while low <= high:
            mid = (low + high) // 2
            trial = save_bytes(img, ext_try, quality=mid)
            if len(trial) <= target:
                best, best_q, under = trial, mid, True
                low = mid + 1
            else:
                high = mid - 1
        if best is not None: return best, ext_try, best_q, under
        lowest = save_bytes(img, ext_try, quality=low)
        return lowest, ext_try, low, False

    if ext in LOSSY:
        return try_binary(ext)
    if ext in {"png","tiff","bmp"} and allow_convert_to_jpeg:
        return try_binary("jpeg")
    raw = save_bytes(img, ext, quality=None)
    return raw, ext, -1, (len(raw) <= target)

def build_name(add_aab: bool, objnr: str, letter: Optional[str], ext: str) -> str:
    base = objnr.strip()
    if letter: base = f"{base} {letter}"
    if add_aab: base = f"AAB {base}"
    if not base.lower().endswith(f".{ext.lower()}"):
        base = f"{base}.{ext.lower()}"
    return base

def letters_for_sorted_by_y(items_y_sorted: List[str]) -> Dict[str, Optional[str]]:
    """items_y_sorted er rækkefølge fra toppen → a, b, c… (1 element => None)."""
    if len(items_y_sorted) <= 1:
        return {items_y_sorted[0]: None} if items_y_sorted else {}
    return {fn: chr(ord('a') + i) for i, fn in enumerate(items_y_sorted)}

def make_thumb_b64(img: Image.Image, max_side=360) -> str:
    th = img.copy()
    th.thumbnail((max_side, max_side))
    b = BytesIO()
    th.save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode("utf-8")

# =========================
# Session state
# =========================
if "files_meta" not in st.session_state:
    # { filename: {"w": int, "h": int, "thumb": b64, "ext": str} }
    st.session_state.files_meta: Dict[str, Dict] = {}

if "layout" not in st.session_state:
    # dashboard layout: { key -> (x,y,w,h) } for billeder
    st.session_state.layout: Dict[str, Tuple[int,int,int,int]] = {}

if "groups" not in st.session_state:
    # grupper: liste af dicts med id & objektnr (header kolonner)
    # index 0 reserveret til "Ufordelte" (tegnes separat)
    st.session_state.groups: List[Dict] = []

# =========================
# Sidebar (enkle indstillinger)
# =========================
with st.sidebar:
    st.header("Indstillinger")
    max_kb = st.number_input("Maks KB for 'lille'", min_value=10, max_value=20000, value=400, step=10)
    add_aab = st.checkbox("Sæt 'AAB ' foran filnavn", value=True)
    allow_jpeg = st.checkbox("Tillad konvertering til JPEG (for at nå maks KB)", value=True)
    st.markdown("---")
    st.caption("‘Stor/’ = originale bytes (kun omdøbt). ‘Lille/’ = samme opløsning, komprimeret til maks KB.")
    

# =========================
# Upload + gruppeknapper
# =========================
L, C, R = st.columns([1, 2.8, 1])
with C:
    st.subheader("1) Upload billeder")
    files = st.file_uploader("Træk og slip eller vælg filer", type=SUPPORTED, accept_multiple_files=True)
    if files:
        # registrér filer + thumbs + initial layout (i Ufordelte)
        for f in files:
            if f.name not in st.session_state.files_meta:
                try:
                    img = safe_open_image(f)
                    b64 = make_thumb_b64(img, 360)
                    st.session_state.files_meta[f.name] = {
                        "w": img.size[0], "h": img.size[1], "thumb": b64,
                        "ext": (Path(f.name).suffix or ".jpg").lstrip(".").lower()
                    }
                except Exception:
                    st.session_state.files_meta[f.name] = {"w": 0, "h": 0, "thumb": "", "ext": (Path(f.name).suffix or ".jpg").lstrip(".").lower()}

            # init placering i "Ufordelte" hvis ikke oprettet
            if f.name not in st.session_state.layout:
                # læg dem i kolonne 0 (Ufordelte), stak nedad
                count_in_bank = sum(1 for k,(x,_,_,_) in st.session_state.layout.items() if x == 0)
                st.session_state.layout[f.name] = (0, HEADER_H + count_in_bank*(CARD_H+1), CARD_W, CARD_H)

        # (Re)byg thumbnails hvis nogen mangler (fx ved reload)
        for f in files:
            if f.name in st.session_state.files_meta and not st.session_state.files_meta[f.name].get("thumb"):
                try:
                    f.seek(0)
                    _img = safe_open_image(f)
                    st.session_state.files_meta[f.name]["thumb"] = make_thumb_b64(_img, 360)
                except Exception:
                    st.session_state.files_meta[f.name]["thumb"] = ""
    else:
        st.info("Upload for at fortsætte.")

    st.subheader("2) Kolonner")
    cc1, cc2 = st.columns([1,1])
    with cc1:
        if st.button("➕ Tilføj kolonne (gruppe)"):
            idx = len(st.session_state.groups) + 1
            st.session_state.groups.append({"id": f"G{idx}", "obj": ""})
    with cc2:
        if st.button("🗑️ Ryd alle kolonner"):
            st.session_state.groups = []
            # flyt alle items tilbage til Ufordelte (x=0)
            for k,(x,y,w,h) in list(st.session_state.layout.items()):
                st.session_state.layout[k] = (0, y, w, h)

    if st.session_state.groups:
        name_cols = st.columns(len(st.session_state.groups))
        for i, g in enumerate(st.session_state.groups):
            with name_cols[i]:
                st.text_input(f"Objektnr for {g['id']}", key=f"obj_{g['id']}", value=g["obj"])
                st.session_state.groups[i]["obj"] = st.session_state.get(f"obj_{g['id']}", "")

# =========================
# Funktion: kolonnegeometri
# =========================
def column_x_ranges() -> List[Tuple[int,int,str]]:
    """
    Returnerer liste af (x_start, x_end, label) for kolonner:
    0: Ufordelte, derefter hver gruppe.
    """
    col_count = 1 + len(st.session_state.groups)
    if col_count <= 0: return []
    # Fordel grid-værdier: første kolonne ca. 12%, resten ligeligt
    bank_w = max(6, int(TOTAL_COLS * 0.12))          # min 6 "grid units"
    remain = max(1, TOTAL_COLS - bank_w)
    each = remain // max(1, len(st.session_state.groups)) if st.session_state.groups else 0

    ranges = []
    # Ufordelte:
    ranges.append((0, max(1, bank_w)-1, "Ufordelte"))
    # Grupper:
    x = bank_w
    for g in st.session_state.groups:
        x_start = x
        x_end = min(TOTAL_COLS-1, x_start + max(6, each) - 1)
        ranges.append((x_start, x_end, g["id"]))
        x = x_end + 1
    return ranges

def clamp_to_column(x: int, col_idx: int) -> int:
    xr = column_x_ranges()[col_idx]
    x_start, x_end, _ = xr
    width = CARD_W
    # snap venstre kant inden for spændet
    return max(x_start, min(x_end - width + 1, x))

def which_column(x_center: int) -> int:
    """Find kolonne ud fra kortets center-x (grid units)."""
    for i,(xs,xe,_) in enumerate(column_x_ranges()):
        if xs <= x_center <= xe:
            return i
    # udenfor -> Ufordelte
    return 0

# =========================
# Rendér dashboard med streamlit-elements
# =========================
C2 = st.container()
with C2:
    st.subheader("3) Træk thumbnails mellem kolonner (øverst=a, derefter b, c …)")
    if not files:
        st.info("Upload billeder for at se boardet.")
    else:
        # Byg dashboard layout: headere + billedkort
        ranges = column_x_ranges()

        layout_list = []
        # Header-items
        for i,(xs, _, label) in enumerate(ranges):
            key = f"__hdr__{label}"
            layout_list.append(dashboard.Item(key, xs, 0, CARD_W+2, HEADER_H, isDraggable=False, isResizable=False, moved=False))
        # Billedkort
        for fn, (x,y,w,h) in st.session_state.layout.items():
            layout_list.append(dashboard.Item(fn, x, y, w, h))

        # Vi tracker nye positioner efter drag
        updated_positions: Dict[str, Tuple[int,int,int,int]] = {}

        def on_layout_change(updated_layout):
            # updated_layout er liste af dicts m. nøgler: i,x,y,w,h
            for it in updated_layout:
                k = it.get("i")
                if k and not k.startswith("__hdr__"):
                    updated_positions[k] = (
                        it.get("x",0), it.get("y",0),
                        it.get("w",CARD_W), it.get("h",CARD_H)
                    )

        # Selve boardet
        with elements("board"):
            with dashboard.Grid(
                layout_list,
                cols=TOTAL_COLS,
                rowHeight=ROW_H,
                draggableHandle=".dragme",
                preventCollision=True,
                onLayoutChange=on_layout_change,
            ):
                # Render headere
                for i,(xs, _, label) in enumerate(ranges):
                    key = f"__hdr__{label}"
                    with mui.Paper(key=key, elevation=1, sx={"p": 1.0, "bgcolor":"#f7f7f7", "borderRadius": 2}):
                        mui.Typography(
                            label if i==0 else f"{label} — objektnr: {st.session_state.groups[i-1]['obj'] if i>0 else ''}",
                            variant="subtitle2"
                        )

                # Render billed-kort
                present_keys = [it["i"] for it in layout_list if not it["i"].startswith("__hdr__")]
                for fn, meta in st.session_state.files_meta.items():
                    if fn not in present_keys:
                        continue
                    thumb64 = meta["thumb"]
                    with mui.Card(key=fn, elevation=3, sx={"borderRadius": 2, "overflow":"hidden"}):
                        with mui.CardActionArea(className="dragme"):  # drag handle
                            if thumb64:
                                mui.CardMedia(
                                    component="img",
                                    image=f"data:image/png;base64,{thumb64}",
                                    sx={"width": "100%", "display": "block"}
                                )
                            with mui.CardContent(sx={"p":1}):
                                mui.Typography(fn, variant="caption")

        # Efter boardet: gem nye positioner og SNAP til nærmeste kolonne
        if updated_positions:
            for k,(x,y,w,h) in updated_positions.items():
                st.session_state.layout[k] = (x,y,w,h)

            # snap ‘x’ ind i nærmeste kolonne
            ranges = column_x_ranges()
            for k,(x,y,w,h) in list(st.session_state.layout.items()):
                cx = x + w//2
                col_idx = which_column(cx)
                snapped_x = clamp_to_column(x, col_idx)
                st.session_state.layout[k] = (snapped_x, y, w, h)

# =========================
# Behandling
# =========================
results: List[Dict[str, str]] = []
zip_buf = BytesIO()

C3 = st.container()
with C3:
    st.subheader("4) Behandl")
    run = st.button("Behandl & download ZIP", type="primary", use_container_width=True)

if run:
    if not files:
        st.error("Upload billeder først.")
    elif not st.session_state.groups or any(g["obj"].strip()=="" for g in st.session_state.groups):
        st.error("Hver gruppe-kolonne skal have et objektnummer.")
    else:
        # kolonne-info
        ranges = column_x_ranges()
        col_info = []
        for idx,(xs,xe,label) in enumerate(ranges):
            if idx==0:
                col_info.append((label, ""))  # Ufordelte (ignoreres ved output)
            else:
                col_info.append((label, st.session_state.groups[idx-1]["obj"].strip()))

        # sorter items pr. kolonne efter y (top først)
        cols_items: Dict[int, List[Tuple[str,int]]] = {i:[] for i in range(len(ranges))}
        for fn,(x,y,w,h) in st.session_state.layout.items():
            cx = x + w//2
            col_idx = which_column(cx)
            cols_items[col_idx].append((fn,y))
        for i in cols_items.keys():
            cols_items[i].sort(key=lambda t: t[1])  # efter y

        # valider: ingen i "Ufordelte"
        unassigned = [fn for (fn,_) in cols_items.get(0,[])]
        if unassigned:
            st.error("Træk alle billeder fra ‘Ufordelte’ til en gruppe-kolonne først:\n- " + "\n- ".join(unassigned))
        else:
            # map filnavn -> UploadedFile
            fmap = {f.name: f for f in files}
            with ZipFile(zip_buf, "w", ZIP_DEFLATED) as zipf:
                for col_idx in range(1, len(ranges)):
                    _, objektnr = col_info[col_idx]
                    ordered_fns = [fn for (fn,_) in cols_items[col_idx]]  # top→bund
                    letters = letters_for_sorted_by_y(ordered_fns)
                    for fn in ordered_fns:
                        f = fmap[fn]
                        letter = letters.get(fn)
                        orig_ext = (Path(f.name).suffix or ".jpg").lstrip(".").lower()

                        # STOR: original bytes, nyt navn
                        f.seek(0)
                        big_bytes = f.read()
                        big_name = build_name(add_aab, objektnr, letter, orig_ext)
                        zipf.writestr(f"stor/{big_name}", big_bytes)

                        # LILLE: komprimer til maks KB
                        f.seek(0)
                        img = safe_open_image(f)
                        small_bytes, out_ext, q, under = compress_to_max_kb(
                            img, orig_ext, int(max_kb), allow_convert_to_jpeg=allow_jpeg
                        )
                        small_name = build_name(add_aab, objektnr, letter, out_ext)
                        zipf.writestr(f"lille/{small_name}", small_bytes)

                        results.append({
                            "Kolonne": col_info[col_idx][0],
                            "Objektnr": objektnr,
                            "Fil": fn,
                            "Bogstav": letter or "-",
                            "Lille ≤ maks KB": "Ja" if under else "Nej",
                            "Lille størrelse": human_size(len(small_bytes)),
                        })

# =========================
# Output
# =========================
if results:
    st.subheader("Resultat")
    st.dataframe(pd.DataFrame(results), use_container_width=True)
    zip_buf.seek(0)
    st.download_button(
        "Download ZIP (stor/ & lille/)",
        data=zip_buf,
        file_name="arkiv_billeder.zip",
        mime="application/zip",
        use_container_width=True,
    )
