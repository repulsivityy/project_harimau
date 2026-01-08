import requests
import time
import os
from typing import Dict, Any, Optional

class HarimauAPIClient:
    """
    Client for interacting with the Harimau Backend API.
    Handles job submission, polling, and result retrieval.
    """
    def __init__(self, backend_url: str = None):
        self.base_url = backend_url or os.getenv("BACKEND_URL", "http://localhost:8080")
        
    def health_check(self) -> bool:
        """Checks if the backend is reachable."""
        try:
            res = requests.get(f"{self.base_url}/health", timeout=5)
            return res.status_code == 200
        except Exception:
            return False

    def submit_investigation(self, ioc: str, ioc_type: str = None) -> str:
        """
        Submits a new investigation job.
        Returns: job_id
        """
        payload = {"ioc": ioc}
        if ioc_type:
            payload["ioc_type"] = ioc_type
            
        res = requests.post(f"{self.base_url}/api/investigate", json=payload)
        res.raise_for_status()
        return res.json().get("job_id")

    def get_investigation(self, job_id: str) -> Dict[str, Any]:
        """
        Gets the current status and results of an investigation.
        """
        res = requests.get(f"{self.base_url}/api/investigations/{job_id}")
        res.raise_for_status()
        return res.json()

    def get_graph_data(self, job_id: str) -> Dict[str, Any]:
        """
        Fetches the graph structure for visualization.
        """
        res = requests.get(f"{self.base_url}/api/investigations/{job_id}/graph")
        res.raise_for_status()
        return res.json()

    def get_report(self, job_id: str) -> str:
        """
        Fetches the final markdown report.
        """
        res = requests.get(f"{self.base_url}/api/investigations/{job_id}/report")
        res.raise_for_status()
        return res.text
