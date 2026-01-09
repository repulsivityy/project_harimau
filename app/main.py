import streamlit as st
import time
from api_client import HarimauAPIClient

# Config
st.set_page_config(page_title="Harimau V2", page_icon="🐯", layout="wide")
api = HarimauAPIClient()

st.title("🐯 Harimau Threat Hunter V2")

# Sidebar Status
with st.sidebar:
    st.header("System Status")
    if api.health_check():
        st.success("Backend Online")
    else:
        st.error("Backend Offline")
        st.warning("Ensure backend is running on port 8080")

# Main Interface
st.write("### Investigation Console")

col1, col2 = st.columns([3, 1])
with col1:
    ioc_input = st.text_input("Enter IOC (IP, Domain, Hash, URL)", placeholder="e.g., 1.1.1.1")
with col2:
    st.write("") # Spacer
    st.write("") # Spacer
    submit_btn = st.button("Start Investigation", type="primary", use_container_width=True)

if submit_btn and ioc_input:
    try:
        # 1. Submit Job
        with st.spinner("Submitting job to Brain..."):
            job_id = api.submit_investigation(ioc_input)
            st.toast(f"Job Initiated: {job_id}", icon="🚀")
            
        # 2. Poll for Completion
        status_placeholder = st.status("Investigation in progress...", expanded=True)
        complete = False
        
        while not complete:
            data = api.get_investigation(job_id)
            status = data.get("status")
            
            if status == "completed":
                status_placeholder.update(label="Investigation Complete!", state="complete", expanded=False)
                complete = True
            elif status == "failed":
                status_placeholder.update(label="Investigation Failed", state="error")
                st.error("The investigation failed on the backend.")
                st.stop()
            else:
                # Show active agents if available (future feature)
                status_placeholder.write(f"Status: {status}...")
                time.sleep(2)
                
        # 3. Display Results
        res = api.get_investigation(job_id)
        subtasks = res.get("subtasks", [])
        
        st.success("Investigation Complete!")
        
        # Tabs for different views
        tab1, tab2, tab3 = st.tabs(["📝 Triage & Plan", "🕸️ Graph", "📄 Final Report"])
        
        with tab1:
            st.subheader("Triage Assessment")
            
            # Extract Rich Intel
            rich_intel = res.get("rich_intel", {})
            t_score = rich_intel.get("threat_score")
            verdict = rich_intel.get("verdict")
            mal_stats = rich_intel.get("malicious_stats")
            desc = rich_intel.get("description")
            
            # Row 1: High Level Signal
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("IOC Type", res.get("ioc_type", "Unknown").upper())
            col_b.metric("Verdict", verdict if verdict else "Unknown")
            col_c.metric("Threat Score", f"{t_score}/100" if t_score else "N/A")
            total_stats = rich_intel.get("total_stats", 0)
            col_d.metric("VT Verdict", f"{mal_stats}/{total_stats}" if total_stats > 0 else "0/0")
            
            # Row 2: Description
            if desc:
                st.info(f"**Analysis (Automated):** {desc}")
                
            t_summary = rich_intel.get("triage_summary")
            if t_summary:
                st.markdown("### 🛡️ Analyst Summary")
                st.markdown(t_summary)
            
            st.divider()
            
            st.write("#### Generated Agent Tasks")
            for task in subtasks:
                with st.expander(f"🤖 {task.get('agent', 'Agent')} - {task.get('task')[:50]}..."):
                    st.write(task.get('task'))

        with tab2:
            st.subheader("Investigation Graph")
            
            # Fetch Graph Data
            try:
                graph_data = api.get_graph_data(job_id)
                from streamlit_agraph import agraph, Node, Edge, Config
                
                nodes = []
                edges = []
                for n in graph_data.get("nodes", []):
                    nodes.append(Node(id=n["id"], label=n["label"], size=n.get("size", 25), color=n.get("color", "#FF4B4B")))
                for e in graph_data.get("edges", []):
                    edges.append(Edge(source=e["source"], target=e["target"], label=e.get("label", "")))
                
                if not nodes:
                    st.warning("No graph nodes generated. Triage might have returned no tasks.")
                else:
                    config = Config(width=None, 
                                    height=500, 
                                    directed=True, 
                                    physics=True, 
                                    hierarchical=False)
                    agraph(nodes=nodes, edges=edges, config=config)
            except Exception as e:
                st.error(f"Graph Error: {e}")

        with tab3:
            st.subheader("Final Intelligence Report")
            report = res.get("final_report", "No report available.")
            st.markdown(report)

    except Exception as e:
        st.error(f"An error occurred: {e}")
