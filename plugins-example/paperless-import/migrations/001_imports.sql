-- Which Paperless documents were imported, so an import can stop and continue without doubles.
CREATE TABLE imported (
    owner_id     bigint NOT NULL,
    paperless_id bigint NOT NULL,
    document_id  text REFERENCES public.documents(id) ON DELETE SET NULL,
    status       text NOT NULL CHECK (status IN ('imported', 'duplicate', 'failed')),
    error        text,
    title        text,
    at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_id, paperless_id)
);

CREATE TABLE runs (
    id          bigserial PRIMARY KEY,
    owner_id    bigint NOT NULL,
    state       text NOT NULL CHECK (state IN ('running', 'finished', 'stopped', 'failed')),
    total       integer NOT NULL DEFAULT 0,
    done        integer NOT NULL DEFAULT 0,
    error       text,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
