import sys
import os

# Ensure backend module can be found
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    print(f"Current Directory: {current_dir}")
    print("Checking imports...")
    
    import backend.tools.webrisk as webrisk
    print("✅ backend.tools.webrisk imported successfully")
    
    # Check if get_webrisk_api_key is defined
    if hasattr(webrisk, 'get_webrisk_api_key'):
        print("✅ get_webrisk_api_key found")
    else:
        print("❌ get_webrisk_api_key MISSING")

    # Check Triage Agent Integration
    from backend.agents.triage import triage_node
    print("✅ backend.agents.triage imported successfully")
    
    # Check Infrastructure Agent Integration
    from backend.agents.infrastructure import infrastructure_node
    print("✅ backend.agents.infrastructure imported successfully")
    
except Exception as e:
    print(f"❌ Verification Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
