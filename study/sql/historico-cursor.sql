SELECT checks.id, checks.monitor_id, checks.run_key, checks.trigger, checks.status, checks.config_version, checks.scheduled_at, checks.started_at, checks.finished_at, checks.duration_ms, checks.status_code, checks.outcome, checks.explanation 
FROM checks 
WHERE checks.monitor_id = %(monitor_id_1)s::INTEGER AND checks.status = %(status_1)s::VARCHAR AND (checks.started_at, checks.id) < (%(param_1)s::TIMESTAMP WITH TIME ZONE, %(param_2)s::INTEGER) ORDER BY checks.started_at DESC, checks.id DESC 
 LIMIT %(param_3)s::INTEGER
