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
# State Management for Persistence
if "current_job_id" not in st.session_state:
    st.session_state.current_job_id = None
if "graph_recenter_key" not in st.session_state:
    st.session_state.graph_recenter_key = 0

# Sidebar Controls (Moved up for better flow)
with st.sidebar:
    st.header("System Status")
    if api.health_check():
        st.success("Backend Online")
    else:
        st.error("Backend Offline")
        st.warning("Ensure backend is running on port 8080")
        
    st.markdown("---")
    st.subheader("🎛️ Graph Controls")
    
    # Recenter Logic
    if "graph_key" not in st.session_state:
        st.session_state.graph_key = 0
    
    if st.button("🔄 Recenter Graph", use_container_width=True):
        st.session_state.graph_key += 1
        st.rerun()  # Force full refresh to reset graph
        
    physics_enabled = st.checkbox("Enable Physics", value=True, help="Dynamic node positioning")
    show_labels = st.checkbox("Show Edge Labels", value=True, help="Display relationship types")
    node_size = st.slider("Node Size", 10, 50, 15, help="Adjust node diameter")
    link_distance = st.slider("Link Distance", 50, 1000, 200, help="Space between nodes")

# Main Interface
st.write("Harimau (Tiger in Malay) is an AI-powered threat hunting platform that uses multiple specialised threat hunt agents to analyze and investigate IOCs (IPs, Domains, Hashes, URLs).")
st.write("Harimau leverages LangGraph with multiple specialised threat hunt agents to mimic the flow of a threat hunting program.")
st.write("Harimau is currently in Beta Phase. Expect some bugs and unexpected behaviour.")
st.write("### Investigation Console")
st.write("\n")

col1, col2 = st.columns([3, 1])
with col1:
    ioc_input = st.text_input("Enter IOC (IP, Domain, Hash, URL)", placeholder="e.g., 1.1.1.1")
with col2:
    st.write("") # Spacer
    st.write("") # Spacer
    submit_btn = st.button("Start Investigation", type="primary", use_container_width=True)

# Logic: New Submission or Persistent State
if submit_btn and ioc_input:
    # New Job
    with st.spinner("The 🐯 Tiger is hunting..."):
        job_id = api.submit_investigation(ioc_input)
        st.session_state.current_job_id = job_id # Persist
        st.toast(f"Job Initiated: {job_id}", icon="🚀")

# Render if we have a job
if st.session_state.current_job_id:
    job_id = st.session_state.current_job_id
    
    try:
        # 2. Poll for Completion (Only if just submitted or running)
        # Check status once first to decide if we need to poll
        current_status = api.get_investigation(job_id).get("status")
        
        if current_status == "running":
            st.write("### 🔍 Investigation Progress")
            progress_bar = st.progress(0)
            status_text = st.empty()
            progress_details = st.empty()
            
            complete = False
            poll_count = 0
            max_polls = 150
            
            while not complete and poll_count < max_polls:
                data = api.get_investigation(job_id)
                status = data.get("status")
                
                # Calculate progress
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
                else:
                    active_agent = data.get("current_agent", "Processing")
                    status_text.info(f"🤖 Status: {status} | Agent: {active_agent}")
                    progress_details.caption(f"Poll #{poll_count + 1} | Elapsed: {poll_count * 2}s")
                    time.sleep(2)
                    poll_count += 1
            
            # Use rerun to clear polling UI and show results clean
            # but st.rerun() might be too aggressive, let's just fall through
        
        # 3. Display Results
        res = api.get_investigation(job_id)
        subtasks = res.get("subtasks", [])
                
        # Tabs for different views
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 Triage & Plan", "🕸️ Graph", "🤖 Specialist Reports", "📄 Final Report", "⏱️ Timeline"])
        
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
            col_b.metric("GTI Verdict", verdict if verdict else "Unknown")
            col_c.metric("GTI Threat Score", f"{t_score}/100" if t_score else "N/A")
            total_stats = rich_intel.get("total_stats", 0)
            col_d.metric("VT Detections", f"{mal_stats}/{total_stats}" if total_stats > 0 else "0/0")
            
            # Row 2: Description
            if desc:
                st.info(f"**Analysis (Automated):** {desc}")
            
            # Analyst Report - Use markdown report if available, fallback to summary
            triage_analysis = res.get("metadata", {}).get("rich_intel", {}).get("triage_analysis", {})
            markdown_report = triage_analysis.get("markdown_report", "")
            
            if markdown_report:
                # Show summary first (if available)
                t_summary = rich_intel.get("triage_summary")
                if t_summary:
                    st.markdown("### 🛡️ Analyst Summary")
                    st.markdown(t_summary)
                
                # Show full report in expander
                with st.expander("📄 View Full Triage Report", expanded=False):
                    st.markdown(markdown_report)
            else:
                # Fallback to old summary format if markdown report not available
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
            
            try:
                graph_data = api.get_graph_data(job_id)
                from streamlit_agraph import agraph, Node, Edge, Config
                
                nodes = []
                edges = []
                
                # Build nodes with scaling logic
                for n in graph_data.get("nodes", []):
                    node_id = n.get("id")
                    node_label = n.get("label")
                    node_color = n.get("color")
                    node_title = n.get("title")
                    
                    # Logic: Scale sizes based on slider `node_size`
                    # Root is 1.1x, Groups are 0.75x, Normal is 1.0x
                    final_size = node_size  # Default (from slider)
                    
                    node_kwargs = {
                        "id": node_id,
                        "label": node_label,
                        "title": node_title
                    }
                    
                    if node_id == "root":
                        final_size = int(node_size * 1.1)
                        node_kwargs["x"] = 0
                        node_kwargs["y"] = 0
                    elif str(node_id).startswith("group_") or str(node_id).startswith("overflow_"):
                        final_size = int(node_size * 0.75)
                    
                    node_kwargs["size"] = final_size
                    node_kwargs["color"] = node_color
                    
                    nodes.append(Node(**node_kwargs))
                
                # Build edges
                for e in graph_data.get("edges", []):
                    edges.append(Edge(
                        source=e.get("source"),
                        target=e.get("target"),
                        label=e.get("label") if show_labels else "",
                        dashes=e.get("dashes", False)
                    ))
                
                if not nodes:
                    st.warning("No graph nodes generated.")
                else:
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
                                'springLength': link_distance,  # Slider controls this
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
                    agraph(nodes=nodes, edges=edges, config=config)
                    
                    st.markdown("**Legend:**")
                    leg_cols = st.columns(6)
                    leg_cols[0].markdown("🔴 **IOC**")
                    leg_cols[1].markdown("🟣 **File**")
                    leg_cols[2].markdown("🟠 **Infra**")
                    leg_cols[3].markdown("🔵 **Context**")
                    leg_cols[4].markdown("⚫ **Group**")
                    leg_cols[5].markdown("🟢 **URL**")
                    
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
            st.subheader("Specialist Agent Reports")
            
            # Get specialist results from the investigation
            specialist_results = res.get("specialist_results", {})
            
            if not specialist_results:
                st.info("No specialist reports available yet. Specialists are invoked based on triage findings.")
            else:
                st.write("Detailed analysis from specialized investigation agents:")
                st.write("")
                
                # Display each specialist's report
                for agent_name, agent_result in specialist_results.items():
                    # Format agent name
                    display_name = agent_name.replace("_", " ").title()
                    
                    # Get the markdown report
                    markdown_report = agent_result.get("markdown_report", "")
                    
                    # Get summary for preview
                    summary = agent_result.get("summary", "No summary available")
                    verdict = agent_result.get("verdict", "N/A")
                    
                    # Agent status indicator
                    if verdict in ["Malicious", "MALICIOUS"]:
                        icon = "🔴"
                    elif verdict in ["Suspicious", "SUSPICIOUS"]:
                        icon = "🟡"
                    elif verdict in ["Benign", "BENIGN"]:
                        icon = "🟢"
                    else:
                        icon = "⚪"
                    
                    # Create collapsible panel for each agent
                    with st.expander(f"{icon} **{display_name}** - {verdict}", expanded=False):
                        if markdown_report:
                            st.markdown(markdown_report)
                        else:
                            st.warning("No detailed report available from this specialist.")
                            st.json(agent_result)  # Fallback to raw JSON
        
        with tab4:
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
            
            # st.markdown(report) -> Replaced with Graphviz-aware rendering
            
            # Split content by graphviz blocks
            # Pattern: ```dot ... ``` or ```graphviz ... ```
            import re
            
            # Regex to find graphviz/dot blocks
            parts = re.split(r'```(?:dot|graphviz)\s+(.*?)\s+```', report, flags=re.DOTALL)
            
            for i, part in enumerate(parts):
                # Even indices are normal markdown (0, 2, 4...)
                # Odd indices are graphviz code (1, 3, 5...)
                if i % 2 == 0:
                    if part.strip():
                        st.markdown(part)
                else:
                    # Render graphviz diagram using native Streamlit
                    clean_code = part.strip()
                    
                    # Debug: Show the graphviz code in an expander
                    with st.expander("🐛 Debug: View Graphviz Code", expanded=False):
                        st.code(clean_code, language="dot")
                    
                    # Render using native Streamlit Graphviz
                    st.graphviz_chart(clean_code, use_container_width=True)
        
        with tab5:
            st.subheader("Investigation Timeline")
            
            # Timeline visualization
            if subtasks:
                st.write("**Task Execution Sequence:**")
                
                for idx, task in enumerate(subtasks, 1):
                    agent = task.get('agent', 'Unknown Agent')
                    task_desc = task.get('task', 'No description')[:80] + "..."
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

    except requests.exceptions.ConnectionError:
        st.error("🔌 Cannot connect to backend server")
        st.warning("**Solution:** Ensure backend is running on port 8080")
        st.code("cd backend && python main.py", language="bash")
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