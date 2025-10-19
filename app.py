import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# ========== PAGE CONFIG ==========
st.set_page_config(
    page_title="Proactive CRM Expiration Agent",
    layout="wide",
    page_icon="🚀"
)

# ========== CUSTOM STYLES ==========
st.markdown("""
<style>
/* Global Page */
html, body, [class*="css"] {
    background-color: #f7f9fc !important;
    font-family: 'Inter', sans-serif !important;
}

/* Center the upload card container */
.upload-container {
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
}



/* Gradient Title */
.main-title {
    font-size: 2.5rem;
    font-weight: 800;
    text-align: center;
    background: linear-gradient(90deg, #007bff 0%, #00d4ff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.2em;
}

/* Subtitle */
.subheader {
    text-align: center;
    color: #555;
    font-size: 1.1rem;
    margin-bottom: 2rem;
}

/* Sidebar Styling */
[data-testid="stSidebar"] {
    background-color: #111 !important;
    color: white !important;
}
[data-testid="stSidebar"] * {
    color: white !important;
}

/* Buttons */
.stDownloadButton button, .stButton button {
    background: linear-gradient(90deg, #007bff, #00c6ff);
    color: white !important;
    font-weight: 600;
    border-radius: 10px;
    padding: 0.6rem 1.4rem;
    border: none;
    transition: all 0.2s ease-in-out;
}
.stDownloadButton button:hover, .stButton button:hover {
    transform: scale(1.05);
}

/* Data Table */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
    background: white;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

/* Footer */
.footer {
    text-align: center;
    color: gray;
    font-size: 0.9rem;
    margin-top: 2rem;
}
</style>
""", unsafe_allow_html=True)

# ========== HEADER ==========
st.markdown('<h1 class="main-title">🚀 Proactive CRM Expiration Agent</h1>', unsafe_allow_html=True)
st.markdown('<p class="subheader">Automatically identify upcoming contract expirations — act before they expire.</p>', unsafe_allow_html=True)

# ========== UPLOAD SECTION ==========
st.markdown('<div class="upload-container"><div class="upload-card">', unsafe_allow_html=True)

st.markdown("### 📤 Upload Your Excel or CSV File")
st.write("Ensure your file contains the columns: **Customer Name**, **Product**, **Warranty Expiry**, and **Maintenance Expiry**")

uploaded_file = st.file_uploader("Upload Excel/CSV file", type=["xlsx", "xls", "csv"])

st.markdown('</div></div>', unsafe_allow_html=True)

# ========== CORE FUNCTIONS ==========
def excel_date_to_datetime(x):
    if pd.isna(x):
        return None
    if isinstance(x, (int, float, np.number)):
        try:
            return pd.to_datetime('1899-12-30') + pd.to_timedelta(int(x), unit='D')
        except Exception:
            return None
    try:
        return pd.to_datetime(x, errors='coerce')
    except:
        return None

def normalize_dates(df, col):
    if col not in df.columns:
        return df
    df[col + "_dt"] = df[col].apply(excel_date_to_datetime)
    return df

# ========== PROCESSING ==========
if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file, engine="openpyxl")
    except Exception as e:
        st.error(f"❌ Could not read file: {e}")
        st.stop()

    df.columns = df.columns.str.strip()
    st.markdown("### ✅ File Uploaded Successfully!")
    st.success(f"Detected {len(df)} rows. Processing...")

    df = normalize_dates(df, "Warranty Expiry")
    df = normalize_dates(df, "Maintenance Expiry")

    now = pd.to_datetime(datetime.utcnow())
    rows = []

    for _, r in df.iterrows():
        base = {"Customer Name": r.get("Customer Name", ""), "Product": r.get("Product", "")}
        for tcol, tname in [("Warranty Expiry_dt", "Warranty"), ("Maintenance Expiry_dt", "Maintenance")]:
            d = r.get(tcol)
            if pd.notna(d):
                days_left = (d - now).days
                rows.append({**base, "Expiry Type": tname, "Expiry Date": d.date(), "Days Left": days_left})

    if not rows:
        st.warning("⚠️ No valid expiry dates found.")
        st.stop()

    out = pd.DataFrame(rows)
    proactive_window = st.sidebar.number_input("🕒 Proactive window (days)", 30, 365, 90)
    out = out[(out["Days Left"] >= 0) & (out["Days Left"] <= proactive_window)].copy()
    out = out.sort_values(["Days Left", "Customer Name"])

    # Sidebar filters
    st.sidebar.header("🔍 Filters")
    customers = ["All"] + sorted(out["Customer Name"].unique().tolist())
    products = ["All"] + sorted(out["Product"].unique().tolist())
    expiry_types = out["Expiry Type"].unique().tolist()

    selected_customer = st.sidebar.selectbox("Customer", customers)
    selected_product = st.sidebar.selectbox("Product", products)
    selected_types = st.sidebar.multiselect("Expiry Type", expiry_types, default=expiry_types)

    filtered = out.copy()
    if selected_customer != "All":
        filtered = filtered[filtered["Customer Name"] == selected_customer]
    if selected_product != "All":
        filtered = filtered[filtered["Product"] == selected_product]
    if selected_types:
        filtered = filtered[filtered["Expiry Type"].isin(selected_types)]

    st.markdown("### 📋 Expiration Report")
    st.write(f"Showing {len(filtered)} items expiring within {proactive_window} days.")
    st.dataframe(filtered.reset_index(drop=True), height=450)

    # Download button
    csv = filtered.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Download Filtered Report", csv, "CRM_Expirations.csv", "text/csv")

else:
    st.info("👆 Upload your Excel or CSV file to start processing.")

# ========== FOOTER ==========
st.markdown('<div class="footer">Built with ❤️ by <b>Thaslim Thoufica</b></div>', unsafe_allow_html=True)
