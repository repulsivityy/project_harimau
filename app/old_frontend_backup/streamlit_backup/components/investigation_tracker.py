import streamlit as st
import time
from api_client import HarimauAPIClient

def render_investigation_tracker(api: HarimauAPIClient, job_id: str):
    """Handles the SSE streaming and fallback polling for an active investigation job."""
    
    st.write("### 🔍 Investigation Progress")
    progress_bar = st.progress(0)
    status_text = st.empty()
    progress_details = st.empty()
    
    # Agent Activity Log (Transparency Feature)
    activity_expander = st.expander("🔍 Agent Activity Log", expanded=False)
    activity_log_container = activity_expander.empty()
    
    # Initialize session state for activity log
    if "activity_log" not in st.session_state:
        st.session_state.activity_log = []
    
    # Try SSE first, fallback to polling if unavailable
    use_sse = True
    complete = False
    poll_count = 0
    max_polls = 150
    
    if use_sse:
        status_text.info("🔄 Connecting to real-time event stream...")
        
        try:
            for event in api.stream_investigation_events(job_id):
                if event is None:
                    # SSE failed, fall back to polling
                    status_text.warning("⚠️ Real-time streaming unavailable. Falling back to polling...")
                    use_sse = False
                    break
                
                event_type = event.get("event_type", "")
                data = event.get("data", {})
                progress = data.get("progress", 0)
                message = data.get("message", "Processing...")
                agent = data.get("agent", "")
                
                # Update progress bar
                progress_bar.progress(min(progress, 100))
                
                # Update status based on event type
                if "completed" in event_type or "failed" in event_type:
                    if "investigation_completed" == event_type:
                        progress_bar.progress(100)
                        status_text.success(f"✅ {message}")
                        complete = True
                        break
                    elif "investigation_failed" == event_type:
                        progress_bar.empty()
                        status_text.error(f"❌ {message}")
                        error_msg = data.get("error", "Unknown error")
                        st.error(f"Investigation failed: {error_msg}")
                        st.stop()
                    else:
                        # Agent completed
                        status_text.info(f"✅ {agent.replace('_', ' ').title()}: {message}")
                elif "started" in event_type:
                    # Agent started
                    status_text.info(f"🤖 {message}")
                elif event_type == "tool_invocation":
                    # Tool call transparency
                    tool = data.get("tool", "unknown")
                    agent_name = data.get("agent", "unknown")
                    log_entry = f"🔧 **{agent_name}**: Calling `{tool}`"
                    st.session_state.activity_log.append(log_entry)
                    # Update activity log display
                    with activity_log_container:
                        for entry in st.session_state.activity_log[-20:]:  # Show last 20 entries
                            st.caption(entry)
                elif event_type == "agent_reasoning":
                    # LLM reasoning transparency
                    agent_name = data.get("agent", "unknown")
                    thought = data.get("thought", "")
                    st.session_state.activity_log.append({"type": "reasoning", "agent": agent_name, "thought": thought})
                    # Update activity log display
                    with activity_log_container:
                        for entry in st.session_state.activity_log[-20:]:
                            if isinstance(entry, dict) and entry.get("type") == "reasoning":
                                st.caption(f"💭 **{entry['agent']}**: [Reasoning available - {len(entry['thought'])} chars]")
                            else:
                                st.caption(entry)
                else:
                    # Generic status update
                    status_text.info(f"🔄 {message}")
                
                progress_details.caption(f"Event: {event_type} | Progress: {progress}%")
                
                # Streamlit needs rerun to update UI
                time.sleep(0.1)  # Small delay to avoid excessive reruns
                
        except Exception as e:
            st.warning(f"SSE stream error: {str(e)}. Falling back to polling...")
            use_sse = False
    
    # Fallback to polling if SSE failed
    if not use_sse and not complete:
        status_text.info("🔄 Using polling for updates (every 10 seconds)...")
        
        while not complete and poll_count < max_polls:
            data = api.get_investigation(job_id)
            status = data.get("status")
            
            # Calculate progress based on elapsed time (assume ~8.5 min avg)
            elapsed_seconds = poll_count * 10  # Polls every 10 seconds
            estimated_duration = 510  # 8.5 minutes in seconds
            progress = min(int((elapsed_seconds / estimated_duration) * 100), 95) if status == "running" else 100
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
                progress_details.caption(f"Poll #{poll_count + 1} | Elapsed: {poll_count * 10}s")
                time.sleep(10)
                poll_count += 1
