import os

from .exceptions import ConfigurationError


def load_config():
    required = ("CANVAS_USERNAME", "CANVAS_PASSWORD", "CANVAS_LOGIN_URL")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ConfigurationError("Missing required configuration: " + ", ".join(missing))
    return {
        "username": os.environ["CANVAS_USERNAME"],
        "password": os.environ["CANVAS_PASSWORD"],
        "login_url": os.environ["CANVAS_LOGIN_URL"],
        "region": os.environ.get("AWS_REGION", "us-east-1"),
        "course_name": os.environ.get("CANVAS_COURSE_NAME", "AWS Academy Learner Lab"),
        "lab_link_text": os.environ.get("CANVAS_LAB_LINK_TEXT", "Sandbox Environment"),
        "timeout_ms": int(os.environ.get("ACADEMY_TIMEOUT_MS", "30000")),
        "lab_timeout_seconds": int(os.environ.get("LAB_TIMEOUT_SECONDS", "300")),
        "headless": os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() != "false",
    }
