import time

from .exceptions import CanvasLoginError, CourseNotFound, LearnerLabNotFound, VocareumLoadError


def open_vocareum(page, config):
    page.set_default_timeout(config["timeout_ms"])
    try:
        page.goto(config["login_url"], wait_until="domcontentloaded")
        user = page.get_by_label("Email").or_(page.get_by_label("Username"))
        password = page.get_by_label("Password")
        user.fill(config["username"])
        password.fill(config["password"])
        page.get_by_role("button", name="Log in", exact=False).click()
        # Canvas may navigate asynchronously after the click; checking the
        # field immediately can misclassify a successful login as a failure.
        password.wait_for(state="hidden", timeout=config["timeout_ms"])
        page.wait_for_load_state("domcontentloaded")
        if password.is_visible():
            raise CanvasLoginError("Canvas did not accept the supplied login")
        print("[academy] Canvas login successful")
    except CanvasLoginError:
        raise
    except Exception as exc:
        raise CanvasLoginError("Could not complete Canvas login") from exc

    course = page.get_by_role("link", name=config["course_name"], exact=False)
    if not course.count():
        course = page.get_by_text(config["course_name"], exact=False)
    # The dashboard in this account lists the Cloud Foundations card, which
    # contains the Academy labs. Wait for it to render after Canvas navigation.
    if not course.count() or not course.first.is_visible():
        academy_course = page.get_by_role("link", name="AWS Academy Cloud Foundations", exact=False)
        try:
            academy_course.first.wait_for(state="visible", timeout=config["timeout_ms"])
            course = academy_course
        except Exception:
            academy_course = page.get_by_text("AWS Academy Cloud Foundations", exact=False)
            try:
                academy_course.first.wait_for(state="visible", timeout=1000)
                course = academy_course
            except Exception as exc:
                raise CourseNotFound("AWS Academy course was not found") from exc
    else:
        course.first.wait_for(state="visible", timeout=config["timeout_ms"])
    course.first.click()
    print("[academy] Academy course opened")
    try:
        page.get_by_role("link", name="Módulos", exact=False).click()
    except Exception:
        try:
            page.get_by_text("Módulos", exact=True).first.click()
        except Exception as exc:
            raise LearnerLabNotFound("Course modules page was not found") from exc
    print("[academy] Course modules opened")
    lab = page.get_by_role("link", name=config["lab_link_text"], exact=False)
    try:
        lab.first.wait_for(state="visible", timeout=config["timeout_ms"])
    except Exception:
        raise LearnerLabNotFound("Learner Lab launch link was not found")
    lab.first.click()

    # Sandbox Environment is an LTI launch embedded asynchronously in Canvas.
    deadline = time.monotonic() + config["timeout_ms"] / 1000
    while time.monotonic() < deadline:
        for frame in page.frames:
            if "labs.vocareum.com" in frame.url and "/main/main.php" in frame.url:
                return frame
        page.wait_for_timeout(250)
    raise VocareumLoadError("Vocareum did not load in the Sandbox Environment")
