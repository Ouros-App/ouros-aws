import hashlib
import unittest
from unittest.mock import patch

from scripts.provision_audience_storage import (
    S3Provisioner,
    bucket_names,
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


if __name__ == "__main__":
    unittest.main()
