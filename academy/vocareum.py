from .exceptions import LabStartError, LabTimeout, VocareumLoadError


def _current_lab_frame(frame):
    return next(
        (
            candidate
            for candidate in frame.page.frames
            if "labs.vocareum.com" in candidate.url and "/main/main.php" in candidate.url
        ),
        frame,
    )


def _lab_is_ready(page):
    body = " ".join(page.locator("body").inner_text().lower().split())
    return "lab status: ready" in body or "lab is ready" in body


def _wait_for_lab(page, start, timeout_seconds):
    for _ in range(timeout_seconds):
        if _lab_is_ready(page):
            return _current_lab_frame(page)
        body = page.locator("body").inner_text().lower()
        if "error" in body and "start lab" in body:
            raise LabStartError("Vocareum reported a lab startup error")
        page.wait_for_timeout(1000)
        if not page.get_by_text("AWS", exact=True).count() and not start.count():
            raise VocareumLoadError("Vocareum lab controls were not found")
    raise LabTimeout("Learner Lab did not become ready before the timeout")


def start_lab(page, timeout_seconds=300):
    try:
        page.wait_for_load_state("domcontentloaded")
        start = page.get_by_role("button", name="Start Lab", exact=True)
        if _lab_is_ready(page):
            return _current_lab_frame(page)
        try:
            start.wait_for(state="visible", timeout=30000)
        except Exception:
            if not _lab_is_ready(page):
                raise VocareumLoadError("Vocareum lab controls did not finish loading")
        if start.count() and start.first.is_visible():
            start.first.click()
        # Vocareum status indicators vary; use accessible labels/text and common
        # status attributes instead of coordinates. Polling is bounded.
        return _wait_for_lab(page, start, timeout_seconds)
    except (LabStartError, VocareumLoadError):
        raise
    except Exception as exc:
        raise LabStartError(f"Could not start the Learner Lab ({type(exc).__name__})") from exc


def open_aws_details(page):
    # The Academy Sandbox exposes its credential panel through the Details
    # dropdown as "AWS: Show" (rather than a button named "AWS Details").
    dropdown = page.locator("#reportsdropdown")
    if not dropdown.count():
        from .exceptions import AwsDetailsNotFound
        raise AwsDetailsNotFound("Vocareum Details menu was not found")
    dropdown.evaluate("element => element.click()")

    show = page.locator("#showawsbtn")
    try:
        show.wait_for(state="visible", timeout=5000)
    except Exception as exc:
        from .exceptions import AwsDetailsNotFound
        raise AwsDetailsNotFound("AWS Details action was not available") from exc
    # Vocareum's backdrop can intercept pointer events in the embedded LTI
    # frame. Dispatch the button's normal DOM click after confirming visibility.
    show.evaluate("element => element.click()")

    try:
        modal = page.locator("#modal-table-report-aws")
        modal.wait_for(state="visible", timeout=10000)
        # Vocareum's Cloud Access view labels these values "AccessKey" and
        # "SecretKey" and populates the table asynchronously.
        page.get_by_text("AccessKey", exact=True).wait_for(
            state="visible", timeout=20000
        )
        page.get_by_text("SecretKey", exact=True).wait_for(
            state="visible", timeout=5000
        )
    except Exception as exc:
        from .exceptions import AwsDetailsNotFound
        raise AwsDetailsNotFound("AWS Details did not show credentials") from exc
