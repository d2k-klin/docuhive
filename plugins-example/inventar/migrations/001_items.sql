-- What you own, where it is, and the documents about it.
CREATE TABLE locations (
    id        bigserial PRIMARY KEY,
    owner_id  bigint NOT NULL,
    name      text NOT NULL,
    parent_id bigint REFERENCES locations(id) ON DELETE SET NULL,
    UNIQUE (owner_id, name)
);

CREATE TABLE items (
    id               bigserial PRIMARY KEY,
    owner_id         bigint NOT NULL,
    shared           boolean NOT NULL DEFAULT false,
    name             text NOT NULL,
    category         text NOT NULL DEFAULT 'other',
    manufacturer     text,
    model            text,
    serial_number    text,
    location_id      bigint REFERENCES locations(id) ON DELETE SET NULL,
    assigned_to      text,
    purchase_date    date,
    price            numeric(12,2),
    currency         text NOT NULL DEFAULT 'EUR',
    quantity         integer NOT NULL DEFAULT 1,
    seller           text,
    warranty_until   date,
    warranty_source  text CHECK (warranty_source IN ('document', 'assumed', 'person')),
    state            text NOT NULL DEFAULT 'proposed'
                     CHECK (state IN ('proposed', 'active', 'sold', 'disposed', 'lost')),
    disposed_on      date,
    notes            text,
    business_flag    text CHECK (business_flag IN ('low_value', 'asset')),
    created_from_document_id text REFERENCES public.documents(id) ON DELETE SET NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX items_owner ON items (owner_id, state);

CREATE TABLE item_documents (
    item_id     bigint NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    document_id text NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    role        text NOT NULL CHECK (role IN ('receipt', 'warranty', 'manual', 'repair', 'photo', 'type_plate', 'other')),
    suggested   boolean NOT NULL DEFAULT false,   -- found by the plugin; a person confirms
    PRIMARY KEY (item_id, document_id)
);

-- "Not an item": the same thing from the same seller is not proposed again.
CREATE TABLE dismissed (
    owner_id bigint NOT NULL,
    seller   text NOT NULL,
    name     text NOT NULL,
    PRIMARY KEY (owner_id, seller, name)
);
