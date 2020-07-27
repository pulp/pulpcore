# PulpExportResponse

Serializer for PulpExports.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**pulp_href** | **str** |  | [optional] [readonly] 
**pulp_created** | **datetime** | Timestamp of creation. | [optional] [readonly] 
**task** | **str** | A URI of the task that ran the Export. | [optional] 
**exported_resources** | **list[object]** | Resources that were exported. | [optional] [readonly] 
**params** | [**object**](.md) | Any additional parameters that were used to create the export. | [optional] [readonly] 
**output_file_info** | [**object**](.md) | Dictionary of filename: sha256hash entries for export-output-file(s) | [optional] [readonly] 

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


