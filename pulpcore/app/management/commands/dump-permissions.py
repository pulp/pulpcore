from gettext import gettext as _
from functools import lru_cache
import json
import sys

from django.db import connection
from django.core.management import BaseCommand, CommandError
from django.contrib.contenttypes.models import ContentType

from pulpcore.app.util import get_url


SEPARATOR = "\t"


@lru_cache
def _get_model(content_type_id):
    return ContentType.objects.get(pk=content_type_id).model_class()


def _get_url(content_type_id, object_pk):
    obj = _get_model(content_type_id).objects.get(pk=object_pk)
    return get_url(obj)


def _get_user_model_permissions():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                auth_user.id,
                array_agg(auth_permission.id),
                username,
                array_agg(concat(app_label, '.', codename))
            FROM auth_user_user_permissions
            LEFT JOIN auth_user ON (user_id=auth_user.id)
            LEFT JOIN auth_permission ON (permission_id=auth_permission.id)
            LEFT JOIN django_content_type ON (content_type_id=django_content_type.id)
            GROUP BY auth_user.id
            ORDER BY username
            """
        )
        while row := cursor.fetchone():
            (
                user_id,
                permission_pks,
                username,
                permissions,
            ) = row
            yield {"username": username, "permissions": permissions}


def _get_group_model_permissions():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                auth_group.id,
                array_agg(auth_permission.id),
                auth_group.name,
                array_agg(concat(app_label, '.', codename))
            FROM auth_group_permissions
            LEFT JOIN auth_group ON (group_id=auth_group.id)
            LEFT JOIN auth_permission ON (permission_id=auth_permission.id)
            LEFT JOIN django_content_type ON (content_type_id=django_content_type.id)
            GROUP BY auth_group.id
            ORDER BY auth_group.name
            """
        )
        while row := cursor.fetchone():
            (
                group_id,
                permission_pks,
                groupname,
                permissions,
            ) = row

            yield {"groupname": groupname, "permissions": permissions}


def _get_user_object_permissions():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                auth_user.id,
                django_content_type.id,
                object_pk,
                array_agg(auth_permission.id),
                app_label,
                model,
                username,
                array_agg(concat(app_label, '.', codename))
            FROM guardian_userobjectpermission
            LEFT JOIN django_content_type ON (content_type_id=django_content_type.id)
            LEFT JOIN auth_user ON (user_id=auth_user.id)
            LEFT JOIN auth_permission ON (permission_id=auth_permission.id)
            GROUP BY auth_user.id, django_content_type.id, object_pk
            ORDER BY username, django_content_type.id, object_pk
            """
        )
        while row := cursor.fetchone():
            (
                user_id,
                content_type_id,
                object_pk,
                permission_pks,
                app_label,
                model,
                username,
                permissions,
            ) = row
            try:
                obj = _get_url(content_type_id, object_pk)
            except Exception:
                obj = f"{app_label}.{model}:{object_pk}"
            yield {"username": username, "object": obj, "permissions": permissions}


def _get_group_object_permissions():
    with connection.cursor() as cursor:
        cursor.execute(
            """
                    SELECT
                        auth_group.id,
                        django_content_type.id,
                        object_pk,
                        array_agg(auth_permission.id),
                        app_label,
                        model,
                        auth_group.name,
                        array_agg(concat(app_label, '.', codename))
                    FROM guardian_groupobjectpermission
                    LEFT JOIN django_content_type ON (content_type_id=django_content_type.id)
                    LEFT JOIN auth_group ON (group_id=auth_group.id)
                    LEFT JOIN auth_permission ON (permission_id=auth_permission.id)
                    GROUP BY auth_group.id, django_content_type.id, object_pk
                    ORDER BY auth_group.name, django_content_type.id, object_pk
                    """
        )
        while row := cursor.fetchone():
            (
                group_id,
                content_type_id,
                object_pk,
                permission_pks,
                app_label,
                model,
                groupname,
                permissions,
            ) = row
            try:
                obj = _get_url(content_type_id, object_pk)
            except Exception:
                obj = f"{app_label}.{model}:{object_pk}"
            yield {"groupname": groupname, "object": obj, "permissions": permissions}


class Command(BaseCommand):
    """
    Django management command for getting a data dump of deprecated permission.
    """

    help = _("Dumps deprecated permissions.")

    def add_arguments(self, parser):
        parser.add_argument("--tabular", action="store_true", help=_("Output table format."))

    def handle(self, *args, **options):
        tabular = options.get("tabular", False)

        if tabular:
            try:
                from prettytable import PrettyTable
            except ImportError:
                raise CommandError("'prettytable' package must be installed for tabular output.")

        table_names = connection.introspection.table_names()
        guardian_uop_available = "guardian_userobjectpermission" in table_names
        guardian_gop_available = "guardian_groupobjectpermission" in table_names

        # User model permissions
        if tabular:
            print("# ==== " + _("User model permissions") + " ====")
            table = PrettyTable()
            table.field_names = [_("username"), _("permission")]
            for t in _get_user_model_permissions():
                table.add_row([t["username"], t["permissions"][0]])
                table.add_rows((["", perm] for perm in t["permissions"][1:]))
            print(table)
            print()

            print("# ==== " + _("Group model permissions") + " ====")
            table = PrettyTable()
            table.field_names = [_("groupname"), _("permission")]
            for t in _get_group_model_permissions():
                table.add_row([t["groupname"], t["permissions"][0]])
                table.add_rows((["", perm] for perm in t["permissions"][1:]))
            print(table)
            print()

            if guardian_uop_available:
                print("# ==== " + _("User object permissions") + " ====")
                table = PrettyTable()
                table.field_names = [_("username"), _("object"), _("permission")]
                for t in _get_user_object_permissions():
                    table.add_row([t["username"], t["object"], t["permissions"][0]])
                    table.add_rows((["", "", perm] for perm in t["permissions"][1:]))
                print(table)
                print()

            if guardian_gop_available:
                print("# ==== " + _("Group object permissions") + " ====")
                table = PrettyTable()
                table.field_names = [_("groupname"), _("object"), _("permissions")]
                for t in _get_group_object_permissions():
                    table.add_row([t["groupname"], t["object"], t["permissions"][0]])
                    table.add_rows((["", "", perm] for perm in t["permissions"][1:]))
                print(table)
                print()

        else:
            # TODO Streaming would be nice...
            data = {
                "user_model_permissions": list(_get_user_model_permissions()),
                "group_model_permissions": list(_get_group_model_permissions()),
            }
            if guardian_uop_available:
                data["user_object_permissions"] = list(_get_user_object_permissions())
            if guardian_gop_available:
                data["group_object_permissions"] = list(_get_group_object_permissions())

            json.dump(
                data,
                sys.stdout,
            )
