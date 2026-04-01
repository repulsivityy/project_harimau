import streamlit as st
import re
from datetime import datetime
from api_client import HarimauAPIClient

def render_tabs(api: HarimauAPIClient, job_id: str, res: dict, graph_settings: dict):
    """Renders the 6 investigation tabs."""
    subtasks = res.get("subtasks", [])
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📝 Triage & Plan", "🕸️ Graph", "🤖 Specialist Reports", 
        "📄 Final Report", "⏱️ Timeline", "🧠 Agent Thinking & Tools"
    ])
    
    with tab1:
        _render_triage_tab(res, subtasks)
        
    with tab2:
        _render_graph_tab(api, job_id, graph_settings)
            
    with tab3:
        _render_specialist_tab(res)
        
    with tab4:
        _render_report_tab(res, job_id)
        
    with tab5:
        _render_timeline_tab(subtasks)
        
    with tab6:
        _render_transparency_tab(res)


def _render_triage_tab(res: dict, subtasks: list):
    st.subheader("Triage Assessment")
    
    rich_intel = res.get("rich_intel", {})
    t_score = rich_intel.get("threat_score")
    verdict = rich_intel.get("verdict")
    mal_stats = rich_intel.get("malicious_stats")
    desc = rich_intel.get("description")
    
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("IOC Type", (res.get("ioc_type") or "Unknown").upper())
    col_b.metric("GTI Verdict", verdict if verdict else "Unknown")
    col_c.metric("GTI Threat Score", f"{t_score}/100" if t_score else "N/A")
    total_stats = rich_intel.get("total_stats", 0)
    col_d.metric("VT Detections", f"{mal_stats}/{total_stats}" if total_stats > 0 else "0/0")
    
    if desc:
        st.info(f"**Analysis (Automated):** {desc}")
    
    triage_analysis = res.get("metadata", {}).get("rich_intel", {}).get("triage_analysis", {})
    markdown_report = triage_analysis.get("markdown_report", "")
    
    if markdown_report:
        t_summary = rich_intel.get("triage_summary")
        if t_summary:
            st.markdown("### 🛡️ Analyst Summary")
            st.markdown(t_summary)
        with st.expander("📄 View Full Triage Report", expanded=False):
            st.markdown(markdown_report)
    else:
        t_summary = rich_intel.get("triage_summary")
        if t_summary:
            st.markdown("### 🛡️ Analyst Summary")
            st.markdown(t_summary)
    
    st.divider()
    
    with st.expander(f"#### 🤖 Generated Agent Tasks ({len(subtasks)})", expanded=True):
        for idx, task in enumerate(subtasks):
            agent_name = task.get('agent', 'Agent')
            task_desc = task.get('task', 'No description')
            status = task.get('status', 'pending')
            
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
            
    st.markdown("---")
    with st.expander("🔍 Agent Transparency", expanded=False):
        st.caption("See what the Triage Agent is thinking and doing under the hood")
        
        tool_trace = res.get("metadata", {}).get("tool_call_trace", [])
        if tool_trace:
            st.subheader("🛠️ Relationship Fetching (Phase 1)")
            success_count = sum(1 for t in tool_trace if t.get("status") == "success")
            total_entities = sum(t.get("entities_found", 0) for t in tool_trace)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Relationships with Data", success_count)
            col2.metric("Total Entities Fetched", total_entities)
            col3.metric("Relationships Attempted", len(tool_trace))
            
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
        
        llm_reasoning = res.get("metadata", {}).get("rich_intel", {}).get("triage_analysis", {}).get("_llm_reasoning")
        if llm_reasoning:
            st.subheader("🧠 Triage Agent Reasoning (Phase 2)")
            st.markdown("The agent's structured analysis based on fetched data:")
            with st.expander("Show full LLM response", expanded=False):
                st.code(llm_reasoning, language="json")
        else:
            st.info("LLM reasoning not available")

def _render_graph_tab(api: HarimauAPIClient, job_id: str, graph_settings: dict):
    st.subheader("Investigation Graph")
    try:
        import requests
        graph_data = api.get_graph_data(job_id)
        from streamlit_agraph import agraph, Node, Edge, Config
        
        nodes = []
        edges = []
        
        # Build nodes
        for n in graph_data.get("nodes", []):
            node_kwargs = {
                "id": n.get("id"),
                "label": n.get("label"),
                "title": n.get("title")
            }
            
            final_size = graph_settings["node_size"]
            if n.get("id") == "root":
                final_size = int(graph_settings["node_size"] * 1.1)
                node_kwargs["x"] = 0
                node_kwargs["y"] = 0
            elif str(n.get("id")).startswith("group_") or str(n.get("id")).startswith("overflow_"):
                final_size = int(graph_settings["node_size"] * 0.75)
            
            node_kwargs["size"] = final_size
            node_kwargs["color"] = n.get("color")
            nodes.append(Node(**node_kwargs))
        
        # Build edges
        for e in graph_data.get("edges", []):
            edges.append(Edge(
                source=e.get("source"),
                target=e.get("target"),
                label=e.get("label") if graph_settings["show_labels"] else "",
                dashes=e.get("dashes", False)
            ))
        
        if not nodes:
            st.warning("No graph nodes generated.")
        else:
            col1, col2 = st.columns(2)
            col1.metric("Nodes", len(nodes))
            col2.metric("Edges", len(edges))
            
            physics_config = {
                'solver': 'forceAtlas2Based',
                'forceAtlas2Based': {
                    'theta': 0.5,
                    'gravitationalConstant': -50,
                    'centralGravity': 0.5,
                    'springConstant': 0.08,
                    'springLength': graph_settings["link_distance"],
                    'damping': 0.4,
                    'avoidOverlap': 0.01
                },
                'stabilization': {
                    'enabled': True,
                    'iterations': 100,
                    'fit': True
                },
                '_recenter_key': st.session_state.graph_key
            } if graph_settings["physics_enabled"] else {'enabled': False, '_recenter_key': st.session_state.graph_key}

            config = Config(
                width="100%",
                height=800,
                directed=True,
                hierarchical=False,
                nodeHighlightBehavior=True,
                highlightColor="#F7A7A6",
                node={'labelProperty': 'label', 'renderLabel': True},
                link={'labelProperty': 'label', 'renderLabel': graph_settings["show_labels"], 'color': '#999'},
                physics=physics_config
            )
            
            agraph(nodes=nodes, edges=edges, config=config)
            
            st.markdown("**Legend:**")
            leg_cols = st.columns(6)
            leg_cols[0].markdown("🔴 **IOC**")
            leg_cols[1].markdown("🟣 **File**")
            leg_cols[2].markdown("🟠 **Infra**")
            leg_cols[3].markdown("🔵 **Context**")
            leg_cols[4].markdown("⚫ **Group**")
            leg_cols[5].markdown("🟢 **URL**")
            
    except Exception as e:
        st.error(f"❌ Error rendering graph: {type(e).__name__}")
        with st.expander("🔍 See full error details"):
            st.exception(e)

def _render_specialist_tab(res: dict):
    st.subheader("Specialist Agent Reports")
    specialist_results = res.get("specialist_results", {})
    
    if not specialist_results:
        st.info("No specialist reports available yet. Specialists are invoked based on triage findings.")
    else:
        st.write("Detailed analysis from specialized investigation agents:\n")
        
        for agent_name, agent_result in specialist_results.items():
            display_name = agent_name.replace("_", " ").title()
            markdown_report = agent_result.get("markdown_report", "")
            verdict = agent_result.get("verdict", "N/A")
            
            icon = "⚪"
            if verdict.upper() == "MALICIOUS": icon = "🔴"
            elif verdict.upper() == "SUSPICIOUS": icon = "🟡"
            elif verdict.upper() == "BENIGN": icon = "🟢"
            
            with st.expander(f"{icon} **{display_name}** - {verdict}", expanded=False):
                if markdown_report:
                    st.markdown(markdown_report)
                else:
                    st.warning("No detailed report available from this specialist.")
                    st.json(agent_result)

def _render_report_tab(res: dict, job_id: str):
    st.subheader("Final Intelligence Report")
    report = res.get("final_report", "No report available.")
    
    col1, col2 = st.columns([5, 1])
    with col2:
        st.download_button(
            "📥 Download",
            data=report,
            file_name=f"harimau_report_{job_id[:8]}.md",
            mime="text/markdown",
            use_container_width=True
        )
    
    parts = re.split(r'```(?:dot|graphviz)\s+(.*?)\s+```', report, flags=re.DOTALL)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            if part.strip():
                st.markdown(part)
        else:
            clean_code = part.strip()
            st.graphviz_chart(clean_code, use_container_width=True)

def _render_timeline_tab(subtasks: list):
    st.subheader("Investigation Timeline")
    if subtasks:
        st.write("**Task Execution Sequence:**")
        for idx, task in enumerate(subtasks, 1):
            agent = task.get('agent', 'Unknown Agent')
            task_desc = task.get('task', 'No description')[:80] + "..."
            timestamp = task.get('timestamp', 'Unknown time')
            duration = task.get('duration', 'N/A')
            
            col_num, col_time, col_agent, col_task = st.columns([1, 2, 2, 6])
            
            time_str = "Unknown time"
            if timestamp != 'Unknown time':
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%H:%M:%S")
                except ValueError:
                    time_str = timestamp

            with col_num: st.markdown(f"**{idx}**")
            with col_time:
                st.caption(f"{time_str}")
                if duration != "N/A":
                    st.caption(f"⏱️ {duration}")
            with col_agent: st.markdown(f"🤖 `{agent}`")
            with col_task: st.write(task_desc)
            
            if idx < len(subtasks):
                st.markdown("<div style='border-left: 2px solid #444; height: 10px; margin-left: 20px;'></div>", unsafe_allow_html=True)
    else:
        st.info("No timeline data available for this investigation.")

def _render_transparency_tab(res: dict):
    st.subheader("Agent Transparency Log")
    st.caption("Full record of agent reasoning and tool invocations during the investigation")
    transparency_log = res.get("transparency_log", [])
    
    if transparency_log:
        st.info(f"📊 **{len(transparency_log)} transparency events recorded**")
        for idx, event in enumerate(transparency_log, 1):
            event_type = event.get("type")
            agent = event.get("agent", "unknown")
            timestamp = event.get("timestamp", "")
            
            time_str = ""
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%H:%M:%S.%f")[:-3]
                except ValueError:
                    time_str = timestamp
            
            if event_type == "tool":
                tool = event.get("tool", "unknown")
                args = event.get("args", {})
                with st.expander(f"🔧 **{idx}.** `{agent}` → `{tool}` ({time_str})", expanded=False):
                    st.json(args)
            elif event_type == "reasoning":
                thought = event.get("thought", "")
                with st.expander(f"💭 **{idx}.** `{agent}` LLM Reasoning ({len(thought)} chars) - {time_str}", expanded=False):
                    st.markdown(f"```\n{thought}\n```")
    else:
        st.info("No transparency log available for this investigation.")
