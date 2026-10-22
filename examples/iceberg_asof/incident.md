# INC-4471: analytics.orders catalog entry lost

Status: mitigated (files preserved, catalog entry not restored)
On call: data-platform

## Timeline (UTC)

- 2026-03-13 15:00  Bad 03-13 08:00 batch (wrong statuses, doubled amounts) found by Finance. Table rolled back.
- 2026-03-14 09:02  `orders-dedup` started (Spark, app-20260314090212-0031). It removes the duplicate order rows Finance reported on 03-13.
- 2026-03-14 09:10  `orders-dedup` driver killed by the node's OOM killer. Job marked FAILED by the scheduler. No retry: owner to rerun after review.
- 2026-03-14 09:30  Finance daily close. The close dashboards read `analytics.orders` directly.
- 2026-03-14 10:55  Ingest service added column `priority`. Its 11:00 merge committed normally.
- 2026-03-14 11:30  Scheduled `lake-maintenance` run on `analytics.*` tables completed (rewrite_manifests, then expire_snapshots with older_than = run time and retain_last = 1).
- 2026-03-14 12:00  Catalog database restored from the 02-27 backup during an unrelated outage. The backup predates `analytics.orders`, so the table's catalog entry is gone.
- 2026-03-14 12:40  Table directory copied from `s3://acme-lake/warehouse/analytics.db/orders/` to local disk for analysis. The copy is complete. Paths inside the metadata still point at the bucket.

## Open question from Finance

Which order rows did the 09:30 close read? Finance needs the exact rows to reconcile the close.
