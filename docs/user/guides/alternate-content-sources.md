# Alternate Content Sources (ACS)

Alternate Content Sources (ACS) in Pulp allow you to specify additional locations where content can be fetched. The primary purpose of using ACS is to fetch binary content from a location that is **latency or bandwidth closer** to your Pulp system than the original remote sources you are syncing from.

### How ACS Works

When you want to use multiple mirror source servers as alternate locations for content, you do not define multiple URLs directly within a single ACS object. Instead, you will need to:

1.  Create a **Remote** object.
2.  Create a separate **Alternate Content Source object**.

For each hostname or server you want to use as an alternate source, create a remote and associated Alternate Content Source object.

The ACS object creation process does not accept full URLs, it only exposes the capability of specifying 'paths'. This 'paths' part is a convenience feature. It is **optional**. It is primarily used in situations where the remote server has multiple repositories available at different paths, and you wish to reference these paths without defining a separate ACS object for each path.

### Content Preference

Content provided by an Alternate Content Source is considered **preferred** over any content provided by a non-ACS source for any sync operation or on-demand download. This preference for ACS applies whenever Pulp needs to fetch binary data remotely.

If the same content is available from multiple configured ACS sources, Pulp will **randomly select** one of these sources to fetch the content from.

The preference for Alternate Content Sources is active **within the domain** they are created in. They will be preferred for syncs or on-demand fetching operations occurring within that specific domain, but they will be ignored for operations in other domains.

### Refreshing ACS

An Alternate Content Source object has a "refresh" operation, which needs to be done prior to being used. This operation performs a sync which indexes the remote source that is referred to by its associated Remote object. The **refresh operation does not actually sync any binary data**. The binary data itself is not known by Pulp and is only brought into the Pulp system **as needed** during other sync operations or when content is downloaded on-demand within that domain.

### Common Use Cases

Some common situations where Alternate Content Sources are useful include:

*   Having a local disk mounted on your Pulp server that contains RPM repositories.
*   Rebuilding one Pulp server from another, where one acts as a source for content.
