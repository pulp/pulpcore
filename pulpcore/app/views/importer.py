from gettext import gettext as _
import json
import os
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView
from rest_framework.response import Response

from pulpcore.app import settings
from pulpcore.app.serializers import PulpImportCheckResponseSerializer, PulpImportCheckSerializer


def _check_allowed_import_path(a_path):
    user_provided_realpath = os.path.realpath(a_path)
    for allowed_path in settings.ALLOWED_IMPORT_PATHS:
        if user_provided_realpath.startswith(allowed_path):
            return True, None
    return False, _(
        "{} is not an allowed import path".format(os.path.dirname(os.path.realpath(a_path)))
    )


def _validate_file(in_param, data):
    """
    Returns a (is-valid, msgs[]) tuple describing all problems found with data[in_param]

    We check for a number of things, attempting to return all the errors we can find. We don't want
    to give out information for files in arbitrary locations on the filesystem; if the check
    for ALLOWED_IMPORT_PATHS fails, we report that and ignore any other problems.

    If the directory containing the base-file doesn't exist, or isn't readable, or the specified
    file doesn't exist, report and return.

    Error-messages for all other checks are additive.
    """
    # check allowed, leave if failed
    file = data[in_param]
    real_file = os.path.realpath(file)
    rc, msg = _check_allowed_import_path(real_file)
    if not rc:
        return rc, [msg]

    # check directory-sanity, leave if failed
    owning_dir = os.path.dirname(real_file)
    if not os.path.exists(owning_dir):
        return False, [_("directory {} does not exist").format(owning_dir)]
    if not os.access(owning_dir, os.R_OK):
        return False, [_("directory {} does not allow read-access").format(owning_dir)]

    # check file-exists, leave if failed
    if not os.path.exists(real_file):
        return False, [_("file {} does not exist").format(real_file)]

    # check file-sanity
    msgs = []
    isfile = os.path.isfile(real_file)
    readable = os.access(real_file, os.R_OK)

    rc = isfile and readable
    if not isfile:
        msgs.append(_("{} is not a file".format(real_file)))
    if not readable:
        msgs.append(_("{} exists but cannot be read".format(real_file)))

    # extra check for toc-dir-write
    if in_param == "toc":
        if not os.access(owning_dir, os.W_OK):
            rc = False
            msgs.append(_("directory {} must allow pulp write-access".format(owning_dir)))

    return rc, msgs


class PulpImporterImportCheckView(APIView):
    """
    Returns validity of proposed parameters for a PulpImport call.
    """

    @extend_schema(
        summary="Validate the parameters to be used for a PulpImport call",
        operation_id="pulp_import_check_post",
        request=PulpImportCheckSerializer,
        responses={200: PulpImportCheckResponseSerializer},
    )
    def post(self, request, format=None):
        """
        Evaluates validity of proposed PulpImport parameters 'toc', 'path', and 'repo_mapping'.

        * Checks that toc, path are in ALLOWED_IMPORT_PATHS
        * if ALLOWED:
          * Checks that toc, path exist and are readable
          * If toc specified, checks that containing dir is writeable
        * Checks that repo_mapping is valid JSON
        """
        serializer = PulpImportCheckSerializer(data=request.data)
        if serializer.is_valid():
            data = {}
            if "toc" in serializer.data:
                data["toc"] = {}
                data["toc"]["context"] = serializer.data["toc"]
                data["toc"]["is_valid"], data["toc"]["messages"] = _validate_file(
                    "toc", serializer.data
                )

            if "path" in serializer.data:
                data["path"] = {}
                data["path"]["context"] = serializer.data["path"]
                data["path"]["is_valid"], data["path"]["messages"] = _validate_file(
                    "path", serializer.data
                )

            if "repo_mapping" in serializer.data:
                data["repo_mapping"] = {}
                data["repo_mapping"]["context"] = serializer.data["repo_mapping"]
                try:
                    json.loads(serializer.data["repo_mapping"])
                    data["repo_mapping"]["is_valid"] = True
                    data["repo_mapping"]["messages"] = []
                except json.JSONDecodeError:
                    data["repo_mapping"]["is_valid"] = False
                    data["repo_mapping"]["messages"] = [_("invalid JSON")]

            crs = PulpImportCheckResponseSerializer(data, context={"request": request})
            return Response(crs.data)
        return Response(serializer.errors, status=400)
