SELECT checks.outcome, count(*) AS count_1 
FROM checks 
WHERE checks.monitor_id = %(monitor_id_1)s::INTEGER AND checks.status = %(status_1)s::VARCHAR AND checks.started_at >= %(started_at_1)s::TIMESTAMP WITH TIME ZONE AND checks.started_at < %(started_at_2)s::TIMESTAMP WITH TIME ZONE GROUP BY checks.outcome
