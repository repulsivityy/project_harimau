import streamlit as st
import requests
from api_client import HarimauAPIClient
from components.sidebar import render_sidebar
from components.investigation_tracker import render_investigation_tracker
from components.results_tabs import render_tabs

# Config
st.set_page_config(page_title="Project Harimau", page_icon="🐯", layout="wide")
api = HarimauAPIClient()

st.title("🐯 Project Harimau - AI Threat Hunter")

# Render Sidebar and get Graph Control Settings
graph_settings = render_sidebar(api)

# Main Interface Header
st.write("Harimau (Tiger in Malay) is an AI-powered threat hunting platform that uses multiple specialised threat hunt agents to analyze and investigate IOCs (IPs, Domains, Hashes, URLs).")
st.write("Harimau leverages LangGraph with multiple specialised threat hunt agents to mimic the flow of a threat hunting program.")
st.write("Harimau is currently in Beta Phase. Expect some bugs and unexpected behaviour. Current investigation takes ~8 minutes to complete.")
st.write("### Investigation Console\n")

# Input Section
col1, col2 = st.columns([3, 1])
with col1:
    ioc_input = st.text_input("Enter IOC (IP, Domain, Hash, URL)", placeholder="e.g., 1.1.1.1")
with col2:
    st.write("") # Spacer
    st.write("") # Spacer
    submit_btn = st.button("Start Investigation", type="primary", use_container_width=True)

# Submit New Job
if submit_btn and ioc_input:
    with st.spinner("The 🐯 Tiger is hunting..."):
        job_id = api.submit_investigation(ioc_input, max_iterations=graph_settings.get("max_iterations", 3))
        st.session_state.current_job_id = job_id
        st.toast(f"Job Initiated: {job_id}", icon="🚀")

# Render Active Investigation
if st.session_state.current_job_id:
    job_id = st.session_state.current_job_id
    st.markdown("---")
    st.subheader("Current Investigation")
    st.caption(f"**Job ID:** `{job_id}`")
    
    try:
        # Check current status
        current_status = api.get_investigation(job_id).get("status")
        
        # 1. Render Progress Tracker (SSE / Polling) if running
        if current_status == "running":
            render_investigation_tracker(api, job_id)
            
        # 2. Display Results Tabs (Always rendered if there are results)
        res = api.get_investigation(job_id)
        if res and res.get("status") == "completed":
            render_tabs(api, job_id, res, graph_settings)
            
    except requests.exceptions.ConnectionError:
        st.error("🔌 Cannot connect to backend server")
        st.warning("**Solution:** Ensure backend is running on port 8080")
        st.code("cd backend && uvicorn backend.main:app --host 0.0.0.0 --port 8080", language="bash")
    except requests.exceptions.Timeout:
        st.error("⏱️ Request timed out")
        st.info("The backend may be overloaded or the investigation is taking too long.")
    except requests.exceptions.HTTPError as e:
        st.error(f"🌐 HTTP Error: {e.response.status_code}")
        st.write(f"**Details:** {e.response.text}")
    except ValueError as e:
        st.error(f"📝 Invalid input or response format")
        with st.expander("Error details"):
            st.exception(e)
    except Exception as e:
        st.error(f"❌ Unexpected error: {type(e).__name__}")
        with st.expander("🔍 Full error traceback"):
            st.exception(e)
        st.info("**Tip:** Check browser console (F12) for additional details")