-- One claim per medical bill: whether it was submitted and what came back.
CREATE TABLE claims (
    id                 bigserial PRIMARY KEY,
    owner_id           bigint NOT NULL,
    document_id        text NOT NULL UNIQUE REFERENCES public.documents(id) ON DELETE CASCADE,
    state              text NOT NULL DEFAULT 'open'
                       CHECK (state IN ('open', 'submitted', 'reimbursed', 'not_claimed')),
    submitted_on       date,
    reimbursed         numeric(12,2),
    notice_document_id text REFERENCES public.documents(id) ON DELETE SET NULL,
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX claims_owner ON claims (owner_id, state);

-- Lines of a reimbursement notice that matched no bill, to match by hand.
CREATE TABLE unmatched (
    id                 bigserial PRIMARY KEY,
    owner_id           bigint NOT NULL,
    notice_document_id text NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    bill_number        text,
    treatment_date     date,
    billed             numeric(12,2),
    reimbursed         numeric(12,2) NOT NULL,
    UNIQUE (notice_document_id, bill_number, treatment_date, billed, reimbursed)
);
