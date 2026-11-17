-- Regular upkeep of a home: what, how often, when it was last done and when it is due next.
CREATE TABLE maintenance (
    id           bigserial PRIMARY KEY,
    owner_id     bigint NOT NULL,
    name         text NOT NULL,
    preset       text,                          -- an id from rules/maintenance.yaml, if any
    every_months integer NOT NULL CHECK (every_months BETWEEN 1 AND 240),
    last_done    date,
    next_due     date NOT NULL,
    notes        text,
    document_id  text REFERENCES public.documents(id) ON DELETE SET NULL,  -- the last invoice
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, name)
);
CREATE INDEX maintenance_owner ON maintenance (owner_id, next_due);
