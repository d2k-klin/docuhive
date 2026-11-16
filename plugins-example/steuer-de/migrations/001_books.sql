-- Books, who may work in them, bookings, rules learnt from confirmed bookings, and periods.
CREATE TABLE books (
    id                 bigserial PRIMARY KEY,
    owner_id           bigint NOT NULL,
    name               text NOT NULL,
    kind               text NOT NULL CHECK (kind IN ('euer', 'hand_over', 'private')),
    chart              text CHECK (chart IN ('skr03', 'skr04')),
    vat_status         text NOT NULL DEFAULT 'regular'
                       CHECK (vat_status IN ('regular', 'small_business', 'exempt')),
    vat_period         text NOT NULL DEFAULT 'quarterly'
                       CHECK (vat_period IN ('monthly', 'quarterly', 'yearly', 'none')),
    vat_basis          text NOT NULL DEFAULT 'invoice' CHECK (vat_basis IN ('invoice', 'payment')),
    standing_extension boolean NOT NULL DEFAULT false,
    special_advance    numeric(14,2) NOT NULL DEFAULT 0,
    tax_number         text,
    vat_id             text,
    federal_state      text,
    default_for_uploads boolean NOT NULL DEFAULT false,
    test_mode          boolean NOT NULL DEFAULT true,
    opened_on          date NOT NULL DEFAULT current_date,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE book_members (
    book_id  bigint NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    user_id  bigint NOT NULL,
    role     text NOT NULL CHECK (role IN ('owner', 'bookkeeper', 'viewer')),
    PRIMARY KEY (book_id, user_id)
);

CREATE TABLE entries (
    id                  bigserial PRIMARY KEY,
    book_id             bigint NOT NULL REFERENCES books(id),
    document_id         text REFERENCES public.documents(id),
    line                integer NOT NULL DEFAULT 1,
    direction           text NOT NULL CHECK (direction IN ('income', 'expense')),
    entry_date          date NOT NULL,
    service_date        date,
    paid_on             date,
    account             text,
    vat_code            text,
    net                 numeric(14,2) NOT NULL,
    vat                 numeric(14,2) NOT NULL,
    gross               numeric(14,2) NOT NULL,
    deductible_fraction numeric(4,3) NOT NULL DEFAULT 1,
    counterparty        text,
    state               text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed', 'confirmed', 'closed')),
    origin              text NOT NULL CHECK (origin IN ('e_invoice', 'ai', 'rule', 'manual', 'invoice')),
    note                text,
    period_vat          text,
    period_year         integer,
    corrects_entry_id   bigint REFERENCES entries(id),
    created_by          text,
    confirmed_by        text,
    confirmed_at        timestamptz,
    CHECK (net + vat = gross),
    UNIQUE (book_id, document_id, line)
);
CREATE INDEX entries_period ON entries (book_id, period_vat);

-- A closed booking never changes; a mistake is corrected by a new booking that refers to it.
CREATE FUNCTION entries_frozen() RETURNS trigger AS $$
BEGIN
    IF OLD.state = 'closed' THEN
        RAISE EXCEPTION 'A booking in a closed period cannot be changed or deleted';
    END IF;
    RETURN COALESCE(NEW, OLD);
END $$ LANGUAGE plpgsql;
CREATE TRIGGER entries_frozen BEFORE UPDATE OR DELETE ON entries
    FOR EACH ROW EXECUTE FUNCTION entries_frozen();

CREATE TABLE booking_rules (
    id          bigserial PRIMARY KEY,
    book_id     bigint NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    counterparty text NOT NULL,
    account     text NOT NULL,
    vat_code    text NOT NULL,
    uses        integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (book_id, counterparty)
);

CREATE TABLE periods (
    id            bigserial PRIMARY KEY,
    book_id       bigint NOT NULL REFERENCES books(id),
    key           text NOT NULL,              -- 2026-03, 2026-Q1, 2026 (VAT) or EUER-2026
    state         text NOT NULL CHECK (state IN ('checked', 'closed', 'filed')),
    rules_version text NOT NULL,
    figures       jsonb NOT NULL,
    note          text,
    closed_by     text,
    closed_at     timestamptz,
    filed_on      date,
    filing_document_id text REFERENCES public.documents(id),
    UNIQUE (book_id, key)
);
