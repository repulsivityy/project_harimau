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
        
        st.markdown("---")
        st.subheader("🔬 Investigation Settings")
        max_iterations = st.slider(
            "Investigation Depth (iterations)",
            min_value=1,
            max_value=5,
            value=3,
            help="Higher = deeper pivots, higher cost. Lower = faster, cheaper."
        )

        st.markdown("---")
        st.subheader("🕰️ Recent Investigations")
        try:
            recent_jobs = api.get_investigations(limit=5)
            if not recent_jobs:
                st.info("No recent investigations found.")
            else:
                for job in recent_jobs:
                    # e.g. "1.1.1.1 (completed)"
                    label = f"{job.get('ioc')} ({job.get('status')})"
                    if st.button(label, key=f"btn_{job.get('job_id')}", use_container_width=True):
                        st.session_state.current_job_id = job.get('job_id')
                        st.session_state.graph_key += 1
                        st.rerun()
        except Exception as e:
            st.error("Could not load history.")
        
    return {
        "physics_enabled": physics_enabled,
        "show_labels": show_labels,
        "node_size": node_size,
        "link_distance": link_distance,
        "max_iterations": max_iterations
    }
