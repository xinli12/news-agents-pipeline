# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging
import os

from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from agents.app_utils.telemetry import setup_telemetry
from agents.app_utils.typing import Feedback

std_logger = logging.getLogger(__name__)

setup_telemetry()

# GCP integration is optional: the server must start with only a Gemini API
# key (no Application Default Credentials), e.g. for local runs and Docker.
project_id = None
gcp_logger = None
try:
    import google.auth

    _, project_id = google.auth.default()
except Exception:
    std_logger.info(
        "No Google Cloud credentials detected; running without Cloud Logging/Tracing."
    )

if project_id:
    try:
        from google.cloud import logging as google_cloud_logging

        gcp_logger = google_cloud_logging.Client().logger(__name__)
    except Exception as e:
        std_logger.warning("Cloud Logging unavailable (%s); using standard logging.", e)

allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=bool(project_id),
)
app.title = "hackathon"
app.description = "API for interacting with the Agent hackathon"


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    payload = feedback.model_dump()
    if gcp_logger is not None:
        try:
            gcp_logger.log_struct(payload, severity="INFO")
            return {"status": "success"}
        except Exception as e:
            std_logger.warning(
                "Failed to log to GCP Cloud Logging: %s. Falling back to standard logging.",
                e,
            )
    std_logger.info("Feedback received: %s", payload)
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
