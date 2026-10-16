<!-- screenpipe — AI that knows everything you've seen, said, or heard -->
<!-- https://screenpipe.com -->
# Reviewed workflow to a repeatable report

First review a procedure and export its approved snapshot from the [review desk](../workflow-review/README.md). There is no automatic approval flag. Then explicitly select the adapter below.

## Adapter contract: paid-order-report-v1

- Input: simple unquoted CSV, exact header `order_id,customer,total,status`.
- Preconditions: unique order IDs, nonempty customers, nonnegative amounts with at most two decimal places, and a single currency chosen by the reviewer. The CSV has no currency column; the adapter cannot verify that precondition.
- Accepted statuses: paid, pending and refunded. Sum paid rows only, per customer, using integer cents and rejecting values beyond safe precision.
- Exceptions: pending/refunded rows are excluded. Unknown statuses, duplicate IDs, malformed rows and spreadsheet-formula-like customer names are rejected.
- Output: a new local CSV and JSON receipt under `output/`. Source data is not overwritten. No network, payment, arbitrary shell or browser action is available.

```sh
bun run replay --approved local-data/approved.json --orders sample-data/orders.csv --adapter paid-order-report-v1
bun run replay --approved local-data/approved.json --orders sample-data/orders-second.csv --adapter paid-order-report-v1
bun run replay --approved local-data/approved.json --orders sample-data/orders-invalid.csv --adapter paid-order-report-v1
```

Expected: first input gives Atlas 150.00 and Beacon 80.00; second gives Atlas 10.30 and Cedar 45.00. Invalid input refuses the duplicate ID before writing a report. Each successful receipt records the reviewed procedure fingerprint, revision, reviewer and adapter.

The runner verifies snapshot integrity and completed review. It does not turn prose into executable code or prove that this adapter implements your SOP. Explicitly choosing it means you have compared its contract with the reviewed procedure. Add new adapters as small, tested code functions with a similarly clear contract.

A useful hackathon demonstration includes a second person's run, a second input, a failure case and the corrections needed to get a useful result. A sample passing is not a production automation commitment.
