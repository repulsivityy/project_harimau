"""
SSE Event Manager for Real-Time Investigation Updates.

This module manages Server-Sent Events (SSE) for streaming investigation
progress to the frontend in real-time.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, AsyncGenerator
from backend.utils.logger import get_logger

logger = get_logger("sse-manager")


class SSEEventManager:
    """
    Manages SSE event queues for active investigations.
    
    Uses broadcast pattern: each subscriber gets their own queue,
    and events are broadcast to all subscribers.
    """
    
    def __init__(self):
        self._subscribers: Dict[str, list] = {}  # job_id -> list of subscriber queues
    
    def create_queue(self, job_id: str):
        """Create subscriber list for a new investigation."""
        if job_id not in self._subscribers:
            self._subscribers[job_id] = []
            logger.info("sse_subscriber_list_created", job_id=job_id)
    
    async def emit_event(self, job_id: str, event_type: str, data: Dict[str, Any]):
        """
        Broadcast an event to all subscribers of this job_id.
        
        Args:
            job_id: Investigation job ID
            event_type: Type of event (e.g., 'triage_started', 'progress')
            data: Event payload
        """
        if job_id not in self._subscribers:
            logger.warning("sse_emit_no_subscribers", job_id=job_id, event_type=event_type)
            return
        
        event = {
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        
        # Broadcast to ALL subscribers
        for subscriber_queue in self._subscribers[job_id]:
            await subscriber_queue.put(event)
        
        logger.debug("sse_event_broadcast", job_id=job_id, event_type=event_type, 
                    subscriber_count=len(self._subscribers[job_id]))
    
    async def subscribe(self, job_id: str) -> AsyncGenerator[str, None]:
        """
        Subscribe to SSE event stream for a job.
        
        Yields SSE-formatted event strings.
        """
        if job_id not in self._subscribers:
            self.create_queue(job_id)
        
        # Create a local queue for THIS subscriber
        local_queue = asyncio.Queue()
        self._subscribers[job_id].append(local_queue)
        
        logger.info("sse_client_connected", job_id=job_id, 
                   subscribers=len(self._subscribers[job_id]))
        
        try:
            # Keepalive tracker
            last_event_time = asyncio.get_event_loop().time()
            
            while True:
                try:
                    # Wait for event with timeout
                    event = await asyncio.wait_for(local_queue.get(), timeout=15.0)
                    
                    # Format as SSE event
                    sse_data = f"data: {json.dumps(event)}\n\n"
                    yield sse_data
                    
                    last_event_time = asyncio.get_event_loop().time()
                    
                    # If completion event, exit
                    if event.get("event_type") in ["investigation_completed", "investigation_failed"]:
                        logger.info("sse_stream_completed", job_id=job_id)
                        break
                
                except asyncio.TimeoutError:
                    # Send keepalive if no event in 15 seconds
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_event_time >= 15:
                        yield ": keepalive\n\n"
                        last_event_time = current_time
        
        except asyncio.CancelledError:
            logger.info("sse_client_disconnected", job_id=job_id)
            raise
        
        finally:
            # Cleanup: remove this subscriber from the list
            if job_id in self._subscribers:
                try:
                    self._subscribers[job_id].remove(local_queue)
                    logger.info("sse_client_disconnected", job_id=job_id,
                              remaining_subscribers=len(self._subscribers[job_id]))
                except ValueError:
                    pass  # Already removed
                
                # Remove subscriber list if empty
                if not self._subscribers[job_id]:
                    del self._subscribers[job_id]
                    logger.info("sse_subscriber_list_cleaned", job_id=job_id)


# Global singleton instance
sse_manager = SSEEventManager()
