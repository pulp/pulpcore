Added ``pulpcore.plugin.viewset.TaskGroupResponse`` which can be used to return a reference to a
task group created in a viewset. Added ``pulpcore.plugin.serializers.TaskGroupResponseSerializer``
which can be used to indicate the serializer response format of viewsets that will use
``TaskGroupResponse`` similar to how ``AsyncOperationResponseSerializer`` is used.
