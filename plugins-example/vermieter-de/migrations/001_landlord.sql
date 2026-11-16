-- Properties, flats, tenancies, cost bills, rent ledger and statements.
CREATE TABLE properties (
    id         bigserial PRIMARY KEY,
    owner_id   bigint NOT NULL,
    profile_id bigint,                 -- the landlord's identity, printed on letters
    name       text NOT NULL,
    street     text NOT NULL DEFAULT '',
    postcode   text NOT NULL DEFAULT '',
    city       text NOT NULL DEFAULT '',
    year_start_month integer NOT NULL DEFAULT 1 CHECK (year_start_month BETWEEN 1 AND 12)
);

CREATE TABLE units (
    id          bigserial PRIMARY KEY,
    property_id bigint NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    name        text NOT NULL,
    area        numeric(8,2) NOT NULL CHECK (area > 0),
    shares      jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE tenancies (
    id              bigserial PRIMARY KEY,
    unit_id         bigint NOT NULL REFERENCES units(id),
    tenant_name     text NOT NULL,
    tenant_email    text,
    tenant_address  text,              -- for letters after moving out
    start_date      date NOT NULL,
    end_date        date,
    rent            numeric(10,2) NOT NULL DEFAULT 0,
    advance         numeric(10,2) NOT NULL DEFAULT 0,   -- service charges and heating, per month
    deposit         numeric(10,2),
    agreement_document_id text REFERENCES public.documents(id) ON DELETE SET NULL,
    CHECK (end_date IS NULL OR end_date >= start_date)
);

CREATE TABLE persons (
    tenancy_id bigint NOT NULL REFERENCES tenancies(id) ON DELETE CASCADE,
    since      date NOT NULL,
    persons    integer NOT NULL CHECK (persons >= 0),
    PRIMARY KEY (tenancy_id, since)
);

CREATE TABLE allocation (
    property_id bigint NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    cost_type   text NOT NULL,
    key         text NOT NULL,
    passable    boolean NOT NULL,
    PRIMARY KEY (property_id, cost_type)
);

CREATE TABLE cost_items (
    id          bigserial PRIMARY KEY,
    property_id bigint NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    cost_type   text,
    document_id text REFERENCES public.documents(id) ON DELETE SET NULL,
    amount      numeric(12,2) NOT NULL,
    period_from date NOT NULL,
    period_to   date NOT NULL,
    unit_id     bigint REFERENCES units(id),   -- a cost of one flat only
    state       text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed', 'confirmed')),
    note        text,
    CHECK (period_to >= period_from)
);

CREATE TABLE consumption (
    property_id bigint NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    year        integer NOT NULL,
    cost_type   text NOT NULL,
    tenancy_id  bigint NOT NULL REFERENCES tenancies(id) ON DELETE CASCADE,
    value       numeric(12,2) NOT NULL,
    PRIMARY KEY (property_id, year, cost_type, tenancy_id)
);

CREATE TABLE rent_ledger (
    tenancy_id bigint NOT NULL REFERENCES tenancies(id) ON DELETE CASCADE,
    month      date NOT NULL,   -- the first day of the month
    due        numeric(10,2) NOT NULL,
    received   numeric(10,2) NOT NULL DEFAULT 0,
    received_on date,
    transaction_id bigint,
    PRIMARY KEY (tenancy_id, month)
);

CREATE TABLE statements (
    id          bigserial PRIMARY KEY,
    tenancy_id  bigint NOT NULL REFERENCES tenancies(id),
    year        integer NOT NULL,
    state       text NOT NULL DEFAULT 'issued' CHECK (state IN ('issued', 'sent')),
    lines       jsonb NOT NULL,
    total_costs numeric(12,2) NOT NULL,
    advances    numeric(12,2) NOT NULL,
    balance     numeric(12,2) NOT NULL,
    document_id text REFERENCES public.documents(id),
    replaces_id bigint REFERENCES statements(id),
    issued_at   timestamptz NOT NULL DEFAULT now(),
    sent_on     date
);
