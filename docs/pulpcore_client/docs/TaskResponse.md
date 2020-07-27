# TaskResponse

Base serializer for use with :class:`pulpcore.app.models.Model`  This ensures that all Serializers provide values for the 'pulp_href` field.  The class provides a default for the ``ref_name`` attribute in the ModelSerializers's ``Meta`` class. This ensures that the OpenAPI definitions of plugins are namespaced properly.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**pulp_href** | **str** |  | [optional] [readonly] 
**pulp_created** | **datetime** | Timestamp of creation. | [optional] [readonly] 
**state** | **str** | The current state of the task. The possible values include: &#39;waiting&#39;, &#39;skipped&#39;, &#39;running&#39;, &#39;completed&#39;, &#39;failed&#39; and &#39;canceled&#39;. | [optional] [readonly] 
**name** | **str** | The name of task. | 
**started_at** | **datetime** | Timestamp of the when this task started execution. | [optional] [readonly] 
**finished_at** | **datetime** | Timestamp of the when this task stopped execution. | [optional] [readonly] 
**error** | [**object**](.md) | A JSON Object of a fatal error encountered during the execution of this task. | [optional] [readonly] 
**worker** | **str** | The worker associated with this task. This field is empty if a worker is not yet assigned. | [optional] [readonly] 
**parent_task** | **str** | The parent task that spawned this task. | [optional] [readonly] 
**child_tasks** | **list[str]** | Any tasks spawned by this task. | [optional] [readonly] 
**task_group** | **str** | The task group that this task is a member of. | [optional] [readonly] 
**progress_reports** | [**list[ProgressReportResponse]**](ProgressReportResponse.md) |  | [optional] [readonly] 
**created_resources** | **list[str]** | Resources created by this task. | [optional] [readonly] 

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


