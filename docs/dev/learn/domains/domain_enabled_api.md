# Creating Domain-Enabled APIs

This document outlines the components and patterns needed to create a domain-enabled API in the Pulp platform

## 1. Model Configuration

### Steps

- Inherit from `BaseModel` to get standard Pulp fields and behaviors
- Include a `pulp_domain` foreign key field to associate records with specific domains

### Example Implementation

```python
from pulpcore.plugin.models import BaseModel, Domain
from pulpcore.app.util import get_domain_pk

class YourDomainEnabledModel(BaseModel):
    # Your model-specific fields
    some_field = models.TextField()
    data = models.JSONField()
    
    # Domain relationship - this is the key component for domain enablement
    pulp_domain = models.ForeignKey("core.Domain", default=get_domain_pk, on_delete=models.CASCADE)
    
    def __str__(self):
        return f"Your Model {self.pulp_id}"
```

## 2. Serializer Configuration

### Instructions

- Inherit from `ModelSerializer` to get standard Pulp serialization behavior
- Include an `IdentityField` for proper HREF generation
- Include all model fields that should be exposed in the API

### Example Implementation

```python
from pulpcore.plugin.serializers import IdentityField
from rest_framework import serializers
from pulpcore.plugin.serializers import ModelSerializer

class YourModelSerializer(ModelSerializer):
    pulp_href = IdentityField(view_name="your-endpoint-name-detail")
    # Include serializer fields corresponding to your model fields
    some_field = serializers.CharField()
    data = serializers.JSONField()
    
    class Meta:
        model = YourDomainEnabledModel
        fields = ModelSerializer.Meta.fields + ('some_field', 'data')
```

## 3. ViewSet Configuration

### Instructions

- Inherit from `NamedModelViewSet` for correct Pulp behavior (routing, permissions, domain scoping)
- Include mixins for specific operations (ListModelMixin, RetrieveModelMixin, etc.)
- Set `endpoint_name` for API URL generation
- Set `queryset` and `serializer_class`
- Implement custom methods as needed (create, list, etc.)

### Out-of-the-Box Functionality with Mixins

By including the standard Django REST Framework mixins, you get working endpoints without writing additional code:

- **ListModelMixin**: Automatically implements the `.list()` method, handling GET requests to the collection endpoint (`/pulp/{domain}/api/v3/your-endpoint-name/`). This provides:
    - Automatic pagination
    - Domain-aware filtering (objects only from the current domain)
    - Serialization of results using your serializer class

- **RetrieveModelMixin**: Automatically implements the `.retrieve()` method, handling GET requests to detail endpoints (`/pulp/{domain}/api/v3/your-endpoint-name/{uuid}/`). This provides:
    - Automatic lookup by UUID (pulp_id)
    - Domain-aware object retrieval
    - 404 responses for objects that don't exist or are in other domains

Simply by including these mixins and setting up the proper `queryset` and `serializer_class`, your API gains functional list and detail views with proper domain isolation.

### Example Implementation

```python
from pulpcore.app.viewsets import NamedModelViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.plugin.tasking import dispatch

class YourModelViewSet(NamedModelViewSet, ListModelMixin, RetrieveModelMixin):
    endpoint_name = 'your-endpoint-name'
    queryset = YourDomainEnabledModel.objects.all()
    serializer_class = YourModelSerializer
    
    # No need to implement list() or retrieve() - they're provided by the mixins!
    
    def create(self, request):
        # Implement your creation logic
        serializer = YourCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # For async operations
        task = dispatch(your_async_task, kwargs={
            'param1': serializer.validated_data['param1']
        })
        
        return OperationPostponedResponse(task, request)
```

## 4. Task Implementation (For Async Operations)

For domain-enabled APIs that need async operations:

```python
def your_async_task(self, param1):
    """
    Process data asynchronously.
    
    Args:
        param1: Data from the API request
        
    Returns:
        Dictionary of results
    """
    # Your task implementation
    # Domain context is automatically handled by Pulp task system
    # Use util method `get_domain` to get the current domain in the running Task
    
    # Create the model instance
    model_instance = YourDomainEnabledModel.objects.create(
        some_field="value",
        data={"processed": True}
    )
    
    return model_instance.pk
```

## 5. URL Registration

With `NamedModelViewSet`, URL registration happens automatically:

- No manual URL configuration is needed
- The `endpoint_name` property in your ViewSet determines the URL path
- URLs are registered automatically when Pulp starts up

For example, a ViewSet with `endpoint_name = 'your-endpoint-name'` will automatically be available at:

- `GET /pulp/{domain-name}/api/v3/your-endpoint-name/` (list endpoint)
- `GET /pulp/{domain-name}/api/v3/your-endpoint-name/{uuid}/` (detail endpoint)
- Other HTTP methods as defined by your included mixins

This automatic URL registration is a key advantage of using the Pulp platform and `NamedModelViewSet`.

```python
# No manual URL registration needed - this happens automatically
class YourModelViewSet(NamedModelViewSet, ListModelMixin, RetrieveModelMixin):
    endpoint_name = 'your-endpoint-name'  # This defines the URL path
    queryset = YourDomainEnabledModel.objects.all()
    serializer_class = YourModelSerializer
```

## Key Considerations

1. **Domain Filtering**: The `pulp_domain` foreign key enables automatic domain filtering in the Pulp platform
2. **Permissions**: Consider domain-specific permissions if needed
3. **Serialization**: Ensure proper serialization of domain-specific data
4. **Task Dispatching**: Use the Pulp task system for async operations

## Complete Example: 

The implementation demonstrates these patterns:

- **Model**: Has `pulp_domain` field to associate reports with domains
- **Serializer**: Exposes domain-specific fields and proper HREF generation
- **ViewSet**: Provides domain-aware CRUD operations
- **Task**: Handles async processing while maintaining domain context

By following these patterns, you can create domain-enabled APIs that properly isolate data between domains while leveraging Pulp's powerful features for API management and asynchronous task handling.
