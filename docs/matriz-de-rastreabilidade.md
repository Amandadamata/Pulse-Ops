# Matriz de rastreabilidade

Requisito ou cenário → onde está implementado → evidência. Os testes estão em
`tests/` e rodam com `uv run pytest` contra PostgreSQL real. "Lab" é o roteiro
`scripts/demo.sh` (11 passos). Os nomes de teste abaixo foram conferidos contra o
código por script (ver "Como esta matriz foi conferida", no fim).

## Os 25 cenários obrigatórios

| # | Cenário | Evidência |
|---|---|---|
| 1 | URL e configuração inválidas | `tests/unit/test_monitor_rules.py::test_out_of_range_values`, `::test_timeout_must_be_smaller_than_interval`, `::test_latency_threshold_cannot_exceed_timeout`, `::test_all_errors_reported_together`; `tests/unit/test_status_codes.py::test_invalid_specs_are_rejected`; `tests/integration/test_api_monitors.py::test_invalid_configuration_is_rejected`, `::test_unknown_fields_and_methods_rejected`; `tests/integration/test_dashboard.py::test_create_monitor_through_form_and_see_errors` |
| 2 | Resposta 200 lenta | `tests/unit/test_checker.py::test_slow_200_is_slow_not_failure`; `tests/unit/test_health.py::test_slow_is_degraded_but_not_a_failure`, `::test_slow_response_counts_towards_recovery`; Lab passo 3 |
| 3 | Status não aceito | `tests/unit/test_checker.py::test_unexpected_status`; `tests/unit/test_status_codes.py::test_ranges_and_single_codes`; Lab passo 5 |
| 4 | Falha de rede e falha TLS | `tests/unit/test_checker.py::test_network_and_tls_failures`, `::test_dns_failure_is_connection_error`, `::test_tls_handshake_error_without_cert_verification`, `::test_total_deadline_is_enforced`; Lab passo 4 (timeout) |
| 5 | Limiar de falhas | `tests/unit/test_health.py::test_mandatory_example_fail_fail_success_opens_nothing`, `::test_mandatory_example_three_failures_open_exactly_one_incident`; `tests/integration/test_incident_lifecycle.py::test_threshold_example_with_database`; Lab passo 5 |
| 6 | Recuperação com sucessos consecutivos | `tests/unit/test_health.py::test_mandatory_example_recovery_requires_configured_successes`, `::test_failure_during_recovery_resets_success_counter`; Lab passos 7 e 8 |
| 7 | Alternância entre falha e sucesso | `tests/unit/test_health.py::test_alternating_results_never_reach_threshold`; `tests/integration/test_incident_lifecycle.py::test_alternating_results_do_not_open_incident` |
| 8 | Incidente sem duplicação | `tests/unit/test_health.py::test_mandatory_example_more_failures_update_the_same_incident`; `tests/integration/test_consistency.py::test_database_rejects_second_open_incident`; Lab passo 6 |
| 9 | Resultado reprocessado | `tests/integration/test_consistency.py::test_reprocessed_result_is_ignored`, `::test_same_run_identity_cannot_be_reserved_twice` |
| 10 | Check sobreposto | `tests/integration/test_consistency.py::test_overlapping_check_is_not_started`, `::test_database_rejects_second_running_check`, `::test_concurrent_claims_never_take_the_same_monitor`; `tests/integration/test_api_monitors.py::test_check_now_marks_next_check_as_manual` |
| 11 | Pausa e retomada | `tests/integration/test_incident_lifecycle.py::test_pause_closes_open_incident_and_resume_starts_clean`, `::test_result_of_run_started_before_pause_and_resume_does_not_count`; `tests/integration/test_api_monitors.py::test_pause_resume_and_conflicts`; `tests/integration/test_metrics.py::test_paused_period_produces_no_samples` |
| 12 | Alteração de configuração | `tests/integration/test_incident_lifecycle.py::test_config_change_resets_counters_and_keeps_incident`, `::test_result_of_run_started_before_config_change_does_not_count` |
| 13 | Reinício com incidente aberto | `tests/integration/test_incident_lifecycle.py::test_restart_with_open_incident_continues_and_records_gap` |
| 14 | Worker parado e dados desatualizados | `tests/integration/test_consistency.py::test_stopped_worker_makes_data_stale`, `::test_old_last_check_is_stale_even_with_worker_alive`, `::test_second_worker_is_refused` |
| 15 | Banco temporariamente indisponível | `tests/integration/test_consistency.py::test_database_failure_while_recording_does_not_count_as_target_failure`, `::test_worker_loop_survives_unreachable_database`, `::test_interrupted_run_becomes_internal_error_not_failure`; `tests/integration/test_health_endpoints.py::test_ready_returns_503_when_database_is_down` |
| 16 | Webhook lento ou indisponível | `tests/integration/test_delivery.py::test_slow_webhook_does_not_block_checks`, `::test_webhook_timeout_is_retryable`, `::test_retries_with_capped_exponential_backoff`; Lab passos 9 e 10 |
| 17 | Retentativa e deduplicação no receptor | `tests/integration/test_delivery.py::test_expired_lease_is_retried_which_may_duplicate`, `::test_webhook_notifier_sends_event_id_and_classifies_errors`, `::test_attempts_are_limited_then_failed`; `tests/unit/test_lab_receiver.py::test_duplicate_event_is_detected`, `::test_unavailable_receiver_rejects_then_accepts`; Lab passo 11 |
| 18 | UTC e limites temporais | `tests/integration/test_api_history.py::test_window_start_inclusive_end_exclusive`, `::test_window_with_other_timezone_is_converted`, `::test_naive_datetimes_are_rejected`; `tests/integration/test_dashboard.py::test_times_are_shown_in_display_timezone`; `tests/unit/test_metrics_formulas.py::test_incident_crossing_window_is_clipped`; `tests/integration/test_consistency.py::test_scheduled_time_and_observed_time_are_both_recorded` |
| 19 | Métricas sem dados e p95 com amostra pequena | `tests/integration/test_metrics.py::test_no_data_returns_na_not_zero_or_hundred`, `::test_sql_percentile_matches_nearest_rank`; `tests/unit/test_metrics_formulas.py::test_nearest_rank_without_samples_is_none`, `::test_nearest_rank_small_sample_returns_maximum`, `::test_ratio_without_base_is_none_not_zero_or_hundred` |
| 20 | Arquivamento com preservação do histórico | `tests/integration/test_api_monitors.py::test_archive_preserves_history`; `tests/integration/test_dashboard.py::test_edit_and_lifecycle_actions_through_forms` |
| 21 | Autenticação, autorização e CSRF | `tests/integration/test_auth.py` (16 testes: `::test_api_requires_session`, `::test_pages_redirect_to_login`, `::test_mutations_without_session_are_rejected`, `::test_api_mutation_requires_csrf_header`, `::test_form_action_requires_csrf_field`, `::test_login_form_requires_its_csrf_cookie`, `::test_session_expires`, `::test_logout_invalidates_session`, entre outros) |
| 22 | Bloqueios SSRF e de redirecionamento | `tests/unit/test_url_policy.py::test_blocked_urls`; `tests/unit/test_transport.py::test_rebinding_is_checked_at_connect_time`, `::test_connects_to_validated_ip_and_keeps_host_header`, `::test_redirects_are_not_followed_by_default`; `tests/unit/test_checker.py::test_redirect_is_not_followed`, `::test_blocked_destination_at_connect_time`; `tests/integration/test_api_monitors.py::test_dns_pointing_to_private_address_is_rejected`, `::test_destinations_api_validates_url`; `tests/integration/test_delivery.py::test_blocked_destination_fails_permanently` |
| 23 | Tentativa de injeção na interface | `tests/integration/test_dashboard.py::test_monitor_name_is_escaped`, `::test_sql_injection_attempts_are_plain_data`, `::test_security_headers` |
| 24 | Retenção de dados | `tests/integration/test_retention.py::test_old_checks_are_purged_and_incidents_kept`, `::test_maintenance_runs_retention` |
| 25 | Inicialização limpa seguindo o README | Execução registrada em `docs/evidencias/instalacao-limpa.md`; `tests/integration/test_migrations.py::test_upgrade_on_empty_database_creates_all_tables`; job `docker` do CI |

## Requisitos funcionais

| Requisito | Implementação | Evidência |
|---|---|---|
| RF01 Cadastro (CRUD, limites, nome único, pausa, arquivamento) | `domain/monitor_rules.py`, `services/monitors.py`, `web/api.py`, `web/pages.py` | Cenários 1, 11, 12, 20; `tests/integration/test_api_monitors.py::test_create_list_get_update`, `::test_duplicate_name_is_rejected_case_insensitive` |
| RF02 Verificações (classificação, corpo não lido, TLS, sem redirecionamento, explicação sem segredos) | `checks/checker.py`, `domain/outcomes.py`, `security/transport.py` | Cenários 2, 3, 4, 22; `tests/unit/test_checker.py::test_body_is_not_read`, `::test_explanation_never_contains_url_or_query`, `::test_unexpected_exception_is_internal_error_not_target_failure`, `::test_head_method_is_used` |
| RF03 Estados e incidentes (limiares, explicação, retrato da decisão) | `domain/health.py`, `services/processing.py`, `services/incidents.py` | Cenários 5 a 13; `tests/unit/test_health.py::test_first_failure_time_is_kept_until_confirmation`, `::test_internal_error_changes_nothing`, `::test_every_target_failure_category_counts`; `tests/integration/test_incident_lifecycle.py::test_error_type_change_is_recorded_on_timeline`, `::test_every_health_change_is_explained` |
| RF04 Histórico (cursor, filtros, linha do tempo, notificações) | `services/queries.py`, `web/api.py` | `tests/integration/test_api_history.py::test_cursor_pagination_is_stable_and_complete`, `::test_filter_by_outcome`, `::test_pagination_limits`, `::test_incident_list_detail_and_timeline`, `::test_alerts_endpoint_lists_deliveries_and_attempts` |
| RF05 Métricas | `domain/metrics.py`, `services/queries.py::monitor_metrics` | Cenários 18 e 19; `tests/integration/test_metrics.py::test_formulas_and_denominators`, `::test_incident_crossing_window_and_open_incident_duration`, `::test_invalid_window_is_rejected` |
| RF06 Alertas (outbox, retentativa, falha permanente, SSRF no webhook) | `services/alerts.py`, `notifications/webhook.py`, `worker/runner.py` | Cenários 16 e 17; `tests/integration/test_delivery.py::test_transition_creates_event_and_delivery_which_is_sent`, `::test_outbox_event_is_atomic_with_incident`, `::test_client_error_is_permanent_failure`, `::test_permanent_status_classification`, `::test_backoff_is_capped`, `::test_without_destination_event_is_still_recorded` |
| RF07 Dashboard | `web/pages.py`, `web/templates/`, `web/charts.py`, `web/static/` | `tests/integration/test_dashboard.py` (12 testes); capturas reais em `docs/imagens/` |
| RF08 Acesso | `services/auth.py`, `web/deps.py`, `cli.py`, `security/passwords.py` | Cenário 21; `tests/unit/test_passwords.py`; `tests/integration/test_cli.py::test_create_admin_from_stdin`, `::test_short_password_is_rejected` |
| RF09 Saúde do próprio PulseOps | `web/health.py`, `worker/runner.py::heartbeat`, `logs.py` | `tests/integration/test_health_endpoints.py::test_live_and_ready`; cenário 14; `tests/unit/test_logging.py::test_context_is_added_to_every_line`, `::test_output_is_json_with_level_and_message` |

## Consistência (CB)

| Regra | Evidência |
|---|---|
| CB1 Resultado em uma transação | `tests/integration/test_delivery.py::test_outbox_event_is_atomic_with_incident`; `tests/integration/test_consistency.py::test_database_failure_while_recording_does_not_count_as_target_failure` |
| CB2 Sem transação durante HTTP | Estrutura de `services/processing.py` (reserva e gravação em funções separadas); ADR 0003 |
| CB3 Um check `running` por monitor | Cenário 10 |
| CB4 Retomada sem avalanche e lacunas | `tests/integration/test_incident_lifecycle.py::test_restart_with_open_incident_continues_and_records_gap` |
| CB5 "Verificar agora" com o mesmo controle | `tests/integration/test_api_monitors.py::test_check_now_marks_next_check_as_manual`; `tests/integration/test_consistency.py::test_overlapping_check_is_not_started` |
| CB6 Retenção | Cenário 24 |
| CB7 Um worker só | `tests/integration/test_consistency.py::test_second_worker_is_refused` |
| Vazão do worker sob fila (B8) | `tests/integration/test_consistency.py::test_dispatcher_refills_freed_slots_without_waiting_a_tick`; `docs/evidencias/ensaio-de-carga.md` |

## Como esta matriz foi conferida

Cada `arquivo::teste` citado foi verificado com um script que procura
`def <teste>` no arquivo indicado (registrado em `docs/evidencias/verificacao.md`).
