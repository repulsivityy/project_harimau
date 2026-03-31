import sys
import os
import requests
import json

# Replace this with your actual Cloud Run Harimau Backend URL
HARIMAU_URL = os.environ.get("HARIMAU_URL", "https://your-cloud-run-url.run.app")

def fetch_and_save_reports(job_id: str):
    url = f"{HARIMAU_URL}/api/investigations/{job_id}/history"
    print(f"Fetching history for job: {job_id}\nFrom: {url}")
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 404:
            print(f"Error 404: Could not find job ID '{job_id}' or no history available.")
        else:
            print(f"HTTP Error fetching history: {e}")
        return
    except requests.exceptions.RequestException as e:
        print(f"Connection Error fetching history: {e}")
        return
        
    iterations = data.get("iterations", [])
    if not iterations:
        print("No iterative report data found for this job.")
        return
        
    dump_dir = f"dumps/{job_id}"
    os.makedirs(dump_dir, exist_ok=True)
    print(f"\nFound {len(iterations)} distinct report states. Saving to {dump_dir}/ ...")
    
    for iter_data in iterations:
        iter_num = iter_data.get("iteration")
        malware = iter_data.get("malware_report")
        infra = iter_data.get("infrastructure_report")
        
        if malware:
            p = os.path.join(dump_dir, f"malware_iter_{iter_num}.md")
            with open(p, "w") as f:
                f.write(malware)
            print(f"  Saved: {p}")
            
        if infra:
            p = os.path.join(dump_dir, f"infra_iter_{iter_num}.md")
            with open(p, "w") as f:
                f.write(infra)
            print(f"  Saved: {p}")
            
    print("\n✅ Verification complete! You can open these files to track the LLM's accumulating output.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download_reports.py <job_id>")
        print("Make sure you prefix with HARIMAU_URL if default is incorrect:")
        print("HARIMAU_URL=https://... python download_reports.py <job_id>")
        sys.exit(1)
        
    target_job_id = sys.argv[1]
    fetch_and_save_reports(target_job_id)
