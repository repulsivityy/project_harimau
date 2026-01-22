import streamlit as st
import time
import requests
from datetime import datetime
from api_client import HarimauAPIClient

# Config
st.set_page_config(page_title="Project Harimau", page_icon="🐯", layout="wide")
api = HarimauAPIClient()

st.title("🐯 Project Harimau - AI Threat Hunter")

# Sidebar Status
with st.sidebar:
    st.header("System Status")
    if api.health_check():
        st.success("Backend Online")
    else:
        st.error("Backend Offline")
        st.warning("Ensure backend is running on port 8080")

# Main Interface
st.write("Project Harimau (Tiger in Malay) is an automated threat hunting platform that uses AI to analyze and investigate IOCs (IPs, Domains, Hashes, URLs). ")
st.write("Harimau leverages LangGraph with multiple specialised threat hunt agents to mimic the flow of a threat hunting program.")
st.write("\n")
st.write("### Investigation Console")
st.write("\n")

col1, col2 = st.columns([3, 1])
# Initialize session state
if "job_id" not in st.session_state:
    st.session_state.job_id = None
if "job_ioc" not in st.session_state:
    st.session_state.job_ioc = ""

# ... (UI Layout Code) ...

col1, col2 = st.columns([3, 1])
with col1:
    ioc_input = st.text_input("Enter IOC (IP, Domain, Hash, URL)", 
                              placeholder="e.g., 1.1.1.1",
                              value=st.session_state.job_ioc if not st.session_state.job_ioc else "") 

    pass # Replaced by below
    
with col2:
    st.write("") # Spacer
    st.write("") # Spacer
    submit_btn = st.button("Start Investigation", type="primary", use_container_width=True)

# Logic: New Submission
if submit_btn and ioc_input:
    try:
        with st.spinner("The 🐯 Tiger is hunting..."):
            job_id = api.submit_investigation(ioc_input)
            st.session_state.job_id = job_id
            st.session_state.job_ioc = ioc_input
            st.toast(f"Job Initiated: {job_id}", icon="🚀")
            st.rerun() # Force rerun to switch to "View Mode"
    except Exception as e:
        st.error(f"Failed to submit job: {str(e)}")

# Logic: View Active/Completed Job
if st.session_state.job_id:
    job_id = st.session_state.job_id
    
    # Poll for Completion with Progress Bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    progress_details = st.empty()
    
    complete = False
    poll_count = 0
    max_polls = 150  # 5 minutes with 2s intervals
    
    while not complete and poll_count < max_polls:
        data = api.get_investigation(job_id)
        status = data.get("status")
        
        # Calculate progress (you can enhance this based on actual backend progress)
        progress = min(poll_count * 2, 95) if status == "running" else 100
        progress_bar.progress(progress)
        
        if status == "completed":
            progress_bar.progress(100)
            status_text.success("✅ Investigation Complete!")
            complete = True
        elif status == "failed":
            progress_bar.empty()
            status_text.error("❌ Investigation Failed")
            st.error("The investigation failed on the backend.")
            st.stop()
            # Show active agents if available
            active_agent = data.get("current_agent", "Processing")
            status_text.info(f"🤖 Status: {status} | Agent: {active_agent}")
            progress_details.caption(f"Poll #{poll_count + 1} | Elapsed: {poll_count * 2}s")
            time.sleep(2)
            poll_count += 1
                
        # 3. Display Results
        res = api.get_investigation(job_id)
        subtasks = res.get("subtasks", [])
                
        # Tabs for different views
        tab1, tab2, tab3, tab4 = st.tabs(["📝 Triage & Plan", "🕸️ Graph", "📄 Final Report", "⏱️ Timeline"])
        
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
            col_a.metric("IOC Type", (res.get("ioc_type") or "Unknown").upper())
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
            
            # Agent Task Status Cards
            for idx, task in enumerate(subtasks):
                agent_name = task.get('agent', 'Agent')
                task_desc = task.get('task', 'No description')
                status = task.get('status', 'pending')
                
                # Determine status icon and color
                if status == "completed":
                    status_icon = "✅"
                    border_color = "#28a745"
                elif status == "running":
                    status_icon = "⏳"
                    border_color = "#ffc107"
                elif status == "failed":
                    status_icon = "❌"
                    border_color = "#dc3545"
                else:
                    status_icon = "⏸️"
                    border_color = "#6c757d"
                
                st.markdown(f"""
                <div style="
                    border-left: 4px solid {border_color};
                    padding: 12px 16px;
                    margin: 8px 0;
                    background-color: rgba(255, 255, 255, 0.05);
                    border-radius: 4px;
                ">
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 20px; margin-right: 10px;">{status_icon}</span>
                        <strong style="font-size: 16px;">{agent_name}</strong>
                    </div>
                    <p style="margin: 0; color: #aaa; font-size: 14px;">{task_desc}</p>
                </div>
                """, unsafe_allow_html=True)
        
            #  Agent Transparency Section
            st.markdown("---")
            with st.expander("🔍 Agent Transparency", expanded=False):
                st.caption("See what the Triage Agent is thinking and doing under the hood")
                
                # Tool Call Trace
                tool_trace = res.get("metadata", {}).get("tool_call_trace", [])
                if tool_trace:
                    st.subheader("🛠️ Relationship Fetching (Phase 1)")
                    
                    # Summary stats
                    success_count = sum(1 for t in tool_trace if t.get("status") == "success")
                    total_entities = sum(t.get("entities_found", 0) for t in tool_trace)
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Relationships with Data", success_count)
                    col2.metric("Total Entities Fetched", total_entities)
                    col3.metric("Relationships Attempted", len(tool_trace))
                    
                    # Detailed trace
                    with st.expander("📋 Detailed Tool Call Log", expanded=False):
                        for call in tool_trace:
                            rel = call.get("relationship", "unknown")
                            status = call.get("status", "unknown")
                            count = call.get("entities_found", 0)
                            
                            if status == "success":
                                st.success(f"**{rel}**: {count} entities")
                                if call.get("sample_entity"):
                                    st.json(call["sample_entity"])
                            elif status == "empty":
                                st.info(f"**{rel}**: No response from GTI")
                            elif status == "no_entities":
                                st.info(f"**{rel}**: Empty results")
                            elif status == "filtered":
                                st.warning(f"**{rel}**: Filtered out ({call.get('before_filter', 0)} → 0)")
                            elif status == "error":
                                st.error(f"**{rel}**: Error - {call.get('error', 'Unknown')}")
                else:
                    st.info("No tool call trace available")
                
                # LLM Reasoning
                llm_reasoning = res.get("metadata", {}).get("rich_intel", {}).get("triage_analysis", {}).get("_llm_reasoning")
                if llm_reasoning:
                    st.subheader("🧠 Triage Agent Reasoning (Phase 2)")
                    st.markdown("The agent's structured analysis based on fetched data:")
                    with st.expander("Show full LLM response", expanded=False):
                        st.code(llm_reasoning, language="json")
                else:
                    st.info("LLM reasoning not available")

        with tab2:
            st.subheader("Investigation Graph")
            
            # Enhanced Graph Interactivity - Sidebar Controls
            with st.sidebar:
                st.markdown("---")
                st.subheader("🎛️ Graph Controls")
                physics_enabled = st.checkbox("Enable Physics", value=True, help="Dynamic node positioning")
                show_labels = st.checkbox("Show Edge Labels", value=True, help="Display relationship types")
                node_size = st.slider("Node Size", 10, 50, 15, help="Adjust node diameter")
                link_distance = st.slider("Link Distance", 50, 1000, 200, help="Space between nodes")
                
                # Recenter Logic
                if "graph_key" not in st.session_state:
                    st.session_state.graph_key = 0
                
                if st.button("🔄 Recenter Graph"):
                    st.session_state.graph_key += 1
                    st.rerun()  # Force full refresh to reset graph
            
            try:
                graph_data = api.get_graph_data(job_id)
                from streamlit_agraph import agraph, Node, Edge, Config
                
                nodes = []
                edges = []
                
                # Build nodes
                for n in graph_data.get("nodes", []):
                    node_id = n.get("id", "unknown")
                    node_label = n.get("label", "Unknown")
                    node_color = n.get("color", "#9E9E9E")
                    node_title = n.get("title", node_label)
                    
                    # Build node properties
                    node_kwargs = {
                        "id": node_id,
                        "label": node_label,
                        "title": node_title
                    }
                    
                    # Logic: Scale sizes based on slider `node_size`
                    # Root is 1.1x, Groups are 0.75x, Normal is 1.0x
                    
                    final_size = node_size # Default (from slider)
                    
                    if node_id == "root":
                        final_size = int(node_size * 1.1)
                        node_kwargs["x"] = 0
                        node_kwargs["y"] = 0
                    elif str(node_id).startswith("group_"):
                        final_size = int(node_size * 0.75)
                    
                    node_kwargs["size"] = final_size
                    node_kwargs["color"] = node_color
                    
                    nodes.append(Node(**node_kwargs))
                
                # Build edges
                for e in graph_data.get("edges", []):
                    edges.append(Edge(
                        source=e.get("source", "unknown"),
                        target=e.get("target", "unknown"),
                        label=e.get("label", "") if show_labels else ""
                    ))
                
                if not nodes:
                    st.warning("No graph nodes generated. Triage might have returned no tasks.")
                else:
                    # Show graph stats
                    col1, col2 = st.columns(2)
                    col1.metric("Nodes", len(nodes))
                    col2.metric("Edges", len(edges))
                    
                    config = Config(
                        width="100%",
                        height=800,
                        directed=True,
                        hierarchical=False,
                        
                        # Node interaction
                        nodeHighlightBehavior=True,
                        highlightColor="#F7A7A6",
                        
                        # Node styling
                        node={
                            'labelProperty': 'label',
                            'renderLabel': True
                        },
                        
                        # Edge styling
                        link={
                            'labelProperty': 'label',
                            'renderLabel': show_labels,
                            'color': '#999'
                        },
                        
                        # Physics (Vis.js style)
                        physics={
                            'solver': 'forceAtlas2Based',
                            'forceAtlas2Based': {
                                'theta': 0.5,
                                'gravitationalConstant': -50,
                                'centralGravity': 0.5,
                                'springConstant': 0.08,
                                'springLength': link_distance, # Slider controls this
                                'damping': 0.4,
                                'avoidOverlap': 0.01
                            },
                            'stabilization': {
                                'enabled': True,
                                'iterations': 100,  # Run physics sim before display
                                'fit': True  # Center viewport on graph
                            },
                            # Inject recenter trigger - changes config hash on button click
                            '_recenter_key': st.session_state.graph_key
                        } if physics_enabled else {'enabled': False, '_recenter_key': st.session_state.graph_key}
                    )
                    
                    # Render graph
                    agraph(nodes=nodes, 
                           edges=edges, 
                           config=config)
                    
                    # Legend
                    st.markdown("---")
                    st.markdown("**Legend:**")
                    leg_col1, leg_col2, leg_col3, leg_col4, leg_col5 = st.columns(5)
                    leg_col1.markdown("🔴 **Root IOC**")
                    leg_col2.markdown("🔵 **Context**") # Was Agent Tasks
                    leg_col3.markdown("🟠 **Infrastructure**")
                    leg_col4.markdown("🟣 **Files** / 🔵 **URLs**")
                    leg_col5.markdown("⚪ **Groups**")

                    # Debug: Graph Data
                    with st.expander("🛠️ Debug: Graph Data (JSON)", expanded=False):
                        st.json(graph_data)
                    
            except requests.exceptions.ConnectionError:
                st.error("🔌 Cannot connect to backend to fetch graph data.")
                st.info("Ensure the backend is running and accessible.")
            except requests.exceptions.Timeout:
                st.error("⏱️ Request timed out while fetching graph data.")
            except KeyError as e:
                st.error(f"📊 Graph data is malformed: Missing key {e}")
                st.info("The backend may not have generated relationship data yet.")
            except Exception as e:
                st.error(f"❌ Unexpected error rendering graph: {type(e).__name__}")
                with st.expander("🔍 See full error details"):
                    st.exception(e)
        
        with tab3:
            st.subheader("Final Intelligence Report")
            report = res.get("final_report", "No report available.")
            
            # Add export option
            col1, col2 = st.columns([5, 1])
            with col2:
                st.download_button(
                    "📥 Download",
                    data=report,
                    file_name=f"harimau_report_{job_id[:8]}.md",
                    mime="text/markdown",
                    use_container_width=True
                )
            
            st.markdown(report)
        
        with tab4:
            st.subheader("Investigation Timeline")
            
            # Timeline visualization
            if subtasks:
                st.write("**Task Execution Sequence:**")
                
                for idx, task in enumerate(subtasks, 1):
                    agent = task.get('agent', 'Unknown Agent')
                    task_desc = task.get('task', 'No description')[:120] + "..."
                    timestamp = task.get('timestamp', 'Unknown time')
                    duration = task.get('duration', 'N/A')
                    
                    # Create timeline entry
                    col_num, col_time, col_agent, col_task = st.columns([1, 2, 2, 6])
                    
                    with col_num:
                        st.markdown(f"**{idx}**")
                    with col_time:
                        st.caption(timestamp if timestamp != 'Unknown time' else f"Step {idx}")
                    with col_agent:
                        st.markdown(f"🤖 `{agent}`")
                    with col_task:
                        st.write(task_desc)
                    
                    if idx < len(subtasks):
                        st.markdown("<div style='border-left: 2px solid #444; height: 10px; margin-left: 20px;'></div>", unsafe_allow_html=True)
            else:
                st.info("No timeline data available for this investigation.")
