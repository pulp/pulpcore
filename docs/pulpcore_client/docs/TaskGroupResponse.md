# TaskGroupResponse

Base serializer for use with :class:`pulpcore.app.models.Model`  This ensures that all Serializers provide values for the 'pulp_href` field.  The class provides a default for the ``ref_name`` attribute in the ModelSerializers's ``Meta`` class. This ensures that the OpenAPI definitions of plugins are namespaced properly.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**pulp_href** | **str** |  | [optional] [readonly] 
**description** | **str** | A description of the task group. | 
**all_tasks_dispatched** | **bool** | Whether all tasks have been spawned for this task group. | 
**waiting** | **int** | Number of tasks in the &#39;waiting&#39; state | [optional] [readonly] 
**skipped** | **int** | Number of tasks in the &#39;skipped&#39; state | [optional] [readonly] 
**running** | **int** | Number of tasks in the &#39;running&#39; state | [optional] [readonly] 
**completed** | **int** | Number of tasks in the &#39;completed&#39; state | [optional] [readonly] 
**canceled** | **int** | Number of tasks in the &#39;canceled&#39; state | [optional] [readonly] 
**failed** | **int** | Number of tasks in the &#39;failed&#39; state | [optional] [readonly] 
**group_progress_reports** | [**list[GroupProgressReportResponse]**](GroupProgressReportResponse.md) |  | [optional] [readonly] 

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


