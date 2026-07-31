import os

# Operator-level default: override via Cloud Run env var
# gcloud run services update harimau-backend --set-env-vars HUNT_ITERATIONS=5
DEFAULT_HUNT_ITERATIONS = int(os.getenv("HUNT_ITERATIONS", "3"))

# Specialist subgraph execution timeout in seconds: override via Cloud Run env var
# gcloud run services update harimau-backend --set-env-vars SPECIALIST_TIMEOUT=300
SPECIALIST_TIMEOUT = float(os.getenv("SPECIALIST_TIMEOUT", "300.0"))
