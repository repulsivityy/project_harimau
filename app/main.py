import streamlit as st
import os
import requests

# Config
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")

st.set_page_config(page_title="Harimau V2", page_icon="🐯", layout="wide")

st.title("🐯 Harimau Threat Hunter V2")

st.sidebar.header("Status")
if st.sidebar.button("Ping Backend"):
    try:
        res = requests.get(f"{BACKEND_URL}/health", timeout=5)
        if res.status_code == 200:
            st.sidebar.success(f"Connected! {res.json()}")
        else:
            st.sidebar.error(f"Error: {res.status_code}")
    except Exception as e:
        st.sidebar.error(f"Connection Failed: {e}")

st.write("### Investigation Console")
st.info("System Ready for Deployment. Phase 1 Verification Mode.")
