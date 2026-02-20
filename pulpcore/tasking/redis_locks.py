"""
Redis distributed lock utilities for task resource coordination.

This module provides functions and Lua scripts for managing exclusive and shared
resource locks using Redis.
"""

import logging
from asgiref.sync import sync_to_async

from pulpcore.app.redis_connection import get_redis_connection


_logger = logging.getLogger(__name__)

# Redis key prefix for resource locks
REDIS_LOCK_PREFIX = "pulp:resource_lock:"

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

-- Release exclusive locks
-- Resource keys start at KEYS[2]
for i = 1, num_exclusive do
    local key = KEYS[1 + i]
    local resource_name = ARGV[2 + i]

    -- Check if we own the lock
    local current_owner = redis.call("get", key)
    if current_owner == lock_owner then
        redis.call("del", key)
    elseif current_owner ~= false then
        -- Lock exists but we don't own it
        table.insert(not_owned_exclusive, resource_name)
    end
    -- If current_owner is false (nil), lock doesn't exist - already released
end

-- Release shared locks
-- Shared keys start at KEYS[2 + num_exclusive]
for i = num_exclusive + 1, #KEYS - 1 do
    local key = KEYS[1 + i]
    local resource_name = ARGV[2 + i]

    -- Remove from set
    local removed = redis.call("srem", key, lock_owner)
    if removed == 0 then
        -- We weren't in the set
        table.insert(not_in_shared, resource_name)
    end
end

-- Release task lock
local task_lock_owner = redis.call("get", task_lock_key)
if task_lock_owner == lock_owner then
    redis.call("del", task_lock_key)
elseif task_lock_owner ~= false then
    -- Task lock exists but we don't own it
    task_lock_not_owned = true
end

return {not_owned_exclusive, not_in_shared, task_lock_not_owned}
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
        bool: True if locks were released, False if already released
    """
    from pulpcore.app.models import AppStatus

    # Check if locks already released (idempotent)
    if getattr(task, "_all_locks_released", False):
        return False

    redis_conn = get_redis_connection()

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
    # Sort resources deterministically to prevent deadlocks
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
    try:
        blocked_resources = acquire_script(keys=keys, args=args)
        # Redis returns list of blocked resources or empty list
        return blocked_resources if blocked_resources else []
    except Exception as e:
        _logger.error("Error acquiring locks: %s", e)
        return ["error"]  # Return non-empty list to indicate failure


def release_resource_locks(redis_conn, lock_owner, task_lock_key, resources, shared_resources=None):
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

        # Log debug for successful releases
        num_released_exclusive = len(exclusive_resources) - len(not_owned_exclusive)
        num_released_shared = len(shared_resources) - len(not_in_shared)
        if num_released_exclusive > 0:
            _logger.debug("Released %d exclusive lock(s)", num_released_exclusive)
        if num_released_shared > 0:
            _logger.debug("Released %d shared lock(s)", num_released_shared)
        if not task_lock_not_owned:
            _logger.debug("Released task lock %s", task_lock_key)
    except Exception as e:
        _logger.error("Error releasing locks: %s", e)


async def async_release_resource_locks(
    redis_conn, lock_owner, task_lock_key, resources, shared_resources=None
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

        # Log debug for successful releases
        num_released_exclusive = len(exclusive_resources) - len(not_owned_exclusive)
        num_released_shared = len(shared_resources) - len(not_in_shared)
        if num_released_exclusive > 0:
            _logger.debug("Released %d exclusive lock(s)", num_released_exclusive)
        if num_released_shared > 0:
            _logger.debug("Released %d shared lock(s)", num_released_shared)
        if not task_lock_not_owned:
            _logger.debug("Released task lock %s", task_lock_key)
    except Exception as e:
        _logger.error("Error releasing locks: %s", e)
