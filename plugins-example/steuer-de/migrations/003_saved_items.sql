-- Lines written again and again (an hour of consulting, the monthly fee): kept per book and
-- added to a draft with one click. A saved item is a template; changing it never changes an
-- invoice that already used it.
CREATE TABLE saved_items (
    id          bigserial PRIMARY KEY,
    book_id     bigint NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    description text NOT NULL,
    unit        text NOT NULL DEFAULT 'C62',
    unit_price  numeric(14,2) NOT NULL,
    vat_code    text NOT NULL,
    UNIQUE (book_id, description)
);
