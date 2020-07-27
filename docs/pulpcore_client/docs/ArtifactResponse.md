# ArtifactResponse

Base serializer for use with :class:`pulpcore.app.models.Model`  This ensures that all Serializers provide values for the 'pulp_href` field.  The class provides a default for the ``ref_name`` attribute in the ModelSerializers's ``Meta`` class. This ensures that the OpenAPI definitions of plugins are namespaced properly.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**pulp_href** | **str** |  | [optional] [readonly] 
**pulp_created** | **datetime** | Timestamp of creation. | [optional] [readonly] 
**file** | **str** | The stored file. | 
**size** | **int** | The size of the file in bytes. | [optional] 
**md5** | **str** | The MD5 checksum of the file if available. | [optional] 
**sha1** | **str** | The SHA-1 checksum of the file if available. | [optional] 
**sha224** | **str** | The SHA-224 checksum of the file if available. | [optional] 
**sha256** | **str** | The SHA-256 checksum of the file if available. | [optional] 
**sha384** | **str** | The SHA-384 checksum of the file if available. | [optional] 
**sha512** | **str** | The SHA-512 checksum of the file if available. | [optional] 

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


