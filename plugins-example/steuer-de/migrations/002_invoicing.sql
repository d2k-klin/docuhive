-- Customers, invoices with their lines, number series, payments and payment reminders.
ALTER TABLE books ADD COLUMN profile_id bigint;   -- the seller: an identity (Settings → Identities)

CREATE TABLE customers (
    id                 bigserial PRIMARY KEY,
    book_id            bigint NOT NULL REFERENCES books(id),
    name               text NOT NULL,
    street             text NOT NULL DEFAULT '',
    postcode           text NOT NULL DEFAULT '',
    city               text NOT NULL DEFAULT '',
    country            text NOT NULL DEFAULT 'DE',
    email              text,
    vat_id             text,
    routing_id         text,             -- Leitweg-ID or another buyer reference
    kind               text NOT NULL DEFAULT 'business' CHECK (kind IN ('business', 'consumer', 'public')),
    e_invoice_format   text NOT NULL DEFAULT 'zugferd' CHECK (e_invoice_format IN ('zugferd', 'xrechnung', 'pdf_only')),
    payment_terms_days integer NOT NULL DEFAULT 14,
    language           text NOT NULL DEFAULT 'de',
    archived           boolean NOT NULL DEFAULT false
);

CREATE TABLE number_series (
    book_id  bigint NOT NULL REFERENCES books(id),
    series   text NOT NULL,
    pattern  text NOT NULL DEFAULT '{year}-{seq:04d}',
    next_seq integer NOT NULL DEFAULT 1 CHECK (next_seq > 0),
    reset    text NOT NULL DEFAULT 'yearly' CHECK (reset IN ('never', 'yearly')),
    year     integer,
    PRIMARY KEY (book_id, series)
);

CREATE TABLE invoices (
    id                  bigserial PRIMARY KEY,
    book_id             bigint NOT NULL REFERENCES books(id),
    customer_id         bigint NOT NULL REFERENCES customers(id),
    kind                text NOT NULL DEFAULT 'invoice' CHECK (kind IN ('quote', 'invoice', 'credit_note')),
    state               text NOT NULL DEFAULT 'draft'
                        CHECK (state IN ('draft', 'issued', 'sent', 'partly_paid', 'paid', 'cancelled', 'written_off')),
    series              text,
    number              text,
    issue_date          date,
    service_from        date,
    service_to          date,
    due_date            date,
    customer_snapshot   jsonb,
    seller_snapshot     jsonb,
    net                 numeric(14,2),
    vat                 numeric(14,2),
    gross               numeric(14,2),
    vat_breakdown       jsonb,
    notes               text,
    refers_to_invoice_id bigint REFERENCES invoices(id),
    document_id         text REFERENCES public.documents(id),
    xml_sha256          text,
    issued_by           text,
    issued_at           timestamptz,
    sent_at             timestamptz,
    sent_to             text,
    recurring_months    integer CHECK (recurring_months > 0),
    next_run            date,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (book_id, series, number)
);

CREATE TABLE invoice_lines (
    id               bigserial PRIMARY KEY,
    invoice_id       bigint NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    position         integer NOT NULL,
    description      text NOT NULL,
    quantity         numeric(14,3) NOT NULL,
    unit             text NOT NULL DEFAULT 'C62',   -- UN/ECE Rec. 20: C62 piece, HUR hour, DAY day, MON month
    unit_price       numeric(14,2) NOT NULL,
    discount_percent numeric(5,2) NOT NULL DEFAULT 0,
    vat_code         text NOT NULL,
    account          text,
    net              numeric(14,2)
);

CREATE TABLE invoice_payments (
    id             bigserial PRIMARY KEY,
    invoice_id     bigint NOT NULL REFERENCES invoices(id),
    paid_on        date NOT NULL,
    amount         numeric(14,2) NOT NULL,
    transaction_id bigint,
    note           text,
    UNIQUE (invoice_id, transaction_id)
);

CREATE TABLE payment_reminders (
    invoice_id  bigint NOT NULL REFERENCES invoices(id),
    level       integer NOT NULL,
    document_id text REFERENCES public.documents(id),
    sent_on     date NOT NULL,
    PRIMARY KEY (invoice_id, level)
);

-- An issued invoice never changes: only its state, payments and sending details may.
CREATE FUNCTION invoices_frozen() RETURNS trigger AS $$
BEGIN
    IF OLD.number IS NOT NULL AND (
        NEW.number IS DISTINCT FROM OLD.number OR NEW.series IS DISTINCT FROM OLD.series
        OR NEW.issue_date IS DISTINCT FROM OLD.issue_date OR NEW.net IS DISTINCT FROM OLD.net
        OR NEW.vat IS DISTINCT FROM OLD.vat OR NEW.gross IS DISTINCT FROM OLD.gross
        OR NEW.customer_snapshot IS DISTINCT FROM OLD.customer_snapshot
        OR NEW.seller_snapshot IS DISTINCT FROM OLD.seller_snapshot
        OR NEW.document_id IS DISTINCT FROM OLD.document_id
        OR NEW.customer_id IS DISTINCT FROM OLD.customer_id OR NEW.kind IS DISTINCT FROM OLD.kind
    ) THEN
        RAISE EXCEPTION 'An issued invoice cannot be changed; cancel it and issue a new one';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER invoices_frozen BEFORE UPDATE ON invoices FOR EACH ROW EXECUTE FUNCTION invoices_frozen();

CREATE FUNCTION invoices_no_delete() RETURNS trigger AS $$
BEGIN
    IF OLD.number IS NOT NULL THEN
        RAISE EXCEPTION 'An issued invoice cannot be deleted';
    END IF;
    RETURN OLD;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER invoices_no_delete BEFORE DELETE ON invoices FOR EACH ROW EXECUTE FUNCTION invoices_no_delete();

CREATE FUNCTION invoice_lines_frozen() RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM invoices WHERE id = COALESCE(NEW.invoice_id, OLD.invoice_id)
               AND number IS NOT NULL) THEN
        RAISE EXCEPTION 'The lines of an issued invoice cannot be changed';
    END IF;
    RETURN COALESCE(NEW, OLD);
END $$ LANGUAGE plpgsql;
CREATE TRIGGER invoice_lines_frozen BEFORE INSERT OR UPDATE OR DELETE ON invoice_lines
    FOR EACH ROW EXECUTE FUNCTION invoice_lines_frozen();
