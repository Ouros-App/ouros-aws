import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from academy.canvas import _open_course
from academy.config import load_config
from academy.credentials import export_github_env, parse_aws_details
from academy.exceptions import AwsDetailsNotFound, ConfigurationError, CredentialsInvalid, LabTimeout
from academy.vocareum import start_lab


class ConfigTests(unittest.TestCase):
    def test_loads_required_values_and_defaults(self):
        with patch.dict(os.environ, {
            "CANVAS_USERNAME": "student",
            "CANVAS_PASSWORD": "password",
            "CANVAS_LOGIN_URL": "https://canvas.example/login",
        }, clear=True):
            config = load_config()
        self.assertEqual(config["region"], "us-east-1")
        self.assertEqual(config["lab_link_text"], "Sandbox Environment")
        self.assertTrue(config["headless"])

    def test_loads_overrides_and_false_headless(self):
        with patch.dict(os.environ, {
            "CANVAS_USERNAME": "student",
            "CANVAS_PASSWORD": "password",
            "CANVAS_LOGIN_URL": "https://canvas.example/login",
            "AWS_REGION": "us-west-2",
            "ACADEMY_TIMEOUT_MS": "12000",
            "LAB_TIMEOUT_SECONDS": "60",
            "PLAYWRIGHT_HEADLESS": "false",
        }, clear=True):
            config = load_config()
        self.assertEqual(config["region"], "us-west-2")
        self.assertEqual(config["timeout_ms"], 12000)
        self.assertEqual(config["lab_timeout_seconds"], 60)
        self.assertFalse(config["headless"])

    def test_missing_required_values_are_reported(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError):
                load_config()


class CredentialTests(unittest.TestCase):
    def test_parses_console_labels_and_optional_session_token(self):
        credentials = parse_aws_details(
            "AccessKey: ASIA1234567890ABCD\n"
            "SecretKey: " + "s" * 40 + "\n"
            "SessionToken: " + "t" * 40,
            "us-west-2",
        )
        self.assertEqual(credentials["AWS_ACCESS_KEY_ID"], "ASIA1234567890ABCD")
        self.assertEqual(credentials["AWS_REGION"], "us-west-2")
        self.assertIn("AWS_SESSION_TOKEN", credentials)

    def test_parses_environment_names(self):
        credentials = parse_aws_details(
            "AWS_ACCESS_KEY_ID=AKIA1234567890ABCD\n"
            "AWS_SECRET_ACCESS_KEY=" + "s" * 40
        )
        self.assertNotIn("AWS_SESSION_TOKEN", credentials)

    def test_rejects_missing_and_unrecognized_credentials(self):
        with self.assertRaises(AwsDetailsNotFound):
            parse_aws_details("no credentials")
        with self.assertRaises(CredentialsInvalid):
            parse_aws_details("AccessKey: XXXX1234567890ABCD\nSecretKey: " + "s" * 40)

    def test_exports_only_to_environment_file_and_masks_secrets(self):
        values = {
            "AWS_ACCESS_KEY_ID": "ASIA1234567890ABCD",
            "AWS_SECRET_ACCESS_KEY": "s" * 40,
            "AWS_REGION": "us-east-1",
        }
        with tempfile.NamedTemporaryFile(mode="r+", encoding="utf-8") as env_file:
            with patch.dict(os.environ, {"GITHUB_ENV": env_file.name}, clear=True):
                with patch("builtins.print") as output:
                    export_github_env(values)
            env_file.seek(0)
            content = env_file.read()
        self.assertIn("AWS_REGION=us-east-1", content)
        self.assertEqual(output.call_count, 2)

    def test_local_export_does_not_write_a_file(self):
        values = {"AWS_REGION": "us-east-1"}
        with patch.dict(os.environ, {}, clear=True):
            export_github_env(values)
            self.assertEqual(os.environ["AWS_REGION"], "us-east-1")


class NavigationTests(unittest.TestCase):
    def test_waits_for_configured_course_before_using_fallback(self):
        configured_course = Mock()
        fallback_course = Mock()
        page = Mock()
        config = {"course_name": "Configured course", "timeout_ms": 12000}

        with patch(
            "academy.canvas._course_locator",
            side_effect=[configured_course, fallback_course],
        ):
            _open_course(page, config)

        configured_course.first.wait_for.assert_called_once_with(
            state="visible", timeout=12000
        )
        configured_course.first.click.assert_called_once_with()
        fallback_course.first.wait_for.assert_not_called()

    def test_missing_start_controls_can_timeout_without_being_reclassified(self):
        page = Mock()
        page.locator.return_value.inner_text.return_value = "Starting lab"
        start_button = Mock()
        start_button.count.side_effect = [1, 0]
        start_button.first.is_visible.return_value = True
        page.get_by_role.return_value = start_button
        start_button.wait_for.return_value = None

        with self.assertRaises(LabTimeout):
            start_lab(page, timeout_seconds=2)

        self.assertEqual(page.wait_for_timeout.call_count, 2)
        start_button.count.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
