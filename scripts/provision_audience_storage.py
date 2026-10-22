#!/usr/bin/env python3
"""Idempotently provision Audience Engine S3 storage with AWS CLI APIs."""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


class AwsCliError(RuntimeError):
    def __init__(self, command: list[str], stderr: str) -> None:
        match = re.search(r"\(([^)]+)\) when calling", stderr)
        self.code = match.group(1) if match else "Unknown"
        super().__init__(f"aws {' '.join(command)} failed ({self.code}): {stderr.strip()}")


def normalize_prefix(value: str) -> str:
    if "*" in value or "?" in value:
        raise ValueError("S3_PREFIX must not contain '*' or '?' because IAM treats them as wildcards")
    return value.strip("/")


def bucket_names(account_id: str) -> tuple[str, str]:
    bucket = f"ouros-audience-engine-{account_id}"
    suffix = hashlib.sha256(bucket.encode()).hexdigest()[:6]
    access_logs = f"{bucket[:50]}-logs-{suffix}"
    return bucket, access_logs


def runtime_policy(bucket_arn: str, prefix: str) -> dict[str, Any]:
    key_prefix = f"{prefix}/audiences/" if prefix else "audiences/"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "CheckBucketHealth",
                "Effect": "Allow",
                "Action": ["s3:ListBucket"],
                "Resource": bucket_arn,
            },
            {
                "Sid": "ReadWriteAudienceObjects",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject"],
                "Resource": f"{bucket_arn}/{key_prefix}*",
            },
        ],
    }


class S3Provisioner:
    def __init__(self, region: str, account_id: str, partition: str) -> None:
        self.region = region
        self.account_id = account_id
        self.partition = partition
        self.bucket, self.access_logs_bucket = bucket_names(account_id)
        self.bucket_arn = f"arn:{partition}:s3:::{self.bucket}"
        self.logs_arn = f"arn:{partition}:s3:::{self.access_logs_bucket}"

    def _run(self, *args: str) -> str:
        command = ["s3api", *args, "--region", self.region]
        result = subprocess.run(
            ["aws", *command], capture_output=True, check=False, text=True
        )
        if result.returncode:
            raise AwsCliError(command, result.stderr)
        return result.stdout

    def _json(self, *args: str) -> dict[str, Any]:
        output = self._run(*args)
        return json.loads(output) if output.strip() else {}

    def _optional_json(self, missing_codes: set[str], *args: str) -> dict[str, Any] | None:
        try:
            return self._json(*args)
        except AwsCliError as exc:
            if exc.code in missing_codes:
                return None
            raise

    def bucket_exists(self, name: str) -> bool:
        try:
            self._run(
                "head-bucket",
                "--bucket",
                name,
                "--expected-bucket-owner",
                self.account_id,
            )
            return True
        except AwsCliError as exc:
            if exc.code in {"404", "NotFound", "NoSuchBucket"}:
                return False
            raise

    def ensure_bucket(self, name: str) -> None:
        if self.bucket_exists(name):
            print(f"[s3] Bucket already exists: {name}")
            return

        command = ["create-bucket", "--bucket", name]
        if self.region != "us-east-1":
            command.extend(
                [
                    "--create-bucket-configuration",
                    f"LocationConstraint={self.region}",
                ]
            )
        try:
            self._run(*command)
            print(f"[s3] Created bucket: {name}")
        except AwsCliError as exc:
            if exc.code != "BucketAlreadyOwnedByYou":
                raise
            print(f"[s3] Bucket already exists in this account: {name}")

    def ensure_tags(self, name: str, extra: dict[str, str]) -> None:
        current = self._optional_json(
            {"NoSuchTagSet"},
            "get-bucket-tagging",
            "--bucket",
            name,
            "--expected-bucket-owner",
            self.account_id,
        )
        tags = {
            item["Key"]: item["Value"]
            for item in (current or {}).get("TagSet", [])
        }
        tags.update(
            {
                "managed_by": "github-actions",
                "project": "ouros-aws",
                "service": "audience-engine",
                **extra,
            }
        )
        tagging = {"TagSet": [{"Key": key, "Value": value} for key, value in sorted(tags.items())]}
        self._run(
            "put-bucket-tagging",
            "--bucket",
            name,
            "--expected-bucket-owner",
            self.account_id,
            "--tagging",
            json.dumps(tagging),
        )

    def ensure_public_access_block(self, name: str) -> None:
        self._run(
            "put-public-access-block",
            "--bucket",
            name,
            "--expected-bucket-owner",
            self.account_id,
            "--public-access-block-configuration",
            "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true",
        )

    def ensure_encryption(self, name: str) -> None:
        current = self._optional_json(
            {"ServerSideEncryptionConfigurationNotFoundError"},
            "get-bucket-encryption",
            "--bucket",
            name,
            "--expected-bucket-owner",
            self.account_id,
        )
        rules = (current or {}).get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
        if current is not None and not (
            len(rules) == 1
            and rules[0].get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm") == "AES256"
        ):
            raise RuntimeError(f"Bucket {name} has encryption settings this workflow will not replace")
        if current is None:
            self._run(
                "put-bucket-encryption",
                "--bucket",
                name,
                "--expected-bucket-owner",
                self.account_id,
                "--server-side-encryption-configuration",
                json.dumps(
                    {
                        "Rules": [
                            {
                                "ApplyServerSideEncryptionByDefault": {
                                    "SSEAlgorithm": "AES256"
                                }
                            }
                        ]
                    }
                ),
            )

    def _ensure_policy(self, name: str, desired: dict[str, Any]) -> None:
        current = self._optional_json(
            {"NoSuchBucketPolicy"},
            "get-bucket-policy",
            "--bucket",
            name,
            "--expected-bucket-owner",
            self.account_id,
        )
        if current is not None:
            current_policy = json.loads(current["Policy"])
            if current_policy != desired:
                raise RuntimeError(f"Bucket {name} has a custom policy this workflow will not replace")
            return
        self._run(
            "put-bucket-policy",
            "--bucket",
            name,
            "--expected-bucket-owner",
            self.account_id,
            "--policy",
            json.dumps(desired),
        )

    def ensure_policies(self) -> None:
        self._ensure_policy(self.access_logs_bucket, self.access_logs_policy())
        self._ensure_policy(self.bucket, self.audience_policy())

    def ensure_lifecycle(self) -> None:
        desired = [
            {
                "ID": "expire-access-logs",
                "Filter": {"Prefix": f"{self.bucket}/"},
                "Status": "Enabled",
                "Expiration": {"Days": 30},
            }
        ]
        current = self._optional_json(
            {"NoSuchLifecycleConfiguration"},
            "get-bucket-lifecycle-configuration",
            "--bucket",
            self.access_logs_bucket,
            "--expected-bucket-owner",
            self.account_id,
        )
        if current is not None and current.get("Rules") != desired:
            raise RuntimeError(
                f"Bucket {self.access_logs_bucket} has a custom lifecycle configuration this workflow will not replace"
            )
        if current is None:
            self._run(
                "put-bucket-lifecycle-configuration",
                "--bucket",
                self.access_logs_bucket,
                "--expected-bucket-owner",
                self.account_id,
                "--lifecycle-configuration",
                json.dumps({"Rules": desired}),
            )

    def ensure_logging(self) -> None:
        current = self._json(
            "get-bucket-logging",
            "--bucket",
            self.bucket,
            "--expected-bucket-owner",
            self.account_id,
        ).get("LoggingEnabled")
        if current is not None:
            if (
                current.get("TargetBucket") != self.access_logs_bucket
                or current.get("TargetPrefix") != f"{self.bucket}/"
            ):
                raise RuntimeError(
                    f"Bucket {self.bucket} has a different access-log destination or prefix"
                )
            return
        self._run(
            "put-bucket-logging",
            "--bucket",
            self.bucket,
            "--expected-bucket-owner",
            self.account_id,
            "--bucket-logging-status",
            json.dumps(
                {
                    "LoggingEnabled": {
                        "TargetBucket": self.access_logs_bucket,
                        "TargetPrefix": f"{self.bucket}/",
                    }
                }
            ),
        )

    def verify(self, prefix: str) -> dict[str, Any]:
        public_block = self._json(
            "get-public-access-block",
            "--bucket",
            self.bucket,
            "--expected-bucket-owner",
            self.account_id,
        )["PublicAccessBlockConfiguration"]
        required_block = {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        }
        if any(public_block.get(key) is not True for key in required_block):
            raise RuntimeError(f"Bucket {self.bucket} failed the public-access-block check")
        self.verify_public_access_block(self.access_logs_bucket)
        self.ensure_encryption(self.bucket)
        self.ensure_encryption(self.access_logs_bucket)
        self._ensure_policy(self.bucket, self.audience_policy())
        self._ensure_policy(self.access_logs_bucket, self.access_logs_policy())
        self.ensure_lifecycle()
        self.ensure_logging()
        return runtime_policy(self.bucket_arn, prefix)

    def verify_public_access_block(self, name: str) -> None:
        config = self._json(
            "get-public-access-block",
            "--bucket",
            name,
            "--expected-bucket-owner",
            self.account_id,
        )["PublicAccessBlockConfiguration"]
        if any(
            config.get(key) is not True
            for key in (
                "BlockPublicAcls",
                "IgnorePublicAcls",
                "BlockPublicPolicy",
                "RestrictPublicBuckets",
            )
        ):
            raise RuntimeError(f"Bucket {name} failed the public-access-block check")

    def audience_policy(self) -> dict[str, Any]:
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "DenyInsecureTransport",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [self.bucket_arn, f"{self.bucket_arn}/*"],
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                }
            ],
        }

    def access_logs_policy(self) -> dict[str, Any]:
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowS3ServerAccessLogs",
                    "Effect": "Allow",
                    "Principal": {"Service": "logging.s3.amazonaws.com"},
                    "Action": "s3:PutObject",
                    "Resource": f"{self.logs_arn}/{self.bucket}/*",
                    "Condition": {
                        "ArnLike": {"aws:SourceArn": self.bucket_arn},
                        "StringEquals": {"aws:SourceAccount": self.account_id},
                    },
                },
                {
                    "Sid": "DenyInsecureTransport",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [self.logs_arn, f"{self.logs_arn}/*"],
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                },
            ],
        }

    def provision(self, prefix: str) -> dict[str, Any]:
        main_exists = self.bucket_exists(self.bucket)
        logs_exists = self.bucket_exists(self.access_logs_bucket)
        if logs_exists and not main_exists:
            raise RuntimeError(
                f"Access-log bucket {self.access_logs_bucket} exists without {self.bucket}; refusing to adopt it"
            )
        self.ensure_bucket(self.bucket)
        self.ensure_bucket(self.access_logs_bucket)
        self.ensure_tags(self.bucket, {})
        self.ensure_tags(self.access_logs_bucket, {"purpose": "access-logs"})
        self.ensure_public_access_block(self.bucket)
        self.ensure_public_access_block(self.access_logs_bucket)
        self.ensure_encryption(self.bucket)
        self.ensure_encryption(self.access_logs_bucket)
        self.ensure_policies()
        self.ensure_lifecycle()
        self.ensure_logging()
        return self.verify(prefix)


def append_summary(provisioner: S3Provisioner, prefix: str, policy: dict[str, Any]) -> None:
    lines = [
        "### Audience Engine S3 storage",
        f"- Access logs bucket: `{provisioner.access_logs_bucket}` (30-day retention)",
        f"- Bucket: `{provisioner.bucket}`",
        f"- Region: `{provisioner.region}`",
        f"- S3 prefix: `{prefix}`",
        "- Attach this policy to the service AWS identity before use:",
        "```json",
        json.dumps(policy, indent=2),
        "```",
        "",
    ]
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write("\n".join(lines))
    else:
        print("\n".join(lines))


def main() -> int:
    try:
        prefix = normalize_prefix(os.environ.get("S3_PREFIX", ""))
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
        identity = json.loads(
            subprocess.run(
                ["aws", "sts", "get-caller-identity", "--region", region, "--output", "json"],
                capture_output=True,
                check=True,
                text=True,
            ).stdout
        )
        partition = identity["Arn"].split(":", 2)[1]
        provisioner = S3Provisioner(region, identity["Account"], partition)
        policy = provisioner.provision(prefix)
        append_summary(provisioner, prefix, policy)
    except (AwsCliError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
