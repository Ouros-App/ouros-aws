import sys
import traceback
from playwright.sync_api import sync_playwright

from .canvas import open_vocareum
from .config import load_config
from .credentials import export_github_env, parse_aws_details
from .exceptions import AcademyError, StsValidationError
from .vocareum import open_aws_details, start_lab


def main():
    try:
        config = load_config()
        print("[academy] Configuration loaded")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=config["headless"])
            context = browser.new_context()
            page = context.new_page()
            try:
                lab_page = open_vocareum(page, config)
                print("[academy] Canvas login successful; Learner Lab opened")
                lab_page = start_lab(lab_page, config["lab_timeout_seconds"])
                print("[academy] AWS lab ready")
                open_aws_details(lab_page)
                details_text = lab_page.locator("body").inner_text()
                # Vocareum often renders credentials in readonly inputs or a
                # textarea, whose values are not included in inner_text().
                field_values = lab_page.locator("input, textarea").evaluate_all(
                    "nodes => nodes.map(node => `${node.name || node.id || ''} ${node.value || ''}`).join('\\n')"
                )
                creds = parse_aws_details(details_text + "\n" + field_values, config["region"])
                export_github_env(creds)
                print("[academy] AWS credentials loaded")
            finally:
                context.close()
                browser.close()
        import subprocess
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--output", "json"],
            check=False, capture_output=True, text=True,
        )
        if result.returncode:
            raise StsValidationError("AWS STS identity validation failed")
        print("[academy] AWS identity validated")
    except AcademyError as exc:
        print(f"::error title={exc.code}::{exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # Report only the exception class: exception text can contain private
        # page content or service responses.
        frames = " -> ".join(frame.name for frame in traceback.extract_tb(exc.__traceback__))
        print(
            f"::error title=ACADEMY_BOOTSTRAP_FAILED::Unexpected bootstrap failure ({type(exc).__name__}; {frames})",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
