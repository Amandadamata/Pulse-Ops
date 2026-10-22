SELECT monitors.id, monitors.name, monitors.description, monitors.url, monitors.method, monitors.interval_seconds, monitors.timeout_seconds, monitors.accepted_status_codes, monitors.latency_threshold_ms, monitors.failure_threshold, monitors.recovery_threshold, monitors.state, monitors.health, monitors.health_reason, monitors.health_changed_at, monitors.consecutive_failures, monitors.consecutive_successes, monitors.first_failure_at, monitors.config_version, monitors.next_run_at, monitors.check_requested, monitors.last_check_at, monitors.created_at, monitors.updated_at, monitors.archived_at 
FROM monitors 
WHERE monitors.state = %(state_1)s::VARCHAR AND monitors.next_run_at <= %(next_run_at_1)s::TIMESTAMP WITH TIME ZONE AND NOT (EXISTS (SELECT * 
FROM checks 
WHERE checks.monitor_id = monitors.id AND checks.status = %(status_1)s::VARCHAR)) ORDER BY monitors.next_run_at, monitors.id 
 LIMIT %(param_1)s::INTEGER FOR UPDATE SKIP LOCKED
