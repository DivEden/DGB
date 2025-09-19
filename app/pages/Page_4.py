# app_min_drag.py
from io import BytesIO
from typing import Dict, Tuple, List
import base64

import streamlit as st
from PIL import Image, ImageDraw
from streamlit_elements import elements, mui, dashboard

st.set_page_config(page_title="Mini Drag Thumbnails", layout="wide")
st.title("✅ Mini drag-demo (uden upload)")

TOTAL_COLS = 24
ROW_H     = 50
CARD_W    = 6
CARD_H    = 8
HEADER_H  = 2

def make_dummy_thumb_b64(w=480, h=320, color=(60,160,255), label="BILLEDE"):
    im = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(im)
    d.rectangle((10, 10, w-10, h-10), outline=(255, 255, 255), width=6)
    d.text((20, h//2 - 10), label, fill=(255, 255, 255))
    im.thumbnail((360, 360))
    b = BytesIO()
    im.save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode("utf-8")

# ---------- State ----------
if "files_meta" not in st.session_state:
    # to demo-billeder
    st.session_state.files_meta = {
        "A.png": {"thumb": make_dummy_thumb_b64(color=(220,80,70), label="A")},
        "B.png": {"thumb": make_dummy_thumb_b64(color=(60,160,255), label="B")},
    }

if "layout" not in st.session_state:
    # start begge i venstre kolonne ("Ufordelte")
    st.session_state.layout = {
        "A.png": (0, HEADER_H + 0*(CARD_H+1), CARD_W, CARD_H),
        "B.png": (0, HEADER_H + 1*(CARD_H+1), CARD_W, CARD_H),
    }

# ---------- Kolonner ----------
def column_x_ranges() -> List[Tuple[int,int,str]]:
    # venstre = Ufordelte (ca. 35%), højre = Gruppe A (resten)
    left_w = max(6, int(TOTAL_COLS * 0.35))
    left  = (0, left_w-1, "Ufordelte")
    right = (left_w, TOTAL_COLS-1, "Gruppe A")
    return [left, right]

def which_column_by_center(x: int, w: int) -> int:
    cx = x + w//2
    for i,(xs,xe,_) in enumerate(column_x_ranges()):
        if xs <= cx <= xe:
            return i
    return 0

def snap_x_to_column(x: int, w: int, col_idx: int) -> int:
    xs, xe, _ = column_x_ranges()[col_idx]
    return max(xs, min(xe - w + 1, x))

# ---------- Board ----------
ranges = column_x_ranges()

# layout: headere + kort
layout_items = []
for (xs, _, label) in ranges:
    key = f"__hdr__{label}"
    layout_items.append(dashboard.Item(key, xs, 0, CARD_W+2, HEADER_H,
                                       isDraggable=False, isResizable=False, moved=False))

for fn, (x,y,w,h) in st.session_state.layout.items():
    layout_items.append(dashboard.Item(fn, x, y, w, h))

updated_positions: Dict[str, Tuple[int,int,int,int]] = {}

def on_layout_change(updated_layout):
    for it in updated_layout:
        k = it.get("i")
        if not k or k.startswith("__hdr__"):
            continue
        updated_positions[k] = (
            it.get("x",0), it.get("y",0),
            it.get("w",CARD_W), it.get("h",CARD_H)
        )

# sanity: hvis denne knap vises, virker streamlit-elements
with elements("sanity"):
    mui.Button("MUI OK", color="success", variant="contained")

st.caption("Træk kortene (A og B) mellem venstre/højre kolonne. Ingen upload nødvendig.")

with elements("board_min"):
    with dashboard.Grid(
        layout_items,
        cols=TOTAL_COLS,
        rowHeight=ROW_H,
        preventCollision=True,          # ingen handle → træk overalt
        onLayoutChange=on_layout_change,
    ):
        # headere
        for (xs, _, label) in ranges:
            key = f"__hdr__{label}"
            with mui.Paper(key=key, elevation=1, sx={"p": 1.0, "bgcolor":"#f7f7f7", "borderRadius": 2}):
                mui.Typography(label, variant="subtitle2")

        # kort
        for fn, meta in st.session_state.files_meta.items():
            thumb64 = meta.get("thumb", "")
            with mui.Card(key=fn, elevation=3, sx={"borderRadius": 2, "overflow":"hidden"}):
                if thumb64:
                    mui.CardMedia(component="img",
                                  image=f"data:image/png;base64,{thumb64}",
                                  sx={"width": "100%", "display": "block"})
                with mui.CardContent(sx={"p":1}):
                    mui.Typography(fn, variant="caption")

# efter drag: gem & snap
if updated_positions:
    for k,(x,y,w,h) in updated_positions.items():
        st.session_state.layout[k] = (x,y,w,h)
    for k,(x,y,w,h) in list(st.session_state.layout.items()):
        col = which_column_by_center(x, w)
        st.session_state.layout[k] = (snap_x_to_column(x, w, col), y, w, h)
