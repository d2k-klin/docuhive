-- Accounts, the statements read for them, their transactions, and which document each
-- payment belongs to.
CREATE TABLE accounts (
    id         bigserial PRIMARY KEY,
    owner_id   bigint NOT NULL,
    iban       text NOT NULL,
    name       text,
    currency   text NOT NULL DEFAULT 'EUR',
    shared     boolean NOT NULL DEFAULT false,
    UNIQUE (owner_id, iban)
);

CREATE TABLE statements (
    document_id  text PRIMARY KEY REFERENCES public.documents(id),
    account_id   bigint NOT NULL REFERENCES accounts(id),
    format       text NOT NULL,
    period_start date,
    period_end   date,
    opening      numeric(14,2),
    closing      numeric(14,2),
    complete     boolean NOT NULL,
    problem      text
);

CREATE TABLE transactions (
    id                bigserial PRIMARY KEY,
    account_id        bigint NOT NULL REFERENCES accounts(id),
    statement_id      text REFERENCES statements(document_id),
    booking_date      date NOT NULL,
    value_date        date,
    amount            numeric(14,2) NOT NULL,
    currency          text NOT NULL,
    counterparty      text,
    counterparty_iban text,
    purpose           text,
    end_to_end_id     text,
    bank_reference    text,
    fingerprint       text NOT NULL,
    ignored_reason    text,
    UNIQUE (account_id, fingerprint)
);
CREATE INDEX transactions_open ON transactions (account_id, booking_date) WHERE ignored_reason IS NULL;

CREATE TABLE matches (
    id             bigserial PRIMARY KEY,
    transaction_id bigint NOT NULL REFERENCES transactions(id),
    document_id    text NOT NULL REFERENCES public.documents(id),
    amount         numeric(14,2) NOT NULL,
    how            text NOT NULL,
    state          text NOT NULL CHECK (state IN ('confirmed', 'suggested')),
    score          real,
    confirmed_by   text,
    confirmed_at   timestamptz,
    UNIQUE (transaction_id, document_id)
);

CREATE TABLE match_rules (
    id         bigserial PRIMARY KEY,
    owner_id   bigint NOT NULL,
    counterparty text NOT NULL,
    reason     text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
