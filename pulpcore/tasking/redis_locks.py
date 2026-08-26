"""
Redis distributed lock utilities for task resource coordination.

This module provides functions and Lua scripts for managing exclusive and shared
resource locks using Redis.
"""

import logging

import redis
from asgiref.sync import sync_to_async

from pulpcore.app.redis_connection import get_redis_connection

_logger = logging.getLogger(__name__)

# Redis key prefix for resource locks
REDIS_LOCK_PREFIX = "pulp:resource_lock:"

# Redis key prefix for the per-owner lock registry. Each owner has a SET listing the
# lock keys it currently holds so cleanup is O(locks held by owner), not O(all locks).
REDIS_OWNER_REGISTRY_PREFIX = "pulp:owner_locks:"

# Redis SET of owner names holding at least one lock. SMEMBERS here is O(#owners),
# avoiding a full-keyspace SCAN. Added by the acquire script; removed only by the cleanup
# path (REDIS_CLEANUP_OWNER_LOCKS_SCRIPT / cleanup_locks_for_owner) -- the release script
# deliberately does NOT (see there). These paths hardcode this literal; keep it matching.
ACTIVE_OWNERS_KEY = "pulp:active_owners"

# Throttle key + interval (seconds) for the legacy full-keyspace SCAN fallback used
# during rolling upgrades (locks acquired before the registry existed).
LEGACY_OWNER_SCAN_KEY = "pulp:last_legacy_owner_scan"
LEGACY_OWNER_SCAN_INTERVAL = 900  # ~15 min, fleet-wide

# Owner name prefix used by safe_release_task_locks for immediate tasks that run in an
# API process without an AppStatus. These owners never have an AppStatus row.
IMMEDIATE_OWNER_PREFIX = "immediate-"

REDIS_ACQUIRE_LOCKS_SCRIPT = """
-- KEYS[1]: task_lock_key
-- KEYS[2...]: exclusive_lock_keys, then shared_lock_keys
-- ARGV[1]: lock_owner (worker name)
-- ARGV[2]: number of exclusive resources
-- ARGV[3...]: exclusive resource names, then shared resource names (for error reporting)
-- Returns: empty table if success, table of blocked resource names if failed

local task_lock_key = KEYS[1]
local lock_owner = ARGV[1]
local num_exclusive = tonumber(ARGV[2])
local blocked_resources = {}
local owner_registry_key = "pulp:owner_locks:" .. lock_owner

-- Check task lock first (fail fast)
if redis.call("exists", task_lock_key) == 1 then
    table.insert(blocked_resources, "__task_lock__")
    return blocked_resources
end

-- Check exclusive resource locks
-- Resource keys start at KEYS[2]
for i = 1, num_exclusive do
    local key = KEYS[1 + i]
    local resource_name = ARGV[2 + i]

    -- Check if lock exists
    if redis.call("exists", key) == 1 then
        -- Lock already held, add to blocked list
        table.insert(blocked_resources, resource_name)
    end
end

-- If any exclusive locks were blocked, don't proceed
if #blocked_resources > 0 then
    return blocked_resources
end

-- Check shared resources - ensure no exclusive locks exist
-- Shared resource keys start at KEYS[2 + num_exclusive]
for i = num_exclusive + 1, #KEYS - 1 do
    local key = KEYS[1 + i]
    local shared_resource_name = ARGV[2 + i]

    -- Check if there's an exclusive lock (string value)
    local lock_type = redis.call("type", key)
    if lock_type["ok"] == "string" then
        -- Exclusive lock exists on a shared resource we need
        table.insert(blocked_resources, shared_resource_name)
    end
end

-- If any shared resources are blocked by exclusive locks, fail
if #blocked_resources > 0 then
    return blocked_resources
end

-- All checks passed, acquire ALL locks atomically
-- Acquire task lock (no expiration - will be deleted explicitly on completion)
redis.call("set", task_lock_key, lock_owner)

-- Acquire exclusive resource locks
for i = 1, num_exclusive do
    local key = KEYS[1 + i]
    redis.call("set", key, lock_owner)
end

-- Acquire shared resource locks
for i = num_exclusive + 1, #KEYS - 1 do
    local key = KEYS[1 + i]
    redis.call("sadd", key, lock_owner)
end

-- Register every held lock key under the owner registry (atomic with acquisition).
-- This lets cleanup enumerate an owner's locks without scanning the whole keyspace.
-- One variadic SADD: all of KEYS are held lock keys (task lock + resource locks).
redis.call("sadd", owner_registry_key, unpack(KEYS))

-- Track this owner in the global active-owners set so reconcile can enumerate
-- lock owners with SMEMBERS instead of a full-keyspace SCAN.
redis.call("sadd", "pulp:active_owners", lock_owner)

-- Return empty table to indicate success
return {}
"""

REDIS_RELEASE_LOCKS_SCRIPT = """
-- KEYS[1]: task_lock_key
-- KEYS[2...]: exclusive_lock_keys, shared_lock_keys
-- ARGV[1]: lock_owner
-- ARGV[2]: number of exclusive resources
-- ARGV[3...]: resource names for error reporting
-- Returns: {not_owned_exclusive, not_in_shared, task_lock_not_owned}

local task_lock_key = KEYS[1]
local lock_owner = ARGV[1]
local num_exclusive = tonumber(ARGV[2])
local not_owned_exclusive = {}
local not_in_shared = {}
local task_lock_not_owned = false
local owner_registry_key = "pulp:owner_locks:" .. lock_owner

-- Release exclusive locks
-- Resource keys start at KEYS[2]
for i = 1, num_exclusive do
    local key = KEYS[1 + i]
    local resource_name = ARGV[2 + i]

    -- Check if we own the lock
    local current_owner = redis.call("get", key)
    if current_owner == lock_owner then
        redis.call("del", key)
        redis.call("srem", owner_registry_key, key)
    elseif current_owner ~= false then
        -- Lock exists but we don't own it
        table.insert(not_owned_exclusive, resource_name)
    end
    -- If current_owner is false (nil), lock doesn't exist - already released
end

-- Release shared locks
-- Shared keys start at KEYS[2 + num_exclusive]
-- INVARIANT: an owner runs one task at a time (see RedisWorker.handle_tasks), so it
-- never holds the same shared resource for two concurrent tasks. That lets us drop
-- the registry entry on release unconditionally. If workers ever become concurrent,
-- this must become reference-counted or the shared lock could be released early.
for i = num_exclusive + 1, #KEYS - 1 do
    local key = KEYS[1 + i]
    local resource_name = ARGV[2 + i]

    -- Remove from set
    local removed = redis.call("srem", key, lock_owner)
    -- No longer a member, so drop the registry entry for this shared key.
    redis.call("srem", owner_registry_key, key)
    if removed == 0 then
        -- We weren't in the set
        table.insert(not_in_shared, resource_name)
    end
end

-- Release task lock
local task_lock_owner = redis.call("get", task_lock_key)
if task_lock_owner == lock_owner then
    redis.call("del", task_lock_key)
    redis.call("srem", owner_registry_key, task_lock_key)
elseif task_lock_owner ~= false then
    -- Task lock exists but we don't own it
    task_lock_not_owned = true
end

-- Do NOT remove lock_owner from "pulp:active_owners" here, even if its registry is now
-- empty: that opens a release->next-acquire gap where reconcile_orphan_redis_locks would
-- miss the owner. A live worker holding zero locks is harmless (reconcile only cleans
-- owners with no AppStatus row); owners leave active_owners only during cleanup.

return {not_owned_exclusive, not_in_shared, task_lock_not_owned}
"""


REDIS_CLEANUP_OWNER_LOCKS_SCRIPT = """
-- Release every lock held by an owner via the per-owner registry set. Each entry is
-- removed individually (not a wholesale registry delete); a key of an unexpected type is
-- left in place and reported as skipped so it is not silently orphaned.
-- ARGV[1]: lock_owner
-- Returns: {released, skipped_keys} (skipped = registry entries with an unexpected type)
local lock_owner = ARGV[1]
local owner_registry_key = "pulp:owner_locks:" .. lock_owner
local keys = redis.call("smembers", owner_registry_key)
local released = 0
local skipped_keys = {}

for _, key in ipairs(keys) do
    local key_type = redis.call("type", key)["ok"]
    if key_type == "string" then
        if redis.call("get", key) == lock_owner then
            -- Still ours: release and stop tracking.
            redis.call("del", key)
            redis.call("srem", owner_registry_key, key)
            released = released + 1
        else
            -- Not ours (successor re-took the name): stop tracking, leave the lock.
            redis.call("srem", owner_registry_key, key)
        end
    elseif key_type == "set" then
        -- srem; the set auto-deletes once its last member leaves.
        released = released + redis.call("srem", key, lock_owner)
        redis.call("srem", owner_registry_key, key)
    elseif key_type == "none" then
        -- Stale entry: lock already gone.
        redis.call("srem", owner_registry_key, key)
    else
        -- Unexpected type: leave it and keep tracking (reported by name, not orphaned).
        skipped_keys[#skipped_keys + 1] = key
    end
end

-- Forget the owner only once its registry is empty; skipped keys keep it enumerable.
if redis.call("scard", owner_registry_key) == 0 then
    redis.call("srem", "pulp:active_owners", lock_owner)
end

return {released, skipped_keys}
"""


REDIS_DELETE_STRING_IF_OWNER_SCRIPT = """
-- Atomically delete a string lock only if it is owned by lock_owner.
-- KEYS[1]: lock key
-- ARGV[1]: lock_owner
-- ARGV[2]: owner_registry_key
if redis.call("get", KEYS[1]) == ARGV[1] then
    redis.call("del", KEYS[1])
    redis.call("srem", ARGV[2], KEYS[1])
    return 1
end
return 0
"""


REDIS_SREM_OWNER_SCRIPT = """
-- Atomically remove lock_owner from a shared set (auto-deletes when empty).
-- KEYS[1]: shared set key
-- ARGV[1]: lock_owner
-- ARGV[2]: owner_registry_key
local removed = redis.call("srem", KEYS[1], ARGV[1])
redis.call("srem", ARGV[2], KEYS[1])
return removed
"""


def resource_to_lock_key(resource_name):
    """
    Convert a resource name to a Redis lock key.

    Args:
        resource_name (str): The resource name (e.g., "prn:rpm.repository:abc123")

    Returns:
        str: A Redis key for the resource lock
    """
    return f"{REDIS_LOCK_PREFIX}{resource_name}"


def get_task_lock_key(task_id):
    """
    Get the Redis lock key for a task.

    Args:
        task_id: The task ID (task.pk or UUID string)

    Returns:
        str: A Redis key for the task lock
    """
    return f"task:{task_id}"


def get_owner_registry_key(owner):
    """Return the Redis key for an owner's lock registry SET."""
    return f"{REDIS_OWNER_REGISTRY_PREFIX}{owner}"


def _decode(value):
    """Decode a redis bytes value to str (redis-py returns bytes by default)."""
    return value.decode() if isinstance(value, bytes) else value


def _legacy_scan_cleanup_for_owner(redis_conn, owner):
    """
    Release an owner's locks by scanning the keyspace (no registry available).

    Used only for locks acquired before the per-owner registry existed (rolling
    upgrade). Uses SCAN (never KEYS) and atomic per-key Lua so a concurrent worker
    that re-took a key by the same name is not clobbered.

    Returns:
        int: Number of locks released (best effort).
    """
    registry_key = get_owner_registry_key(owner)
    delete_if_owner = redis_conn.register_script(REDIS_DELETE_STRING_IF_OWNER_SCRIPT)
    srem_owner = redis_conn.register_script(REDIS_SREM_OWNER_SCRIPT)
    released = 0

    for key in redis_conn.scan_iter(match="task:*", count=500):
        if _decode(redis_conn.get(key)) == owner:
            released += delete_if_owner(keys=[key], args=[owner, registry_key])

    for key in redis_conn.scan_iter(match=f"{REDIS_LOCK_PREFIX}*", count=500):
        if _decode(redis_conn.type(key)) == "string":
            if _decode(redis_conn.get(key)) == owner:
                released += delete_if_owner(keys=[key], args=[owner, registry_key])
        else:
            released += srem_owner(keys=[key], args=[owner, registry_key])

    redis_conn.delete(registry_key)
    redis_conn.srem(ACTIVE_OWNERS_KEY, owner)
    return released


def cleanup_locks_for_owner(redis_conn, owner, allow_legacy_scan=False):
    """
    Release all Redis locks held by `owner`.

    Prefers the per-owner registry (O(locks held by owner)). Falls back to a legacy
    keyspace SCAN only when the registry is missing and `allow_legacy_scan` is set.

    Args:
        redis_conn: Redis connection
        owner (str): The lock owner (worker name or `immediate-{task_pk}`)
        allow_legacy_scan (bool): Permit the legacy SCAN fallback for pre-registry locks

    Returns:
        bool: True if cleanup completed (including a no-op), False on error so the
            caller can retain state and retry on a later pass.
    """
    registry_key = get_owner_registry_key(owner)
    try:
        released = 0
        skipped_keys = []
        if redis_conn.exists(registry_key):
            cleanup_script = redis_conn.register_script(REDIS_CLEANUP_OWNER_LOCKS_SCRIPT)
            released, skipped_keys = cleanup_script(keys=[], args=[owner])
        elif allow_legacy_scan:
            released = _legacy_scan_cleanup_for_owner(redis_conn, owner)
        else:
            # No registry and no scan: nothing to release, but drop any stale
            # active-owners marker so reconcile stops re-visiting this owner.
            redis_conn.srem(ACTIVE_OWNERS_KEY, owner)
        if released:
            _logger.info("Reclaimed %d Redis lock(s) held by owner %s", released, owner)
        if skipped_keys:
            _logger.warning(
                "Left %d unexpected registry entr(y/ies) for owner %s in place for a "
                "later cleanup pass: %s",
                len(skipped_keys),
                owner,
                ", ".join(_decode(key) for key in skipped_keys),
            )
        return True
    except Exception as e:
        _logger.error("Error cleaning up Redis locks for owner %s: %s", owner, e)
        return False


def collect_lock_owners(redis_conn, allow_legacy_scan=False):
    """
    Return the set of owner names that currently hold Redis locks.

    Owners are read from the global active-owners SET via SMEMBERS -- O(#owners) and
    scan-free (a SCAN with MATCH still walks the whole keyspace, so scanning for
    registry keys would be O(all locks)). The legacy SCAN of the full `task:*` /
    `pulp:resource_lock:*` keyspace is expensive and is only run when
    `allow_legacy_scan` is set (throttled by the caller) to catch pre-registry locks.

    Args:
        redis_conn: Redis connection
        allow_legacy_scan (bool): Also discover owners of pre-registry (legacy) locks

    Returns:
        set: Owner names holding at least one lock.
    """
    owners = {_decode(member) for member in redis_conn.smembers(ACTIVE_OWNERS_KEY)}

    if allow_legacy_scan:
        for key in redis_conn.scan_iter(match="task:*", count=500):
            value = redis_conn.get(key)
            if value:
                owners.add(_decode(value))
        for key in redis_conn.scan_iter(match=f"{REDIS_LOCK_PREFIX}*", count=500):
            if _decode(redis_conn.type(key)) == "string":
                value = redis_conn.get(key)
                if value:
                    owners.add(_decode(value))
            else:
                for member in redis_conn.smembers(key):
                    owners.add(_decode(member))

    return owners


def extract_task_resources(task):
    """
    Extract exclusive and shared resources from a task.

    Args:
        task: Task object with reserved_resources_record field

    Returns:
        tuple: (exclusive_resources, shared_resources)
            exclusive_resources: List of exclusive resource names
            shared_resources: List of shared resource names (with "shared:" prefix stripped)
    """
    reserved_resources_record = task.reserved_resources_record or []

    exclusive_resources = [
        resource for resource in reserved_resources_record if not resource.startswith("shared:")
    ]

    shared_resources = [
        resource[7:]  # Remove "shared:" prefix
        for resource in reserved_resources_record
        if resource.startswith("shared:")
    ]

    return exclusive_resources, shared_resources


def safe_release_task_locks(task, lock_owner=None):
    """
    Safely release all locks for a task with idempotency check.

    This function:
    1. Checks if locks have already been released (idempotent)
    2. Extracts resources from task.reserved_resources_record
    3. Determines lock owner (from AppStatus or task-specific identifier)
    4. Releases task lock and all resource locks atomically
    5. Marks locks as released to prevent double-release

    Args:
        task: The Task object to release locks for
        lock_owner: Optional lock owner identifier. If not provided, will use
            AppStatus.objects.current() or fall back to f"immediate-{task.pk}"

    Returns:
        bool: True if locks were released, False if already released or no Redis connection
    """
    from pulpcore.app.models import AppStatus

    # Check if locks already released (idempotent)
    if getattr(task, "_all_locks_released", False):
        return False

    redis_conn = get_redis_connection()
    if redis_conn is None:
        return False

    # Extract resources from task
    exclusive_resources, shared_resources = extract_task_resources(task)

    # Determine lock owner
    if lock_owner is None:
        current_app = AppStatus.objects.current()
        lock_owner = current_app.name if current_app else f"immediate-{task.pk}"

    # Build task lock key
    task_lock_key = get_task_lock_key(task.pk)

    # Release all locks atomically
    release_resource_locks(
        redis_conn, lock_owner, task_lock_key, exclusive_resources, shared_resources
    )

    # Mark all locks as released
    task._all_locks_released = True
    return True


async def async_safe_release_task_locks(task, lock_owner=None):
    """
    Async version: Safely release all locks for a task with idempotency check.

    This function:
    1. Checks if locks have already been released (idempotent)
    2. Extracts resources from task.reserved_resources_record
    3. Determines lock owner (from AppStatus or task-specific identifier)
    4. Releases task lock and all resource locks atomically
    5. Marks locks as released to prevent double-release

    Args:
        task: The Task object to release locks for
        lock_owner: Optional lock owner identifier. If not provided, will use
            AppStatus.objects.current() or fall back to f"immediate-{task.pk}"

    Returns:
        bool: True if locks were released, False if already released or no Redis connection
    """
    from pulpcore.app.models import AppStatus

    # Check if locks already released (idempotent)
    if getattr(task, "_all_locks_released", False):
        return False

    redis_conn = get_redis_connection()
    if redis_conn is None:
        return False

    # Extract resources from task
    exclusive_resources, shared_resources = extract_task_resources(task)

    # Determine lock owner
    if lock_owner is None:
        current_app = await sync_to_async(AppStatus.objects.current)()
        lock_owner = current_app.name if current_app else f"immediate-{task.pk}"

    # Build task lock key
    task_lock_key = get_task_lock_key(task.pk)

    # Release all locks atomically
    await async_release_resource_locks(
        redis_conn, lock_owner, task_lock_key, exclusive_resources, shared_resources
    )

    # Mark all locks as released
    task._all_locks_released = True
    return True


def acquire_locks(redis_conn, lock_owner, task_lock_key, exclusive_resources, shared_resources):
    """
    Atomically try to acquire task lock and resource locks.

    Args:
        redis_conn: Redis connection
        lock_owner (str): The identifier of the lock owner (worker/task)
        task_lock_key (str): Redis key for the task lock (e.g., "task:{task_id}")
        exclusive_resources (list): List of exclusive resource names
        shared_resources (list): List of shared resource names

    Returns:
        list: Empty list if all locks acquired successfully,
              list of blocked resource names if acquisition failed
              (includes "__task_lock__" if task lock is held by another worker)
    """
    # Sort resources for consistent, reproducible key ordering
    exclusive_resources = sorted(exclusive_resources) if exclusive_resources else []
    shared_resources = sorted(shared_resources) if shared_resources else []

    # Build KEYS list: task_lock_key, then exclusive lock keys, then shared lock keys
    keys = [task_lock_key]
    for resource in exclusive_resources:
        keys.append(resource_to_lock_key(resource))
    for resource in shared_resources:
        keys.append(resource_to_lock_key(resource))

    # Build ARGV list: lock_owner, num_exclusive, resource names (for error reporting)
    args = [lock_owner, str(len(exclusive_resources))]
    args.extend(exclusive_resources)
    args.extend(shared_resources)

    # Register and execute the Lua script
    acquire_script = redis_conn.register_script(REDIS_ACQUIRE_LOCKS_SCRIPT)
    blocked_resources = acquire_script(keys=keys, args=args)
    return blocked_resources if blocked_resources else []


def release_resource_locks(
    redis_conn, lock_owner, task_lock_key, resources=None, shared_resources=None
):
    """
    Atomically release task lock and resource locks.

    Uses a Lua script to ensure we only release locks that we own.

    Args:
        redis_conn: Redis connection
        lock_owner (str): The identifier of the lock owner
        task_lock_key (str): Redis key for the task lock (e.g., "task:{task_id}")
        resources (list): List of exclusive resource names to release locks for
        shared_resources (list): Optional list of shared resource names
    """
    exclusive_resources = resources if resources else []
    shared_resources = shared_resources if shared_resources else []

    # Build KEYS list: task_lock_key, then exclusive lock keys, then shared lock keys
    keys = [task_lock_key]
    for resource in exclusive_resources:
        keys.append(resource_to_lock_key(resource))
    for resource in shared_resources:
        keys.append(resource_to_lock_key(resource))

    # Build ARGV list: lock_owner, num_exclusive, resource names (for error reporting)
    args = [lock_owner, str(len(exclusive_resources))]
    args.extend(exclusive_resources)
    args.extend(shared_resources)

    # Register and execute the Lua script
    release_script = redis_conn.register_script(REDIS_RELEASE_LOCKS_SCRIPT)
    try:
        result = release_script(keys=keys, args=args)
        # Result is [not_owned_exclusive, not_in_shared, task_lock_not_owned]
        not_owned_exclusive = result[0] if result and len(result) > 0 else []
        not_in_shared = result[1] if result and len(result) > 1 else []
        task_lock_not_owned = result[2] if result and len(result) > 2 else False

        # Log warnings for locks we didn't own
        for resource in not_owned_exclusive:
            _logger.warning("Lock for resource %s was not owned by %s", resource, lock_owner)
        for resource in not_in_shared:
            _logger.warning("Shared resource %s did not contain %s", resource, lock_owner)
        if task_lock_not_owned:
            _logger.warning("Task lock %s was not owned by %s", task_lock_key, lock_owner)

    except redis.RedisError as e:
        _logger.error("Error releasing locks: %s", e)
        raise


async def async_release_resource_locks(
    redis_conn, lock_owner, task_lock_key, resources=None, shared_resources=None
):
    """
    Async version: Atomically release task lock and resource locks.

    Uses a Lua script to ensure we only release locks that we own.

    Args:
        redis_conn: Redis connection
        lock_owner (str): The identifier of the lock owner
        task_lock_key (str): Redis key for the task lock (e.g., "task:{task_id}")
        resources (list): List of exclusive resource names to release locks for
        shared_resources (list): Optional list of shared resource names
    """
    exclusive_resources = resources if resources else []
    shared_resources = shared_resources if shared_resources else []

    # Build KEYS list: task_lock_key, then exclusive lock keys, then shared lock keys
    keys = [task_lock_key]
    for resource in exclusive_resources:
        keys.append(resource_to_lock_key(resource))
    for resource in shared_resources:
        keys.append(resource_to_lock_key(resource))

    # Build ARGV list: lock_owner, num_exclusive, resource names (for error reporting)
    args = [lock_owner, str(len(exclusive_resources))]
    args.extend(exclusive_resources)
    args.extend(shared_resources)

    # Register and execute the Lua script
    release_script = await sync_to_async(redis_conn.register_script)(REDIS_RELEASE_LOCKS_SCRIPT)
    try:
        result = await sync_to_async(release_script)(keys=keys, args=args)
        # Result is [not_owned_exclusive, not_in_shared, task_lock_not_owned]
        not_owned_exclusive = result[0] if result and len(result) > 0 else []
        not_in_shared = result[1] if result and len(result) > 1 else []
        task_lock_not_owned = result[2] if result and len(result) > 2 else False

        # Log warnings for locks we didn't own
        for resource in not_owned_exclusive:
            _logger.warning("Lock for resource %s was not owned by %s", resource, lock_owner)
        for resource in not_in_shared:
            _logger.warning("Shared resource %s did not contain %s", resource, lock_owner)
        if task_lock_not_owned:
            _logger.warning("Task lock %s was not owned by %s", task_lock_key, lock_owner)

    except redis.RedisError as e:
        _logger.error("Error releasing locks: %s", e)
        raise
