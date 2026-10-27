-- Register PayProof's synthetic source systems in Zetaris (Lightning SQL).
-- Syntax follows the Zetaris Lightning SQL reference (CREATE LIGHTNING DATABASE /
-- CREATE LIGHTNING FILESTORE TABLE ... FORMAT CSV). NOT YET RUN against a live Zetaris:
-- replace <PATH> with where data/zetaris/*.csv is reachable from your Zetaris instance
-- (e.g. a mounted path or an s3a:// bucket) and run one statement at a time.
-- Generate the CSVs first: python3 scripts/export_zetaris_csv.py
-- Database name must match ZETARIS_DATABASE (default: payproof).

CREATE LIGHTNING DATABASE payproof DESCRIBE BY "PayProof synthetic commission-dispute sources";

CREATE LIGHTNING FILESTORE TABLE hris_records    FROM payproof FORMAT CSV OPTIONS (path "<PATH>/hris_records.csv",    header "true", inferSchema "false", escape "\"", multiLine "false");
CREATE LIGHTNING FILESTORE TABLE crm_records     FROM payproof FORMAT CSV OPTIONS (path "<PATH>/crm_records.csv",     header "true", inferSchema "false", escape "\"", multiLine "false");
CREATE LIGHTNING FILESTORE TABLE clm_records     FROM payproof FORMAT CSV OPTIONS (path "<PATH>/clm_records.csv",     header "true", inferSchema "false", escape "\"", multiLine "false");
CREATE LIGHTNING FILESTORE TABLE billing_records FROM payproof FORMAT CSV OPTIONS (path "<PATH>/billing_records.csv", header "true", inferSchema "false", escape "\"", multiLine "false");
CREATE LIGHTNING FILESTORE TABLE comp_records    FROM payproof FORMAT CSV OPTIONS (path "<PATH>/comp_records.csv",    header "true", inferSchema "false", escape "\"", multiLine "false");
CREATE LIGHTNING FILESTORE TABLE payroll_records FROM payproof FORMAT CSV OPTIONS (path "<PATH>/payroll_records.csv", header "true", inferSchema "false", escape "\"", multiLine "false");

-- Verify (these are exactly the statements PayProof sends, per system):
SELECT record_id, record_type, payload_json FROM payproof.crm_records WHERE case_key = 'CASE-1001' ORDER BY record_id;
