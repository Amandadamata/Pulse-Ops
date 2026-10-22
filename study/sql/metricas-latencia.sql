SELECT count(checks.duration_ms) AS count_1, avg(checks.duration_ms) AS avg_1, percentile_disc(%(percentile_disc_2)s) WITHIN GROUP (ORDER BY checks.duration_ms) AS percentile_disc_1 
FROM checks 
WHERE checks.monitor_id = %(monitor_id_1)s::INTEGER AND checks.status = %(status_1)s::VARCHAR AND checks.started_at >= %(started_at_1)s::TIMESTAMP WITH TIME ZONE AND checks.started_at < %(started_at_2)s::TIMESTAMP WITH TIME ZONE AND checks.outcome IN (%(outcome_1_1)s::VARCHAR, %(outcome_1_2)s::VARCHAR, %(outcome_1_3)s::VARCHAR)
