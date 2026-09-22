export async function register() {
  // Skip during `next build` (Cloud Build image creation) where runtime secrets are not mounted yet.
  if (process.env.NEXT_PHASE === "phase-production-build") {
    return;
  }

  if (process.env.NEXT_RUNTIME === "nodejs") {
    const apiKey = (process.env.HARIMAU_API_KEY || "").trim();
    if (!apiKey) {
      console.error(
        "[FATAL] HARIMAU_API_KEY environment variable is missing or empty. Terminating frontend instance (fail-closed)."
      );
      process.exit(1);
    }
  }
}
