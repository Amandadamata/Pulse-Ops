DELETE FROM checks WHERE checks.id IN (SELECT checks.id 
FROM checks 
WHERE checks.started_at < %(started_at_1)s::TIMESTAMP WITH TIME ZONE AND checks.status = %(status_1)s::VARCHAR 
 LIMIT %(param_1)s::INTEGER) RETURNING checks.id
