# TasksApi

All URIs are relative to *http://localhost:24817*

Method | HTTP request | Description
------------- | ------------- | -------------
[**delete**](TasksApi.md#delete) | **DELETE** {task_href} | 
[**list**](TasksApi.md#list) | **GET** /pulp/api/v3/tasks/ | 
[**partial_update**](TasksApi.md#partial_update) | **PATCH** {task_href} | Cancel a task
[**read**](TasksApi.md#read) | **GET** {task_href} | 


# **delete**
> delete(task_href)



A customized named ModelViewSet that knows how to register itself with the Pulp API router.  This viewset is discoverable by its name. \"Normal\" Django Models and Master/Detail models are supported by the ``register_with`` method.  Attributes:     lookup_field (str): The name of the field by which an object should be looked up, in         addition to any parent lookups if this ViewSet is nested. Defaults to 'pk'     endpoint_name (str): The name of the final path segment that should identify the ViewSet's         collection endpoint.     nest_prefix (str): Optional prefix under which this ViewSet should be nested. This must         correspond to the \"parent_prefix\" of a router with rest_framework_nested.NestedMixin.         None indicates this ViewSet should not be nested.     parent_lookup_kwargs (dict): Optional mapping of key names that would appear in self.kwargs         to django model filter expressions that can be used with the corresponding value from         self.kwargs, used only by a nested ViewSet to filter based on the parent object's         identity.     schema (DefaultSchema): The schema class to use by default in a viewset.

### Example

* Basic Authentication (basicAuth):
```python
from __future__ import print_function
import time
import pulpcore.client.pulpcore
from pulpcore.client.pulpcore.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:24817
# See configuration.py for a list of all supported configuration parameters.
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = pulpcore.client.pulpcore.Configuration(
    username = 'YOUR_USERNAME',
    password = 'YOUR_PASSWORD'
)

# Configure API key authorization: cookieAuth
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817",
    api_key = {
        'Session': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Session'] = 'Bearer'

# Enter a context with an instance of the API client
with pulpcore.client.pulpcore.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = pulpcore.client.pulpcore.TasksApi(api_client)
    task_href = 'task_href_example' # str | 

    try:
        api_instance.delete(task_href)
    except ApiException as e:
        print("Exception when calling TasksApi->delete: %s\n" % e)
```

* Api Key Authentication (cookieAuth):
```python
from __future__ import print_function
import time
import pulpcore.client.pulpcore
from pulpcore.client.pulpcore.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:24817
# See configuration.py for a list of all supported configuration parameters.
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = pulpcore.client.pulpcore.Configuration(
    username = 'YOUR_USERNAME',
    password = 'YOUR_PASSWORD'
)

# Configure API key authorization: cookieAuth
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817",
    api_key = {
        'Session': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Session'] = 'Bearer'

# Enter a context with an instance of the API client
with pulpcore.client.pulpcore.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = pulpcore.client.pulpcore.TasksApi(api_client)
    task_href = 'task_href_example' # str | 

    try:
        api_instance.delete(task_href)
    except ApiException as e:
        print("Exception when calling TasksApi->delete: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **task_href** | **str**|  | 

### Return type

void (empty response body)

### Authorization

[basicAuth](../README.md#basicAuth), [cookieAuth](../README.md#cookieAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: Not defined

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**204** | No response body |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list**
> InlineResponse2007 list(child_tasks=child_tasks, created_resources=created_resources, finished_at=finished_at, finished_at__gt=finished_at__gt, finished_at__gte=finished_at__gte, finished_at__lt=finished_at__lt, finished_at__lte=finished_at__lte, finished_at__range=finished_at__range, limit=limit, name=name, name__contains=name__contains, offset=offset, ordering=ordering, parent_task=parent_task, reserved_resources_record=reserved_resources_record, started_at=started_at, started_at__gt=started_at__gt, started_at__gte=started_at__gte, started_at__lt=started_at__lt, started_at__lte=started_at__lte, started_at__range=started_at__range, state=state, state__in=state__in, task_group=task_group, worker=worker, worker__in=worker__in, fields=fields, exclude_fields=exclude_fields)



A customized named ModelViewSet that knows how to register itself with the Pulp API router.  This viewset is discoverable by its name. \"Normal\" Django Models and Master/Detail models are supported by the ``register_with`` method.  Attributes:     lookup_field (str): The name of the field by which an object should be looked up, in         addition to any parent lookups if this ViewSet is nested. Defaults to 'pk'     endpoint_name (str): The name of the final path segment that should identify the ViewSet's         collection endpoint.     nest_prefix (str): Optional prefix under which this ViewSet should be nested. This must         correspond to the \"parent_prefix\" of a router with rest_framework_nested.NestedMixin.         None indicates this ViewSet should not be nested.     parent_lookup_kwargs (dict): Optional mapping of key names that would appear in self.kwargs         to django model filter expressions that can be used with the corresponding value from         self.kwargs, used only by a nested ViewSet to filter based on the parent object's         identity.     schema (DefaultSchema): The schema class to use by default in a viewset.

### Example

* Basic Authentication (basicAuth):
```python
from __future__ import print_function
import time
import pulpcore.client.pulpcore
from pulpcore.client.pulpcore.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:24817
# See configuration.py for a list of all supported configuration parameters.
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = pulpcore.client.pulpcore.Configuration(
    username = 'YOUR_USERNAME',
    password = 'YOUR_PASSWORD'
)

# Configure API key authorization: cookieAuth
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817",
    api_key = {
        'Session': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Session'] = 'Bearer'

# Enter a context with an instance of the API client
with pulpcore.client.pulpcore.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = pulpcore.client.pulpcore.TasksApi(api_client)
    child_tasks = 'child_tasks_example' # str | child_tasks (optional)
created_resources = 'created_resources_example' # str | created_resources (optional)
finished_at = 'finished_at_example' # str | finished_at (optional)
finished_at__gt = 'finished_at__gt_example' # str | finished_at__gt (optional)
finished_at__gte = 'finished_at__gte_example' # str | finished_at__gte (optional)
finished_at__lt = 'finished_at__lt_example' # str | finished_at__lt (optional)
finished_at__lte = 'finished_at__lte_example' # str | finished_at__lte (optional)
finished_at__range = 'finished_at__range_example' # str | finished_at__range (optional)
limit = 56 # int | Number of results to return per page. (optional)
name = 'name_example' # str | name (optional)
name__contains = 'name__contains_example' # str | name__contains (optional)
offset = 56 # int | The initial index from which to return the results. (optional)
ordering = 'ordering_example' # str | Which field to use when ordering the results. (optional)
parent_task = 'parent_task_example' # str | parent_task (optional)
reserved_resources_record = 'reserved_resources_record_example' # str | reserved_resources_record (optional)
started_at = 'started_at_example' # str | started_at (optional)
started_at__gt = 'started_at__gt_example' # str | started_at__gt (optional)
started_at__gte = 'started_at__gte_example' # str | started_at__gte (optional)
started_at__lt = 'started_at__lt_example' # str | started_at__lt (optional)
started_at__lte = 'started_at__lte_example' # str | started_at__lte (optional)
started_at__range = 'started_at__range_example' # str | started_at__range (optional)
state = 'state_example' # str | state (optional)
state__in = 'state__in_example' # str | state__in (optional)
task_group = 'task_group_example' # str | task_group (optional)
worker = 'worker_example' # str | worker (optional)
worker__in = 'worker__in_example' # str | worker__in (optional)
fields = 'fields_example' # str | A list of fields to include in the response. (optional)
exclude_fields = 'exclude_fields_example' # str | A list of fields to exclude from the response. (optional)

    try:
        api_response = api_instance.list(child_tasks=child_tasks, created_resources=created_resources, finished_at=finished_at, finished_at__gt=finished_at__gt, finished_at__gte=finished_at__gte, finished_at__lt=finished_at__lt, finished_at__lte=finished_at__lte, finished_at__range=finished_at__range, limit=limit, name=name, name__contains=name__contains, offset=offset, ordering=ordering, parent_task=parent_task, reserved_resources_record=reserved_resources_record, started_at=started_at, started_at__gt=started_at__gt, started_at__gte=started_at__gte, started_at__lt=started_at__lt, started_at__lte=started_at__lte, started_at__range=started_at__range, state=state, state__in=state__in, task_group=task_group, worker=worker, worker__in=worker__in, fields=fields, exclude_fields=exclude_fields)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling TasksApi->list: %s\n" % e)
```

* Api Key Authentication (cookieAuth):
```python
from __future__ import print_function
import time
import pulpcore.client.pulpcore
from pulpcore.client.pulpcore.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:24817
# See configuration.py for a list of all supported configuration parameters.
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = pulpcore.client.pulpcore.Configuration(
    username = 'YOUR_USERNAME',
    password = 'YOUR_PASSWORD'
)

# Configure API key authorization: cookieAuth
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817",
    api_key = {
        'Session': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Session'] = 'Bearer'

# Enter a context with an instance of the API client
with pulpcore.client.pulpcore.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = pulpcore.client.pulpcore.TasksApi(api_client)
    child_tasks = 'child_tasks_example' # str | child_tasks (optional)
created_resources = 'created_resources_example' # str | created_resources (optional)
finished_at = 'finished_at_example' # str | finished_at (optional)
finished_at__gt = 'finished_at__gt_example' # str | finished_at__gt (optional)
finished_at__gte = 'finished_at__gte_example' # str | finished_at__gte (optional)
finished_at__lt = 'finished_at__lt_example' # str | finished_at__lt (optional)
finished_at__lte = 'finished_at__lte_example' # str | finished_at__lte (optional)
finished_at__range = 'finished_at__range_example' # str | finished_at__range (optional)
limit = 56 # int | Number of results to return per page. (optional)
name = 'name_example' # str | name (optional)
name__contains = 'name__contains_example' # str | name__contains (optional)
offset = 56 # int | The initial index from which to return the results. (optional)
ordering = 'ordering_example' # str | Which field to use when ordering the results. (optional)
parent_task = 'parent_task_example' # str | parent_task (optional)
reserved_resources_record = 'reserved_resources_record_example' # str | reserved_resources_record (optional)
started_at = 'started_at_example' # str | started_at (optional)
started_at__gt = 'started_at__gt_example' # str | started_at__gt (optional)
started_at__gte = 'started_at__gte_example' # str | started_at__gte (optional)
started_at__lt = 'started_at__lt_example' # str | started_at__lt (optional)
started_at__lte = 'started_at__lte_example' # str | started_at__lte (optional)
started_at__range = 'started_at__range_example' # str | started_at__range (optional)
state = 'state_example' # str | state (optional)
state__in = 'state__in_example' # str | state__in (optional)
task_group = 'task_group_example' # str | task_group (optional)
worker = 'worker_example' # str | worker (optional)
worker__in = 'worker__in_example' # str | worker__in (optional)
fields = 'fields_example' # str | A list of fields to include in the response. (optional)
exclude_fields = 'exclude_fields_example' # str | A list of fields to exclude from the response. (optional)

    try:
        api_response = api_instance.list(child_tasks=child_tasks, created_resources=created_resources, finished_at=finished_at, finished_at__gt=finished_at__gt, finished_at__gte=finished_at__gte, finished_at__lt=finished_at__lt, finished_at__lte=finished_at__lte, finished_at__range=finished_at__range, limit=limit, name=name, name__contains=name__contains, offset=offset, ordering=ordering, parent_task=parent_task, reserved_resources_record=reserved_resources_record, started_at=started_at, started_at__gt=started_at__gt, started_at__gte=started_at__gte, started_at__lt=started_at__lt, started_at__lte=started_at__lte, started_at__range=started_at__range, state=state, state__in=state__in, task_group=task_group, worker=worker, worker__in=worker__in, fields=fields, exclude_fields=exclude_fields)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling TasksApi->list: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **child_tasks** | **str**| child_tasks | [optional] 
 **created_resources** | **str**| created_resources | [optional] 
 **finished_at** | **str**| finished_at | [optional] 
 **finished_at__gt** | **str**| finished_at__gt | [optional] 
 **finished_at__gte** | **str**| finished_at__gte | [optional] 
 **finished_at__lt** | **str**| finished_at__lt | [optional] 
 **finished_at__lte** | **str**| finished_at__lte | [optional] 
 **finished_at__range** | **str**| finished_at__range | [optional] 
 **limit** | **int**| Number of results to return per page. | [optional] 
 **name** | **str**| name | [optional] 
 **name__contains** | **str**| name__contains | [optional] 
 **offset** | **int**| The initial index from which to return the results. | [optional] 
 **ordering** | **str**| Which field to use when ordering the results. | [optional] 
 **parent_task** | **str**| parent_task | [optional] 
 **reserved_resources_record** | **str**| reserved_resources_record | [optional] 
 **started_at** | **str**| started_at | [optional] 
 **started_at__gt** | **str**| started_at__gt | [optional] 
 **started_at__gte** | **str**| started_at__gte | [optional] 
 **started_at__lt** | **str**| started_at__lt | [optional] 
 **started_at__lte** | **str**| started_at__lte | [optional] 
 **started_at__range** | **str**| started_at__range | [optional] 
 **state** | **str**| state | [optional] 
 **state__in** | **str**| state__in | [optional] 
 **task_group** | **str**| task_group | [optional] 
 **worker** | **str**| worker | [optional] 
 **worker__in** | **str**| worker__in | [optional] 
 **fields** | **str**| A list of fields to include in the response. | [optional] 
 **exclude_fields** | **str**| A list of fields to exclude from the response. | [optional] 

### Return type

[**InlineResponse2007**](InlineResponse2007.md)

### Authorization

[basicAuth](../README.md#basicAuth), [cookieAuth](../README.md#cookieAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** |  |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **partial_update**
> TaskResponse partial_update(task_href, patched_task_cancel, child_tasks=child_tasks, created_resources=created_resources, finished_at=finished_at, finished_at__gt=finished_at__gt, finished_at__gte=finished_at__gte, finished_at__lt=finished_at__lt, finished_at__lte=finished_at__lte, finished_at__range=finished_at__range, name=name, name__contains=name__contains, ordering=ordering, parent_task=parent_task, reserved_resources_record=reserved_resources_record, started_at=started_at, started_at__gt=started_at__gt, started_at__gte=started_at__gte, started_at__lt=started_at__lt, started_at__lte=started_at__lte, started_at__range=started_at__range, state=state, state__in=state__in, task_group=task_group, worker=worker, worker__in=worker__in)

Cancel a task

This operation cancels a task.

### Example

* Basic Authentication (basicAuth):
```python
from __future__ import print_function
import time
import pulpcore.client.pulpcore
from pulpcore.client.pulpcore.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:24817
# See configuration.py for a list of all supported configuration parameters.
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = pulpcore.client.pulpcore.Configuration(
    username = 'YOUR_USERNAME',
    password = 'YOUR_PASSWORD'
)

# Configure API key authorization: cookieAuth
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817",
    api_key = {
        'Session': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Session'] = 'Bearer'

# Enter a context with an instance of the API client
with pulpcore.client.pulpcore.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = pulpcore.client.pulpcore.TasksApi(api_client)
    task_href = 'task_href_example' # str | 
patched_task_cancel = pulpcore.client.pulpcore.PatchedTaskCancel() # PatchedTaskCancel | 
child_tasks = 'child_tasks_example' # str | child_tasks (optional)
created_resources = 'created_resources_example' # str | created_resources (optional)
finished_at = 'finished_at_example' # str | finished_at (optional)
finished_at__gt = 'finished_at__gt_example' # str | finished_at__gt (optional)
finished_at__gte = 'finished_at__gte_example' # str | finished_at__gte (optional)
finished_at__lt = 'finished_at__lt_example' # str | finished_at__lt (optional)
finished_at__lte = 'finished_at__lte_example' # str | finished_at__lte (optional)
finished_at__range = 'finished_at__range_example' # str | finished_at__range (optional)
name = 'name_example' # str | name (optional)
name__contains = 'name__contains_example' # str | name__contains (optional)
ordering = 'ordering_example' # str | Which field to use when ordering the results. (optional)
parent_task = 'parent_task_example' # str | parent_task (optional)
reserved_resources_record = 'reserved_resources_record_example' # str | reserved_resources_record (optional)
started_at = 'started_at_example' # str | started_at (optional)
started_at__gt = 'started_at__gt_example' # str | started_at__gt (optional)
started_at__gte = 'started_at__gte_example' # str | started_at__gte (optional)
started_at__lt = 'started_at__lt_example' # str | started_at__lt (optional)
started_at__lte = 'started_at__lte_example' # str | started_at__lte (optional)
started_at__range = 'started_at__range_example' # str | started_at__range (optional)
state = 'state_example' # str | state (optional)
state__in = 'state__in_example' # str | state__in (optional)
task_group = 'task_group_example' # str | task_group (optional)
worker = 'worker_example' # str | worker (optional)
worker__in = 'worker__in_example' # str | worker__in (optional)

    try:
        # Cancel a task
        api_response = api_instance.partial_update(task_href, patched_task_cancel, child_tasks=child_tasks, created_resources=created_resources, finished_at=finished_at, finished_at__gt=finished_at__gt, finished_at__gte=finished_at__gte, finished_at__lt=finished_at__lt, finished_at__lte=finished_at__lte, finished_at__range=finished_at__range, name=name, name__contains=name__contains, ordering=ordering, parent_task=parent_task, reserved_resources_record=reserved_resources_record, started_at=started_at, started_at__gt=started_at__gt, started_at__gte=started_at__gte, started_at__lt=started_at__lt, started_at__lte=started_at__lte, started_at__range=started_at__range, state=state, state__in=state__in, task_group=task_group, worker=worker, worker__in=worker__in)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling TasksApi->partial_update: %s\n" % e)
```

* Api Key Authentication (cookieAuth):
```python
from __future__ import print_function
import time
import pulpcore.client.pulpcore
from pulpcore.client.pulpcore.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:24817
# See configuration.py for a list of all supported configuration parameters.
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = pulpcore.client.pulpcore.Configuration(
    username = 'YOUR_USERNAME',
    password = 'YOUR_PASSWORD'
)

# Configure API key authorization: cookieAuth
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817",
    api_key = {
        'Session': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Session'] = 'Bearer'

# Enter a context with an instance of the API client
with pulpcore.client.pulpcore.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = pulpcore.client.pulpcore.TasksApi(api_client)
    task_href = 'task_href_example' # str | 
patched_task_cancel = pulpcore.client.pulpcore.PatchedTaskCancel() # PatchedTaskCancel | 
child_tasks = 'child_tasks_example' # str | child_tasks (optional)
created_resources = 'created_resources_example' # str | created_resources (optional)
finished_at = 'finished_at_example' # str | finished_at (optional)
finished_at__gt = 'finished_at__gt_example' # str | finished_at__gt (optional)
finished_at__gte = 'finished_at__gte_example' # str | finished_at__gte (optional)
finished_at__lt = 'finished_at__lt_example' # str | finished_at__lt (optional)
finished_at__lte = 'finished_at__lte_example' # str | finished_at__lte (optional)
finished_at__range = 'finished_at__range_example' # str | finished_at__range (optional)
name = 'name_example' # str | name (optional)
name__contains = 'name__contains_example' # str | name__contains (optional)
ordering = 'ordering_example' # str | Which field to use when ordering the results. (optional)
parent_task = 'parent_task_example' # str | parent_task (optional)
reserved_resources_record = 'reserved_resources_record_example' # str | reserved_resources_record (optional)
started_at = 'started_at_example' # str | started_at (optional)
started_at__gt = 'started_at__gt_example' # str | started_at__gt (optional)
started_at__gte = 'started_at__gte_example' # str | started_at__gte (optional)
started_at__lt = 'started_at__lt_example' # str | started_at__lt (optional)
started_at__lte = 'started_at__lte_example' # str | started_at__lte (optional)
started_at__range = 'started_at__range_example' # str | started_at__range (optional)
state = 'state_example' # str | state (optional)
state__in = 'state__in_example' # str | state__in (optional)
task_group = 'task_group_example' # str | task_group (optional)
worker = 'worker_example' # str | worker (optional)
worker__in = 'worker__in_example' # str | worker__in (optional)

    try:
        # Cancel a task
        api_response = api_instance.partial_update(task_href, patched_task_cancel, child_tasks=child_tasks, created_resources=created_resources, finished_at=finished_at, finished_at__gt=finished_at__gt, finished_at__gte=finished_at__gte, finished_at__lt=finished_at__lt, finished_at__lte=finished_at__lte, finished_at__range=finished_at__range, name=name, name__contains=name__contains, ordering=ordering, parent_task=parent_task, reserved_resources_record=reserved_resources_record, started_at=started_at, started_at__gt=started_at__gt, started_at__gte=started_at__gte, started_at__lt=started_at__lt, started_at__lte=started_at__lte, started_at__range=started_at__range, state=state, state__in=state__in, task_group=task_group, worker=worker, worker__in=worker__in)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling TasksApi->partial_update: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **task_href** | **str**|  | 
 **patched_task_cancel** | [**PatchedTaskCancel**](PatchedTaskCancel.md)|  | 
 **child_tasks** | **str**| child_tasks | [optional] 
 **created_resources** | **str**| created_resources | [optional] 
 **finished_at** | **str**| finished_at | [optional] 
 **finished_at__gt** | **str**| finished_at__gt | [optional] 
 **finished_at__gte** | **str**| finished_at__gte | [optional] 
 **finished_at__lt** | **str**| finished_at__lt | [optional] 
 **finished_at__lte** | **str**| finished_at__lte | [optional] 
 **finished_at__range** | **str**| finished_at__range | [optional] 
 **name** | **str**| name | [optional] 
 **name__contains** | **str**| name__contains | [optional] 
 **ordering** | **str**| Which field to use when ordering the results. | [optional] 
 **parent_task** | **str**| parent_task | [optional] 
 **reserved_resources_record** | **str**| reserved_resources_record | [optional] 
 **started_at** | **str**| started_at | [optional] 
 **started_at__gt** | **str**| started_at__gt | [optional] 
 **started_at__gte** | **str**| started_at__gte | [optional] 
 **started_at__lt** | **str**| started_at__lt | [optional] 
 **started_at__lte** | **str**| started_at__lte | [optional] 
 **started_at__range** | **str**| started_at__range | [optional] 
 **state** | **str**| state | [optional] 
 **state__in** | **str**| state__in | [optional] 
 **task_group** | **str**| task_group | [optional] 
 **worker** | **str**| worker | [optional] 
 **worker__in** | **str**| worker__in | [optional] 

### Return type

[**TaskResponse**](TaskResponse.md)

### Authorization

[basicAuth](../README.md#basicAuth), [cookieAuth](../README.md#cookieAuth)

### HTTP request headers

 - **Content-Type**: application/json, application/x-www-form-urlencoded, multipart/form-data
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** |  |  -  |
**409** |  |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **read**
> TaskResponse read(task_href, fields=fields, exclude_fields=exclude_fields)



A customized named ModelViewSet that knows how to register itself with the Pulp API router.  This viewset is discoverable by its name. \"Normal\" Django Models and Master/Detail models are supported by the ``register_with`` method.  Attributes:     lookup_field (str): The name of the field by which an object should be looked up, in         addition to any parent lookups if this ViewSet is nested. Defaults to 'pk'     endpoint_name (str): The name of the final path segment that should identify the ViewSet's         collection endpoint.     nest_prefix (str): Optional prefix under which this ViewSet should be nested. This must         correspond to the \"parent_prefix\" of a router with rest_framework_nested.NestedMixin.         None indicates this ViewSet should not be nested.     parent_lookup_kwargs (dict): Optional mapping of key names that would appear in self.kwargs         to django model filter expressions that can be used with the corresponding value from         self.kwargs, used only by a nested ViewSet to filter based on the parent object's         identity.     schema (DefaultSchema): The schema class to use by default in a viewset.

### Example

* Basic Authentication (basicAuth):
```python
from __future__ import print_function
import time
import pulpcore.client.pulpcore
from pulpcore.client.pulpcore.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:24817
# See configuration.py for a list of all supported configuration parameters.
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = pulpcore.client.pulpcore.Configuration(
    username = 'YOUR_USERNAME',
    password = 'YOUR_PASSWORD'
)

# Configure API key authorization: cookieAuth
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817",
    api_key = {
        'Session': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Session'] = 'Bearer'

# Enter a context with an instance of the API client
with pulpcore.client.pulpcore.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = pulpcore.client.pulpcore.TasksApi(api_client)
    task_href = 'task_href_example' # str | 
fields = 'fields_example' # str | A list of fields to include in the response. (optional)
exclude_fields = 'exclude_fields_example' # str | A list of fields to exclude from the response. (optional)

    try:
        api_response = api_instance.read(task_href, fields=fields, exclude_fields=exclude_fields)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling TasksApi->read: %s\n" % e)
```

* Api Key Authentication (cookieAuth):
```python
from __future__ import print_function
import time
import pulpcore.client.pulpcore
from pulpcore.client.pulpcore.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:24817
# See configuration.py for a list of all supported configuration parameters.
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = pulpcore.client.pulpcore.Configuration(
    username = 'YOUR_USERNAME',
    password = 'YOUR_PASSWORD'
)

# Configure API key authorization: cookieAuth
configuration = pulpcore.client.pulpcore.Configuration(
    host = "http://localhost:24817",
    api_key = {
        'Session': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Session'] = 'Bearer'

# Enter a context with an instance of the API client
with pulpcore.client.pulpcore.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = pulpcore.client.pulpcore.TasksApi(api_client)
    task_href = 'task_href_example' # str | 
fields = 'fields_example' # str | A list of fields to include in the response. (optional)
exclude_fields = 'exclude_fields_example' # str | A list of fields to exclude from the response. (optional)

    try:
        api_response = api_instance.read(task_href, fields=fields, exclude_fields=exclude_fields)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling TasksApi->read: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **task_href** | **str**|  | 
 **fields** | **str**| A list of fields to include in the response. | [optional] 
 **exclude_fields** | **str**| A list of fields to exclude from the response. | [optional] 

### Return type

[**TaskResponse**](TaskResponse.md)

### Authorization

[basicAuth](../README.md#basicAuth), [cookieAuth](../README.md#cookieAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** |  |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

