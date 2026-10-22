import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.provision_audience_storage import (
    AWS_CLI_TIMEOUT_SECONDS,
    AwsCliError,
    S3Provisioner,
    append_summary,
    bucket_names,
    main,
    normalize_prefix,
    runtime_policy,
)


class AudienceStoragePolicyTests(unittest.TestCase):
    def test_normalizes_prefix_slashes(self):
        self.assertEqual(normalize_prefix("/tenant-a/audiences/"), "tenant-a/audiences")
        self.assertEqual(normalize_prefix(""), "")

    def test_rejects_wildcards_in_prefix(self):
        for prefix in ("tenant/*", "tenant/?"):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                normalize_prefix(prefix)

    def test_runtime_policy_limits_object_access_to_prefix_without_delete(self):
        policy = runtime_policy("arn:aws:s3:::audience", "tenant-a")

        self.assertEqual(policy["Statement"][0]["Action"], ["s3:ListBucket"])
        object_statement = policy["Statement"][1]
        self.assertEqual(object_statement["Action"], ["s3:GetObject", "s3:PutObject"])
        self.assertEqual(
            object_statement["Resource"],
            "arn:aws:s3:::audience/tenant-a/audiences/*",
        )
        self.assertNotIn("s3:DeleteObject", object_statement["Action"])

    def test_empty_prefix_targets_audiences_root(self):
        policy = runtime_policy("arn:aws:s3:::audience", "")
        self.assertEqual(
            policy["Statement"][1]["Resource"],
            "arn:aws:s3:::audience/audiences/*",
        )

    def test_bucket_names_are_deterministic_and_valid_length(self):
        bucket, logs = bucket_names("123456789012")
        self.assertEqual(bucket, "ouros-audience-engine-123456789012")
        suffix = hashlib.sha256(bucket.encode()).hexdigest()[:6]
        self.assertEqual(logs, bucket[:50] + "-logs-" + suffix)
        self.assertLessEqual(len(logs), 63)

    def test_bucket_policies_keep_tls_and_logs_scoped(self):
        provisioner = S3Provisioner("us-east-1", "123456789012", "aws")
        audience_deny = provisioner.audience_policy()["Statement"][0]
        self.assertEqual(audience_deny["Condition"]["Bool"]["aws:SecureTransport"], "false")
        logs_allow = provisioner.access_logs_policy()["Statement"][0]
        self.assertEqual(logs_allow["Principal"]["Service"], "logging.s3.amazonaws.com")
        self.assertEqual(
            logs_allow["Condition"]["StringEquals"]["aws:SourceAccount"],
            "123456789012",
        )
        self.assertEqual(
            logs_allow["Resource"],
            f"{provisioner.logs_arn}/{provisioner.bucket}/*",
        )

    def test_refuses_orphaned_log_bucket_without_adopting_it(self):
        provisioner = S3Provisioner("us-east-1", "123456789012", "aws")

        with (
            patch.object(provisioner, "bucket_exists", side_effect=[False, True]),
            patch.object(provisioner, "ensure_bucket") as ensure_bucket,
            self.assertRaisesRegex(RuntimeError, "refusing to adopt it"),
        ):
            provisioner.provision("")

        ensure_bucket.assert_not_called()



class ProvisioningFlowTests(unittest.TestCase):
    def test_creates_and_verifies_buckets_without_object_lock_api(self):
        provisioner = S3Provisioner("us-east-1", "123456789012", "aws")
        state = {
            "tags": {},
            "encrypted": set(),
            "policies": {},
            "lifecycle": None,
            "logging": None,
            "public_access": set(),
            "calls": [],
        }

        def run(*args):
            operation = args[0]
            state["calls"].append(operation)
            name = args[args.index("--bucket") + 1] if "--bucket" in args else None

            if operation == "head-bucket":
                raise AwsCliError(list(args), "An error occurred (404) when calling HeadBucket")
            if operation == "create-bucket":
                return ""
            if operation == "get-bucket-tagging":
                if name not in state["tags"]:
                    raise AwsCliError(list(args), "An error occurred (NoSuchTagSet) when calling GetBucketTagging")
                return json.dumps({"TagSet": state["tags"][name]})
            if operation == "put-bucket-tagging":
                state["tags"][name] = json.loads(args[args.index("--tagging") + 1])["TagSet"]
                return ""
            if operation == "put-public-access-block":
                state["public_access"].add(name)
                return ""
            if operation == "get-public-access-block":
                return json.dumps({
                    "PublicAccessBlockConfiguration": {
                        "BlockPublicAcls": True,
                        "IgnorePublicAcls": True,
                        "BlockPublicPolicy": True,
                        "RestrictPublicBuckets": True,
                    }
                })
            if operation == "get-bucket-encryption":
                if name not in state["encrypted"]:
                    raise AwsCliError(list(args), "An error occurred (ServerSideEncryptionConfigurationNotFoundError) when calling GetBucketEncryption")
                return json.dumps({"ServerSideEncryptionConfiguration": {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}})
            if operation == "put-bucket-encryption":
                state["encrypted"].add(name)
                return ""
            if operation == "get-bucket-policy":
                if name not in state["policies"]:
                    raise AwsCliError(list(args), "An error occurred (NoSuchBucketPolicy) when calling GetBucketPolicy")
                return json.dumps({"Policy": json.dumps(state["policies"][name])})
            if operation == "put-bucket-policy":
                state["policies"][name] = json.loads(args[args.index("--policy") + 1])
                return ""
            if operation == "get-bucket-lifecycle-configuration":
                if state["lifecycle"] is None:
                    raise AwsCliError(list(args), "An error occurred (NoSuchLifecycleConfiguration) when calling GetBucketLifecycleConfiguration")
                return json.dumps(state["lifecycle"])
            if operation == "put-bucket-lifecycle-configuration":
                state["lifecycle"] = json.loads(args[args.index("--lifecycle-configuration") + 1])
                return ""
            if operation == "get-bucket-logging":
                return json.dumps({"LoggingEnabled": state["logging"]} if state["logging"] else {})
            if operation == "put-bucket-logging":
                state["logging"] = json.loads(args[args.index("--bucket-logging-status") + 1])["LoggingEnabled"]
                return ""
            self.fail(f"Unexpected AWS CLI operation: {operation}")

        with patch.object(provisioner, "_run", side_effect=run):
            policy = provisioner.provision("tenant-a")

        self.assertEqual(policy, runtime_policy(provisioner.bucket_arn, "tenant-a"))
        self.assertEqual(state["public_access"], {provisioner.bucket, provisioner.access_logs_bucket})
        self.assertEqual(state["encrypted"], {provisioner.bucket, provisioner.access_logs_bucket})
        self.assertIn("service", {tag["Key"] for tag in state["tags"][provisioner.bucket]})
        self.assertIn("purpose", {tag["Key"] for tag in state["tags"][provisioner.access_logs_bucket]})
        self.assertEqual(state["logging"]["TargetBucket"], provisioner.access_logs_bucket)
        self.assertNotIn("get-bucket-object-lock-configuration", state["calls"])

    def test_rejects_incompatible_existing_encryption(self):
        provisioner = S3Provisioner("us-east-1", "123456789012", "aws")
        with (
            patch.object(
                provisioner,
                "_optional_json",
                return_value={
                    "ServerSideEncryptionConfiguration": {
                        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}]
                    }
                },
            ),
            patch.object(provisioner, "_run") as run,
            self.assertRaisesRegex(RuntimeError, "will not replace"),
        ):
            provisioner.ensure_encryption(provisioner.bucket)
        run.assert_not_called()

    def test_aws_cli_error_extracts_service_error_code(self):
        error = AwsCliError(["s3api", "head-bucket"], "An error occurred (403) when calling HeadBucket")
        self.assertEqual(error.code, "403")

    def test_aws_cli_subprocess_uses_timeout(self):
        provisioner = S3Provisioner("us-east-1", "123456789012", "aws")
        with patch(
            "scripts.provision_audience_storage.subprocess.run",
            return_value=Mock(returncode=0, stdout="ok"),
        ) as run_aws:
            self.assertEqual(provisioner._run("list-buckets"), "ok")
        self.assertEqual(run_aws.call_args.kwargs["timeout"], AWS_CLI_TIMEOUT_SECONDS)


    def test_main_rejects_wildcard_prefix(self):
        with patch.dict(os.environ, {"S3_PREFIX": "bad/*"}, clear=True):
            self.assertEqual(main(), 1)

    def test_main_reports_timeout_and_missing_aws_cli(self):
        errors = (
            subprocess.TimeoutExpired(["aws"], AWS_CLI_TIMEOUT_SECONDS),
            FileNotFoundError("aws"),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                with (
                    patch.dict(os.environ, {"S3_PREFIX": ""}, clear=True),
                    patch("scripts.provision_audience_storage.subprocess.run", side_effect=error),
                    patch("builtins.print") as report_error,
                ):
                    self.assertEqual(main(), 1)
                self.assertTrue(report_error.call_args.args[0].startswith("::error::"))


    def test_main_provisions_and_writes_summary(self):
        instance = Mock()
        instance.provision.return_value = {"Version": "2012-10-17"}
        with (
            patch.dict(os.environ, {"S3_PREFIX": "/tenant-a/"}, clear=True),
            patch(
                "scripts.provision_audience_storage.subprocess.run",
                return_value=Mock(
                    stdout=json.dumps({
                        "Arn": "arn:aws:iam::123456789012:role/test",
                        "Account": "123456789012",
                    })
                ),
            ) as run_aws,
            patch("scripts.provision_audience_storage.S3Provisioner", return_value=instance),
            patch("scripts.provision_audience_storage.append_summary") as write_summary,
        ):
            self.assertEqual(main(), 0)
        instance.provision.assert_called_once_with("tenant-a")
        self.assertEqual(run_aws.call_args.kwargs["timeout"], AWS_CLI_TIMEOUT_SECONDS)
        write_summary.assert_called_once_with(instance, "tenant-a", {"Version": "2012-10-17"})

    def test_summary_appends_to_github_step_summary(self):

        provisioner = S3Provisioner("us-east-1", "123456789012", "aws")
        with tempfile.NamedTemporaryFile(mode="r+", encoding="utf-8") as summary:
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary.name}, clear=True):
                append_summary(provisioner, "", {})
            summary.seek(0)
            self.assertIn(provisioner.bucket, summary.read())

if __name__ == "__main__":
    unittest.main()
