"""
This is an elaborate hack sourced from https://dev.to/redhap/efficient-django-delete-cascade-43i5

The purpose is to avoid the memory spike caused by the deletion of an object at the apex of a large
tree of cascading deletes. As per the Django documentation [0], cascading deletes are handled by
Django and require objects to be loaded into memory. If the tree of objects is sufficiently large,
this can result in a fatal memory spike.

The alternative is an overridden delete() which knows what the cascade tree looks like and deletes
those manually [1]

It is possible that [2] may eliminate the need for this hack in the future, although perhaps not
because we use signals to trigger cache invalidation.

[0] https://docs.djangoproject.com/en/4.2/ref/models/querysets/#delete
[1] https://code.djangoproject.com/ticket/21961
[2] https://til.simonwillison.net/django/efficient-bulk-deletions-in-django
"""

from django.db import models
from django.db import transaction
from django.db.models.sql.compiler import SQLDeleteCompiler
from sqlparse import format as format_sql
import logging


LOG = logging.getLogger(__name__)


def get_delete_sql(query):
    """
    Compile a DELTE SQL statement from a QuerySet instance
    Params:
        query (QuerySet) : The query to compile to SQL
    Returns (tuple):
        (sql, params) : sql is the sql statement to exeucte
                        params are any parameters for the statement to use. This is a tuple.
    """
    return SQLDeleteCompiler(query.query, transaction.get_connection(), query.db).as_sql()


def get_update_sql(query, **updatespec):
    """
    Compile the query with the update specifications into an UPDATE SQL statement and parameters
    Params:
        query (QuerySet) : The QuerySet that will select the row(s) to update
        updatespec (dict) : {column: new_value} expressed in the function call as
            `column=new_value` named parameters
    Returns (tuple):
        (sql, params) : sql is the sql statement to exeucte
                        params are any parameters for the statement to use. This is a tuple.
    """
    assert query.query.can_filter()
    query.for_write = True
    q = query.query.chain(models.sql.UpdateQuery)
    q.add_update_values(updatespec)
    q._annotations = None

    return q.get_compiler(query.db).as_sql()


def execute_compiled_sql(sql, params=None):
    """
    Execute the SQL with any parameters directly using connection.cursor()
    Params:
        sql (str) : The parameterized SQL statement.
        params (tuple/list) : Parameters for the sql statement or None
    Returns :
        int : rows affected by the statement
    """
    rows_affected = 0
    with transaction.get_connection().cursor() as cur:
        params = params or None
        LOG.debug(format_sql(cur.mogrify(sql, params), reindent_aligned=True))
        cur.execute(sql, params)
        rows_affected = cur.rowcount

    return rows_affected


def execute_delete_sql(query):
    """Execute the SQL for handling the deletion"""
    return execute_compiled_sql(*get_delete_sql(query))


def execute_update_sql(query, **updatespec):
    """Execute the SQL for handling the update"""
    return execute_compiled_sql(*get_update_sql(query, **updatespec))


def cascade_delete(from_model, instance_pk_query, skip_relations=None, base_model=None, level=0):
    """
    Performs a cascading delete by walking the Django model relations and executing compiled SQL
    to perform the on_delete actions instead or running the collector.
    Parameters:
        from_model (models.Model) : A model class that is the relation root
        instance_pk_query (QuerySet) : A query for the records to delete and cascade from
        base_model (None; Model) : The root model class, If null, this will be set for you.
        level (int) : Recursion depth. This is used in logging only. Do not set.
        skip_relations (Iterable of Models) : Relations to skip over in case they are handled
            explicitly elsewhere
    """
    if base_model is None:
        base_model = from_model
    if skip_relations is None:
        skip_relations = []
    instance_pk_query = instance_pk_query.values_list("pk").order_by()
    LOG.debug(
        f"Level {level} Delete Cascade for {base_model.__name__}: "
        f"Checking relations for {from_model.__name__}"
    )
    for model_relation in from_model._meta.related_objects:
        related_model = model_relation.related_model

        LOG.debug(
            f"Relation from {related_model} to {base_model}: on_delete={model_relation.on_delete}"
        )
        if related_model in skip_relations:
            LOG.debug(f"SKIPPING RELATION {related_model.__name__} from caller directive")
            continue

        if model_relation.on_delete is None:
            # This appears to be the case when the field is pointing to a many-to-many table
            # and also the back-relationship to the parent on multi-table objects
            pass
        elif model_relation.on_delete.__name__ == "DO_NOTHING":
            pass
        elif model_relation.on_delete.__name__ in {"PROTECT", "SET_DEFAULT", "SET", "RESTRICT"}:
            # At the present moment, these are not needed in the object trees with which we are
            # concerned
            raise models.ProtectedError(
                "Cannot execute cascade delete - unsupported '{}' relationship encountered".format(
                    model_relation.on_delete.__name__
                ),
                [],  # todo
            )
        elif model_relation.on_delete.__name__ == "SET_NULL":
            filterspec = {
                f"{model_relation.remote_field.column}__in": models.Subquery(instance_pk_query)
            }
            updatespec = {f"{model_relation.remote_field.column}": None}
            LOG.debug(
                f"    Executing SET NULL constraint action on {related_model.__name__}"
                f" relation of {from_model.__name__}"
            )
            rec_count = execute_update_sql(related_model.objects.filter(**filterspec), **updatespec)
            LOG.debug(f"    Updated {rec_count} records in {related_model.__name__}")
        elif model_relation.on_delete.__name__ == "CASCADE":
            filterspec = {
                f"{model_relation.remote_field.column}__in": models.Subquery(instance_pk_query)
            }
            related_pk_values = related_model.objects.filter(**filterspec).values_list(
                related_model._meta.pk.name
            )
            LOG.debug(f"    Cascading delete to relations of {related_model.__name__}")
            cascade_delete(
                related_model,
                related_pk_values,
                base_model=base_model,
                level=level + 1,
                skip_relations=skip_relations,
            )

    LOG.debug(f"Level {level}: delete records from {from_model.__name__}")
    if level == 0:
        del_query = instance_pk_query
        # make sure we send signals for the top-level deletion
        # important for repositories as we have to invalidate caches
        rec_count = base_model.objects.filter(pk__in=del_query).delete()
        LOG.debug(f"Deleted {rec_count}")
    else:
        filterspec = {f"{from_model._meta.pk.name}__in": models.Subquery(instance_pk_query)}
        del_query = from_model.objects.filter(**filterspec)
        rec_count = execute_delete_sql(del_query)
        LOG.debug(f"Deleted {rec_count} records from {from_model.__name__}")
