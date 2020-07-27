# PulpExporterResponse

Serializer for pulp exporters.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**pulp_href** | **str** |  | [optional] [readonly] 
**pulp_created** | **datetime** | Timestamp of creation. | [optional] [readonly] 
**name** | **str** | Unique name of the file system exporter. | 
**path** | **str** | File system directory to store exported tar.gzs. | 
**repositories** | **list[str]** |  | 
**last_export** | **str** | Last attempted export for this PulpExporter | [optional] 

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


