-- Regular payments a person said are not a contract: not suggested again.
CREATE TABLE dismissed_payees (
    owner_id bigint NOT NULL,
    payee    text NOT NULL,
    PRIMARY KEY (owner_id, payee)
);
