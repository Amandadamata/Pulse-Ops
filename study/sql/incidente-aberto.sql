SELECT incidents.id, incidents.monitor_id, incidents.status, incidents.started_at, incidents.confirmed_at, incidents.ended_at, incidents.failure_threshold, incidents.recovery_threshold, incidents.timeout_seconds, incidents.latency_threshold_ms, incidents.opening_reason, incidents.resolution_reason, incidents.resolution_explanation, incidents.failure_count, incidents.last_outcome, incidents.last_explanation, incidents.last_check_id 
FROM incidents 
WHERE incidents.monitor_id = %(monitor_id_1)s::INTEGER AND incidents.status = %(status_1)s::VARCHAR FOR UPDATE
