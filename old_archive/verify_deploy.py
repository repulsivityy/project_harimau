import urllib.request
import json
import urllib.error
import sys
import subprocess

def get_service_url():
    try:
        result = subprocess.run(
            ["gcloud", "run", "services", "describe", "harimau-backend", 
             "--platform", "managed", 
             "--region", "asia-southeast1", 
             "--format", "value(status.url)"],
            capture_output=True, text=True, check=True, shell=True
        )
        return result.stdout.strip() + "/investigate"
    except subprocess.CalledProcessError as e:
        print(f"Error fetching service URL: {e}")
        sys.exit(1)

import time

url = get_service_url()
data = json.dumps({"ioc": "google.com"}).encode("utf-8")
headers = {"Content-Type": "application/json"}

print(f"Testing {url}...")
req = urllib.request.Request(url, data=data, headers=headers)

try:
    # 1. Start Investigation
    response = urllib.request.urlopen(req)
    resp_data = json.loads(response.read().decode("utf-8"))
    print(f"Start Response: {json.dumps(resp_data, indent=2)}")
    
    job_id = resp_data.get("job_id")
    if not job_id:
        print("ERROR: No job_id returned")
        sys.exit(1)
        
    # 2. Poll Status
    status_url = url.replace("/investigate", f"/investigations/{job_id}")
    print(f"Polling {status_url}...")
    
    for i in range(30): # 30 attempts * 2s = 60s timeout (investigation usually takes <5s for google.com cached?)
        # Wait
        time.sleep(2)
        
        # Check
        status_req = urllib.request.Request(status_url)
        status_resp = urllib.request.urlopen(status_req)
        status_data = json.loads(status_resp.read().decode("utf-8"))
        
        status = status_data.get("status")
        print(f"[{i+1}/30] Status: {status}")
        
        if status in ["completed", "failed"]:
            print(f"Final Result: {json.dumps(status_data, indent=2)}")
            if status == "completed":
                print("VERIFICATION SUCCESS")
            else:
                print("VERIFICATION FAILED")
            break
    else:
        print("TIMEOUT polling status")

except urllib.error.HTTPError as e:
    print(f"HTTP ERROR {e.code}")
    print(e.read().decode("utf-8"))
except Exception as e:
    print(f"ERROR: {e}")
