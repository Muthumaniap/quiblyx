
CREATE TABLE applications (
	name VARCHAR(120) NOT NULL, 
	group_id VARCHAR(36), 
	connection_id VARCHAR(36) NOT NULL, 
	paused BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE INDEX ix_applications_tenant_id ON applications (tenant_id);

CREATE TABLE audit_events (
	actor VARCHAR(255) NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	target VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE INDEX ix_audit_events_tenant_id ON audit_events (tenant_id);

CREATE TABLE budgets (
	scope_id VARCHAR(36) NOT NULL, 
	period VARCHAR(7) NOT NULL, 
	hard_limit BIGINT NOT NULL, 
	spent BIGINT NOT NULL, 
	reserved BIGINT NOT NULL, 
	version INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (tenant_id, scope_id, period), 
	CHECK (spent >= 0 AND reserved >= 0 AND hard_limit >= 0)
)

;
CREATE INDEX ix_budgets_tenant_id ON budgets (tenant_id);

CREATE TABLE groups (
	name VARCHAR(120) NOT NULL, 
	parent_id VARCHAR(36), 
	paused BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE INDEX ix_groups_tenant_id ON groups (tenant_id);

CREATE TABLE ledger_entries (
	request_id VARCHAR(36) NOT NULL, 
	budget_id VARCHAR(36) NOT NULL, 
	amount BIGINT NOT NULL, 
	event VARCHAR(40) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (request_id, budget_id, event)
)

;
CREATE INDEX ix_ledger_entries_tenant_id ON ledger_entries (tenant_id);

CREATE TABLE memberships (
	subject VARCHAR(255) NOT NULL, 
	role VARCHAR(80) NOT NULL, 
	scope_id VARCHAR(36), 
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (tenant_id, subject)
)

;
CREATE INDEX ix_memberships_subject ON memberships (subject);
CREATE INDEX ix_memberships_tenant_id ON memberships (tenant_id);

CREATE TABLE outbox_events (
	kind VARCHAR(40) NOT NULL, 
	payload JSON NOT NULL, 
	delivered BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE INDEX ix_outbox_events_tenant_id ON outbox_events (tenant_id);

CREATE TABLE provider_connections (
	name VARCHAR(120) NOT NULL, 
	provider VARCHAR(30) NOT NULL, 
	encrypted_secret VARCHAR NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE INDEX ix_provider_connections_tenant_id ON provider_connections (tenant_id);

CREATE TABLE requests (
	application_id VARCHAR(36) NOT NULL, 
	key_id VARCHAR(36) NOT NULL, 
	idempotency_key VARCHAR(128) NOT NULL, 
	payload_hash VARCHAR(64) NOT NULL, 
	state VARCHAR(30) NOT NULL, 
	bound BIGINT NOT NULL, 
	cost BIGINT, 
	input_tokens INTEGER NOT NULL, 
	output_tokens INTEGER NOT NULL, 
	response JSON, 
	model VARCHAR(100) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (tenant_id, key_id, idempotency_key)
)

;
CREATE INDEX ix_requests_tenant_id ON requests (tenant_id);

CREATE TABLE reservations (
	request_id VARCHAR(36) NOT NULL, 
	budget_id VARCHAR(36) NOT NULL, 
	amount BIGINT NOT NULL, 
	settled BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (request_id, budget_id)
)

;
CREATE INDEX ix_reservations_request_id ON reservations (request_id);
CREATE INDEX ix_reservations_tenant_id ON reservations (tenant_id);

CREATE TABLE tenants (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	content_days INTEGER NOT NULL, 
	metadata_days INTEGER NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE virtual_keys (
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR(36) NOT NULL, 
	application_id VARCHAR(36) NOT NULL, 
	digest VARCHAR(64) NOT NULL, 
	prefix VARCHAR(16) NOT NULL, 
	revoked BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (digest)
)

;
CREATE INDEX ix_virtual_keys_tenant_id ON virtual_keys (tenant_id);