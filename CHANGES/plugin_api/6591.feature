TaskGroups now have an 'all_tasks_dispatched' field that can be used to notify systems that no
further tasks will be dispatched for a TaskGroup. Plugin writers should call ".finish()" on all
TaskGroups created once they are done using them to set this field.
