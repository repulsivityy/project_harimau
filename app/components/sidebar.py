import streamlit as st
from api_client import HarimauAPIClient

def render_sidebar(api: HarimauAPIClient):
    """Renders the Streamlit sidebar containing system status and graph controls."""
    
    # State Management for Persistence
    if "current_job_id" not in st.session_state:
        st.session_state.current_job_id = None
    if "graph_recenter_key" not in st.session_state:
        st.session_state.graph_recenter_key = 0
    if "graph_key" not in st.session_state:
        st.session_state.graph_key = 0

    with st.sidebar:
        st.header("System Status")
        if api.health_check():
            st.success("Backend Online")
        else:
            st.error("Backend Offline")
            st.warning("Ensure backend is running on port 8080")
            
        st.markdown("---")
        st.subheader("🎛️ Graph Controls")
        
        if st.button("🔄 Recenter Graph", use_container_width=True):
            st.session_state.graph_key += 1
            st.rerun()  # Force full refresh to reset graph
            
        physics_enabled = st.checkbox("Enable Physics", value=True, help="Dynamic node positioning")
        show_labels = st.checkbox("Show Edge Labels", value=True, help="Display relationship types")
        node_size = st.slider("Node Size", 10, 50, 15, help="Adjust node diameter")
        link_distance = st.slider("Link Distance", 50, 1000, 200, help="Space between nodes")
        
    return {
        "physics_enabled": physics_enabled,
        "show_labels": show_labels,
        "node_size": node_size,
        "link_distance": link_distance
    }
