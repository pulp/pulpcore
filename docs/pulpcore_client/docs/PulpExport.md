# PulpExport

Serializer for PulpExports.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**task** | **str** | A URI of the task that ran the Export. | [optional] 
**full** | **bool** | Do a Full (true) or Incremental (false) export. | [optional] [default to True]
**dry_run** | **bool** | Generate report on what would be exported and disk-space required. | [optional] [default to False]
**versions** | **list[str]** | List of explicit repo-version hrefs to export (replaces current_version). | [optional] 
**chunk_size** | **str** | Chunk export-tarfile into pieces of chunk_size bytes.Recognizes units of B/KB/MB/GB/TB. | [optional] 
**start_versions** | **list[str]** | List of explicit last-exported-repo-version hrefs (replaces last_export). | [optional] 

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


