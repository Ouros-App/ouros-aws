import time

from .exceptions import CanvasLoginError, CourseNotFound, LearnerLabNotFound, VocareumLoadError


def _login(page, config):
    page.set_default_timeout(config["timeout_ms"])
    password = page.get_by_label("Password")
    try:
        page.goto(config["login_url"], wait_until="domcontentloaded")
        user = page.get_by_label("Email").or_(page.get_by_label("Username"))
        user.fill(config["username"])
        password.fill(config["password"])
        page.get_by_role("button", name="Log in", exact=False).click()
        # Canvas may navigate asynchronously after the click.
        password.wait_for(state="hidden", timeout=config["timeout_ms"])
        page.wait_for_load_state("domcontentloaded")
        if password.is_visible():
            raise CanvasLoginError("Canvas did not accept the supplied login")
    except CanvasLoginError:
        raise
    except Exception as exc:
        raise CanvasLoginError("Could not complete Canvas login") from exc
    print("[academy] Canvas login successful")


def _open_course(page, config):
    course = _course_locator(page, config["course_name"])
    try:
        course.first.wait_for(state="visible", timeout=config["timeout_ms"])
    except Exception:
        course = _course_locator(page, "AWS Academy Cloud Foundations")
        try:
            course.first.wait_for(state="visible", timeout=config["timeout_ms"])
        except Exception as exc:
            raise CourseNotFound("AWS Academy course was not found") from exc
    course.first.click()
    print("[academy] Academy course opened")


def _course_locator(page, course_name):
    return page.get_by_role("link", name=course_name, exact=False).or_(
        page.get_by_text(course_name, exact=False)
    )


def _open_modules(page):
    try:
        page.get_by_role("link", name="Módulos", exact=False).click()
    except Exception:
        try:
            page.get_by_text("Módulos", exact=True).first.click()
        except Exception as exc:
            raise LearnerLabNotFound("Course modules page was not found") from exc
    print("[academy] Course modules opened")


def _launch_lab(page, config):
    lab = page.get_by_role("link", name=config["lab_link_text"], exact=False)
    try:
        lab.first.wait_for(state="visible", timeout=config["timeout_ms"])
    except Exception as exc:
        raise LearnerLabNotFound("Learner Lab launch link was not found") from exc
    lab.first.click()


def _find_lab_frame(page, config):
    deadline = time.monotonic() + config["timeout_ms"] / 1000
    while time.monotonic() < deadline:
        for frame in page.frames:
            if "labs.vocareum.com" in frame.url and "/main/main.php" in frame.url:
                return frame
        page.wait_for_timeout(250)
    raise VocareumLoadError("Vocareum did not load in the Sandbox Environment")


def open_vocareum(page, config):
    _login(page, config)
    _open_course(page, config)
    _open_modules(page)
    _launch_lab(page, config)
    # Sandbox Environment is an LTI launch embedded asynchronously in Canvas.
    return _find_lab_frame(page, config)
