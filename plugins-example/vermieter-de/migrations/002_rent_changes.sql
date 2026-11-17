-- Rent and advance payments change over time: each change applies from its first month.
CREATE TABLE rent_changes (
    tenancy_id bigint NOT NULL REFERENCES tenancies(id) ON DELETE CASCADE,
    valid_from date NOT NULL,
    rent       numeric(10,2) NOT NULL,
    advance    numeric(10,2) NOT NULL,
    PRIMARY KEY (tenancy_id, valid_from)
);
