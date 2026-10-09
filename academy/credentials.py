import os
import re

from .exceptions import AwsDetailsNotFound, CredentialsInvalid

_KEY = re.compile(r"(?i:\bAWS_ACCESS_KEY_ID\b|\bAccessKey\b)[ \t]{0,20}[:=]?[ \t]{0,20}([A-Z0-9]{16,})")
_SECRET = re.compile(r"(?i:\bAWS_SECRET_ACCESS_KEY\b|\bSecretKey\b)[ \t]{0,20}[:=]?[ \t]{0,20}([A-Za-z0-9/+=]{30,})")
_TOKEN = re.compile(r"(?i:\bAWS_SESSION_TOKEN\b|\bSessionToken\b)[ \t]{0,20}[:=]?[ \t]{0,20}([A-Za-z0-9/+=_-]{30,})")


def parse_aws_details(text, region="us-east-1"):
    values = {
        "AWS_ACCESS_KEY_ID": _KEY.search(text),
        "AWS_SECRET_ACCESS_KEY": _SECRET.search(text),
        "AWS_SESSION_TOKEN": _TOKEN.search(text),
    }
    if values["AWS_ACCESS_KEY_ID"] is None or values["AWS_SECRET_ACCESS_KEY"] is None:
        raise AwsDetailsNotFound("AWS Details did not contain access key and secret key")
    credentials = {
        name: match.group(1).strip()
        for name, match in values.items()
        if match is not None
    }
    if not credentials["AWS_ACCESS_KEY_ID"].startswith(("ASIA", "AKIA")):
        raise CredentialsInvalid("AWS access key format is not recognized")
    if any(not value for value in credentials.values()):
        raise CredentialsInvalid("AWS credentials contain an empty value")
    credentials["AWS_REGION"] = region
    credentials["AWS_DEFAULT_REGION"] = region
    return credentials


def export_github_env(credentials):
    env_path = os.environ.get("GITHUB_ENV")
    # Mask before writing any secret to the runner environment file.
    if env_path:
        for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
            if name not in credentials:
                continue
            print(f"::add-mask::{credentials[name]}")
        with open(env_path, "a", encoding="utf-8") as env_file:
            for name, value in credentials.items():
                env_file.write(f"{name}={value}\n")
                os.environ[name] = value
    else:
        # Local runs keep credentials only in this process environment so STS
        # can validate them; they are never printed or written to disk.
        os.environ.update(credentials)
