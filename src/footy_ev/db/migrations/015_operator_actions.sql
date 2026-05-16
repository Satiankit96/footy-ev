-- 015_operator_actions: append-only audit trail for every operator-initiated mutation.
-- No UPDATE or DELETE ever references this table. Rows are written by the API audit
-- middleware after each successful state-mutating request (POST/PUT/DELETE).
CREATE TABLE IF NOT EXISTS operator_actions (
    action_id      VARCHAR PRIMARY KEY,
    action_type    VARCHAR NOT NULL,
    operator       VARCHAR NOT NULL DEFAULT 'operator',
    performed_at   TIMESTAMP NOT NULL,
    input_params   JSON,
    result_summary VARCHAR,
    request_id     VARCHAR
);
