from pulpcore.constants import (  # noqa
    ALL_KNOWN_CONTENT_CHECKSUMS,
    SYNC_MODES,
    SYNC_CHOICES,
    TASK_STATES,
    TASK_CHOICES,
    TASK_FINAL_STATES,
)


@property
def API_ROOT():
    from django.conf import settings
    from pulpcore.app.loggers import deprecation_logger

    deprecation_logger.warn(
        "The API_ROOT constant has been deprecated and turned into a setting. Please use "
        "`settings.V3_API_ROOT_NO_FRONT_SLASH` instead. This symbol will be deleted with pulpcore "
        "3.20."
    )
    return settings.V3_API_ROOT_NO_FRONT_SLASH
