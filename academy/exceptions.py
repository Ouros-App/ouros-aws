class AcademyError(RuntimeError):
    """Base exception carrying a safe, actionable workflow error code."""


class ConfigurationError(AcademyError):
    code = "CONFIGURATION_INVALID"


class CanvasLoginError(AcademyError):
    code = "CANVAS_LOGIN_FAILED"


class CourseNotFound(AcademyError):
    code = "COURSE_NOT_FOUND"


class LearnerLabNotFound(AcademyError):
    code = "LEARNER_LAB_NOT_FOUND"


class VocareumLoadError(AcademyError):
    code = "VOCAREUM_LOAD_FAILED"


class LabStartError(AcademyError):
    code = "LAB_START_FAILED"


class LabTimeout(AcademyError):
    code = "LAB_TIMEOUT"


class AwsDetailsNotFound(AcademyError):
    code = "AWS_DETAILS_NOT_FOUND"


class CredentialsInvalid(AcademyError):
    code = "AWS_CREDENTIALS_INVALID"


class StsValidationError(AcademyError):
    code = "STS_VALIDATION_FAILED"
