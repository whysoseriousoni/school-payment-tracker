-- GENERATED reference of the schema produced by data_management/migrations.
-- Do not run this file; it is documentation. Regenerate after adding a migration.

CREATE TABLE academic_year (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    label           TEXT    NOT NULL UNIQUE,
    start_date      DATE    NOT NULL,
    end_date        DATE    NOT NULL,
    is_current      INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0, 1)),
    inserted_on     DATETIME NOT NULL,
    updated_on      DATETIME NOT NULL,
    CHECK (end_date > start_date)
);

CREATE TABLE app_setting (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_on  DATETIME NOT NULL
);

CREATE TABLE app_user (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('ADMIN', 'BILLER')),
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    last_login_on DATETIME,
    inserted_on   DATETIME NOT NULL,
    updated_on    DATETIME NOT NULL
);

CREATE TABLE fee_structure (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    academic_year_id     INTEGER NOT NULL REFERENCES academic_year (id) ON DELETE RESTRICT,
    student_class        TEXT    NOT NULL,
    fee_type             TEXT    NOT NULL CHECK (fee_type IN ('TUITION', 'VAN')),
    monthly_amount_paise INTEGER NOT NULL CHECK (monthly_amount_paise >= 0),
    is_active            INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    inserted_on          DATETIME NOT NULL,
    updated_on           DATETIME NOT NULL,
    UNIQUE (academic_year_id, student_class, fee_type)
);

CREATE TABLE guardian (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL CHECK (trim(name) <> ''),
    mobile_number   TEXT,
    year_of_birth   INTEGER,
    inserted_on     DATETIME NOT NULL,
    updated_on      DATETIME NOT NULL
);

CREATE TABLE identifier (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    identifier_type TEXT    NOT NULL,
    ciphertext      TEXT,
    nonce           TEXT,
    last_4_digits   TEXT    NOT NULL CHECK (length(last_4_digits) = 4 AND last_4_digits NOT GLOB '*[^0-9]*'),
    key_version     INTEGER NOT NULL DEFAULT 1,
    inserted_on     DATETIME NOT NULL,
    updated_on      DATETIME NOT NULL, fingerprint TEXT,
    CHECK ((ciphertext IS NULL) = (nonce IS NULL))
);

CREATE TABLE payment (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no      TEXT    NOT NULL UNIQUE,
    student_id      INTEGER NOT NULL REFERENCES student (id) ON DELETE RESTRICT,
    enrollment_id   INTEGER NOT NULL REFERENCES student_enrollment (id) ON DELETE RESTRICT,
    paid_on         DATE    NOT NULL,
    amount_paise    INTEGER NOT NULL CHECK (amount_paise > 0),
    payment_method  TEXT    NOT NULL,
    payment_notes   TEXT,
    billing_name    TEXT,
    notes           TEXT,
    amount_in_words TEXT    NOT NULL,
    collected_by    TEXT,
    is_voided       INTEGER NOT NULL DEFAULT 0 CHECK (is_voided IN (0, 1)),
    void_reason     TEXT,
    voided_on       DATETIME,
    voided_by       TEXT,
    inserted_on     DATETIME NOT NULL,
    updated_on      DATETIME NOT NULL,
    CHECK (is_voided = 0 OR (void_reason IS NOT NULL AND trim(void_reason) <> ''))
);

CREATE TABLE payment_allocation (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id   INTEGER NOT NULL REFERENCES payment (id) ON DELETE CASCADE,
    fee_due_id   INTEGER NOT NULL REFERENCES student_fee_due (id) ON DELETE RESTRICT,
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    UNIQUE (payment_id, fee_due_id)
);

CREATE TABLE receipt_counter (
    academic_year_id INTEGER PRIMARY KEY REFERENCES academic_year (id) ON DELETE RESTRICT,
    last_number      INTEGER NOT NULL CHECK (last_number >= 0)
);

CREATE TABLE schema_migrations ( version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_on TEXT NOT NULL);

CREATE TABLE student (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    admission_no    TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    name            TEXT    NOT NULL CHECK (trim(name) <> ''),
    date_of_birth   DATE,
    category        TEXT,
    status          TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'LEFT', 'PASSED_OUT')),
    date_of_join    DATE,
    class_joined    TEXT,
    date_of_leaving DATE,
    identifier_id   INTEGER UNIQUE REFERENCES identifier (id) ON DELETE SET NULL,
    notes           TEXT,
    inserted_on     DATETIME NOT NULL,
    updated_on      DATETIME NOT NULL
);

CREATE TABLE student_enrollment (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id       INTEGER NOT NULL REFERENCES student (id) ON DELETE RESTRICT,
    academic_year_id INTEGER NOT NULL REFERENCES academic_year (id) ON DELETE RESTRICT,
    student_class    TEXT    NOT NULL,
    section          TEXT    NOT NULL,
    roll_no          INTEGER CHECK (roll_no IS NULL OR roll_no > 0),
    outcome          TEXT    CHECK (outcome IS NULL OR outcome IN ('PROMOTED', 'RETAINED', 'LEFT', 'PASSED_OUT')),
    inserted_on      DATETIME NOT NULL,
    updated_on       DATETIME NOT NULL,
    UNIQUE (student_id, academic_year_id),
    UNIQUE (academic_year_id, student_class, section, roll_no)
);

CREATE TABLE student_fee_due (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    enrollment_id    INTEGER NOT NULL REFERENCES student_enrollment (id) ON DELETE RESTRICT,
    fee_type         TEXT    NOT NULL,
    fee_month        DATE,
    description      TEXT,
    amount_due_paise INTEGER NOT NULL CHECK (amount_due_paise >= 0),
    inserted_on      DATETIME NOT NULL,
    updated_on       DATETIME NOT NULL,
    -- Recurring fees are monthly; every other fee type is a one-off charge.
    CHECK ((fee_type IN ('TUITION', 'VAN')) = (fee_month IS NOT NULL)),
    CHECK (fee_month IS NULL OR strftime('%d', fee_month) = '01')
);

CREATE TABLE student_guardian (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      INTEGER NOT NULL REFERENCES student (id) ON DELETE CASCADE,
    guardian_id     INTEGER NOT NULL REFERENCES guardian (id) ON DELETE CASCADE,
    relation_type   TEXT    NOT NULL,
    is_primary      INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    inserted_on     DATETIME NOT NULL,
    updated_on      DATETIME NOT NULL,
    UNIQUE (student_id, guardian_id)
);

CREATE INDEX ix_allocation_fee_due ON payment_allocation (fee_due_id);

CREATE INDEX ix_enrollment_year_class ON student_enrollment (academic_year_id, student_class, section);

CREATE INDEX ix_fee_due_month ON student_fee_due (fee_month);

CREATE INDEX ix_guardian_mobile ON guardian (mobile_number);

CREATE INDEX ix_payment_enrollment ON payment (enrollment_id);

CREATE INDEX ix_payment_paid_on ON payment (paid_on);

CREATE INDEX ix_payment_student ON payment (student_id);

CREATE INDEX ix_student_guardian_guardian ON student_guardian (guardian_id);

CREATE INDEX ix_student_name ON student (name COLLATE NOCASE);

CREATE UNIQUE INDEX ux_academic_year_single_current ON academic_year (is_current) WHERE is_current = 1;

CREATE UNIQUE INDEX ux_fee_due_recurring ON student_fee_due (enrollment_id, fee_type, fee_month)
    WHERE fee_month IS NOT NULL;

CREATE UNIQUE INDEX ux_identifier_fingerprint ON identifier (fingerprint) WHERE fingerprint IS NOT NULL;

CREATE UNIQUE INDEX ux_student_guardian_one_primary ON student_guardian (student_id) WHERE is_primary = 1;

CREATE TRIGGER trg_allocation_immutable
BEFORE UPDATE ON payment_allocation
BEGIN
    SELECT RAISE(ABORT, 'Allocations are immutable; void the payment instead');
END;

CREATE TRIGGER trg_allocation_rules
BEFORE INSERT ON payment_allocation
BEGIN
    SELECT RAISE(ABORT, 'Cannot allocate a voided payment')
    WHERE (SELECT is_voided FROM payment WHERE id = NEW.payment_id) = 1;

    SELECT RAISE(ABORT, 'Payment and fee due belong to different enrollments (no carry-over across years)')
    WHERE (SELECT enrollment_id FROM payment WHERE id = NEW.payment_id)
       <> (SELECT enrollment_id FROM student_fee_due WHERE id = NEW.fee_due_id);

    SELECT RAISE(ABORT, 'Allocations exceed the payment amount')
    WHERE (SELECT COALESCE(SUM(amount_paise), 0) FROM payment_allocation WHERE payment_id = NEW.payment_id)
          + NEW.amount_paise
        > (SELECT amount_paise FROM payment WHERE id = NEW.payment_id);

    SELECT RAISE(ABORT, 'Allocations exceed the amount due')
    WHERE (SELECT COALESCE(SUM(a.amount_paise), 0)
             FROM payment_allocation a JOIN payment p ON p.id = a.payment_id
            WHERE a.fee_due_id = NEW.fee_due_id AND p.is_voided = 0)
          + NEW.amount_paise
        > (SELECT amount_due_paise FROM student_fee_due WHERE id = NEW.fee_due_id);
END;

CREATE TRIGGER trg_fee_due_not_below_paid
BEFORE UPDATE OF amount_due_paise ON student_fee_due
WHEN NEW.amount_due_paise < (
    SELECT COALESCE(SUM(a.amount_paise), 0)
      FROM payment_allocation a JOIN payment p ON p.id = a.payment_id
     WHERE a.fee_due_id = NEW.id AND p.is_voided = 0)
BEGIN
    SELECT RAISE(ABORT, 'Amount due cannot be reduced below the amount already paid');
END;

CREATE TRIGGER trg_payment_core_fields_immutable
BEFORE UPDATE OF student_id, enrollment_id, amount_paise, receipt_no ON payment
WHEN NEW.student_id <> OLD.student_id OR NEW.enrollment_id <> OLD.enrollment_id
  OR NEW.amount_paise <> OLD.amount_paise OR NEW.receipt_no <> OLD.receipt_no
BEGIN
    SELECT RAISE(ABORT, 'Payment amount, student, enrollment and receipt number cannot change; void and re-issue');
END;

CREATE TRIGGER trg_payment_no_delete
BEFORE DELETE ON payment
BEGIN
    SELECT RAISE(ABORT, 'Payments cannot be deleted; void them instead');
END;

CREATE TRIGGER trg_payment_no_unvoid
BEFORE UPDATE OF is_voided ON payment
WHEN OLD.is_voided = 1 AND NEW.is_voided = 0
BEGIN
    SELECT RAISE(ABORT, 'A voided payment cannot be restored');
END;

CREATE VIEW v_fee_due_status AS
SELECT d.id                 AS fee_due_id,
       d.enrollment_id,
       e.student_id,
       e.academic_year_id,
       e.student_class,
       e.section,
       d.fee_type,
       d.fee_month,
       d.description,
       d.amount_due_paise,
       COALESCE(SUM(CASE WHEN p.is_voided = 0 THEN a.amount_paise END), 0) AS amount_paid_paise,
       d.amount_due_paise
         - COALESCE(SUM(CASE WHEN p.is_voided = 0 THEN a.amount_paise END), 0) AS balance_paise
  FROM student_fee_due d
  JOIN student_enrollment e ON e.id = d.enrollment_id
  LEFT JOIN payment_allocation a ON a.fee_due_id = d.id
  LEFT JOIN payment p ON p.id = a.payment_id
 GROUP BY d.id;
