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
            
        # 2. Poll for Completion with Progress Bar
        st.write("### 🔍 Investigation Progress")
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
            else:
                # Show active agents if available
                active_agent = data.get("current_agent", "Processing")
                status_text.info(f"🤖 Status: {status} | Agent: {active_agent}")
                progress_details.caption(f"Poll #{poll_count + 1} | Elapsed: {poll_count * 2}s")
                time.sleep(2)
                poll_count += 1
                
        # 3. Display Results
        res = api.get_investigation(job_id)
        subtasks = res.get("subtasks", [])
        
        st.success("Investigation Complete!")
        
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

        with tab2:
            st.subheader("Investigation Graph")
            
            # Enhanced Graph Interactivity - Sidebar Controls
            with st.sidebar:
                st.markdown("---")
                st.subheader("🎛️ Graph Controls")
                physics_enabled = st.checkbox("Enable Physics", value=True, help="Dynamic node positioning")
                show_labels = st.checkbox("Show Edge Labels", value=True, help="Display relationship types")
                node_size = st.slider("Node Size", 15, 50, 25, help="Adjust node diameter")
                link_distance = st.slider("Link Distance", 50, 200, 100, help="Space between nodes")
            
            try:
                graph_data = api.get_graph_data(job_id)
                from streamlit_agraph import agraph, Node, Edge, Config
                
                # Node Coloring by Type
                color_map = {
                    "root": "#FF4B4B",           # Red for root IOC
                    "agent": "#4B9FFF",          # Blue for agent tasks
                    "malware": "#FF6B6B",        # Light red for malware entities
                    "infrastructure": "#FFB74D", # Orange for infrastructure
                    "indicator": "#AB47BC",      # Purple for indicators
                    "relationship": "#26C6DA",   # Cyan for relationships
                    "default": "#9E9E9E"         # Gray for others
                }
                
                nodes = []
                edges = []
                
                # Build nodes with type-based coloring
                for n in graph_data.get("nodes", []):
                    node_type = n.get("type", "default")
                    node_color = color_map.get(node_type, color_map["default"])
                    
                    # Override with custom color if provided
                    if "color" in n:
                        node_color = n["color"]
                    
                    # Specialized Node Logic
                    node_kwargs = {
                        "id": n["id"],
                        "label": n["label"],
                        "size": n.get("size", node_size),
                        "color": node_color,
                        "title": n.get("title", f"{node_type.title()}: {n['label']}")
                    }
                    
                    # PIN THE ROOT NODE to Center
                    if n["id"] == "root":
                        node_kwargs["x"] = 0
                        node_kwargs["y"] = 0
                        node_kwargs["fixed"] = True
                        # Make it slightly larger too
                        node_kwargs["size"] = 40
                    
                    nodes.append(Node(**node_kwargs))
                
                # Build edges
                for e in graph_data.get("edges", []):
                    edges.append(Edge(
                        source=e["source"], 
                        target=e["target"], 
                        label=e.get("label", "") if show_labels else ""  # Conditional labels
                    ))
                
                if not nodes:
                    st.warning("No graph nodes generated. Triage might have returned no tasks.")
                else:
                    # Show graph stats
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Nodes", len(nodes))
                    col2.metric("Edges", len(edges))
                    col3.metric("Relationships", len(nodes) - 1 - len(res.get("subtasks", [])))
                    
                    # ✅ ENHANCED CONFIG with User Controls
                    config = Config(
                        width="100%",           # Use full container width
                        height=600,             # Fixed height for consistency
                        directed=True,          # Show arrow direction
                        physics=physics_enabled,  # User-controlled physics
                        hierarchical=False,     # Disable hierarchical (too rigid)
                        fit=True,               # Force fit to screen center
                        
                        # Node interaction
                        nodeHighlightBehavior=True,
                        highlightColor="#F7A7A6",
                        
                        # Layout physics (makes graph more readable)
                        node={
                            'labelProperty': 'label',
                            'renderLabel': True
                        },
                        
                        # Edge styling
                        link={
                            'labelProperty': 'label',
                            'renderLabel': show_labels,  # User-controlled labels
                            'color': '#999'
                        },
                        
                        # Initial zoom/fit with user controls
                        d3={
                            'alphaTarget': 0,
                            'gravity': -100,      # Spread nodes apart
                            'linkLength': link_distance,  # User-controlled distance
                            'linkStrength': 1
                        }
                    )
                    
                    # Render graph
                    agraph(nodes=nodes, edges=edges, config=config)
                    
                    # ✅ ENHANCED LEGEND with Color Coding
                    st.markdown("---")
                    st.markdown("**Legend:**")
                    leg_col1, leg_col2, leg_col3, leg_col4, leg_col5 = st.columns(5)
                    leg_col1.markdown("🔴 **Root IOC**")
                    leg_col2.markdown("🔵 **Agent Tasks**")
                    leg_col3.markdown("🟠 **Infrastructure**")
                    leg_col4.markdown("🟣 **Indicators**")
                    leg_col5.markdown("💡 *Hover for details*")
                    
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