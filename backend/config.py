import os

# Operator-level default: override via Cloud Run env var
# gcloud run services update harimau-backend --set-env-vars HUNT_ITERATIONS=5
DEFAULT_HUNT_ITERATIONS = int(os.getenv("HUNT_ITERATIONS", "3"))
