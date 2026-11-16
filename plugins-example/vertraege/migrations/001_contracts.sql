-- One row per contract, linked to its documents; prices as they changed over time.
CREATE TABLE contracts (
    id               bigserial PRIMARY KEY,
    owner_id         bigint NOT NULL,
    shared           boolean NOT NULL DEFAULT false,
    profile_id       bigint,
    provider         text NOT NULL,
    provider_address text[] NOT NULL DEFAULT '{}',
    kind             text NOT NULL DEFAULT 'other',
    product          text,
    customer_number  text,
    contract_number  text,
    start_date       date,
    term_end         date,
    renewal_months   integer,
    notice_amount    integer,
    notice_unit      text CHECK (notice_unit IN ('days', 'weeks', 'months')),
    notice_to        text NOT NULL DEFAULT 'term_end'
                     CHECK (notice_to IN ('term_end', 'month_end', 'quarter_end', 'any_day')),
    price            numeric(12,2),
    price_period     text CHECK (price_period IN ('month', 'quarter', 'year', 'once')),
    currency         text NOT NULL DEFAULT 'EUR',
    state            text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'cancelled', 'ended')),
    cancel_sent_on   date,
    cancel_effective date,
    cancel_confirmed_on date,
    notes            text,
    locked_fields    text[] NOT NULL DEFAULT '{}',   -- set by a person: the AI never changes them
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX contracts_owner ON contracts (owner_id);

CREATE TABLE contract_documents (
    contract_id bigint NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    document_id text NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    role        text NOT NULL CHECK (role IN ('contract', 'change', 'invoice', 'cancellation', 'confirmation', 'other')),
    PRIMARY KEY (contract_id, document_id)
);

CREATE TABLE price_history (
    id           bigserial PRIMARY KEY,
    contract_id  bigint NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    valid_from   date,
    price        numeric(12,2) NOT NULL,
    price_period text,
    document_id  text REFERENCES public.documents(id) ON DELETE SET NULL,
    accepted     boolean NOT NULL DEFAULT false   -- a note until the person accepts it
);
