# Prior session transcript (seeded for eval)

**User:** We need to move our file uploads off the app server. What's the plan?

**Assistant:** Right now uploads land on the app server's local disk under `/var/app/uploads` and are served by Nginx. That breaks as soon as we run more than one app instance, and it's why last month's deploy lost the files uploaded during the rollout. The plan I'd propose has three parts.

The storage move itself is straightforward: write new uploads to an S3-compatible bucket through the existing `Storage` interface in `lib/storage.rb`, which already abstracts the disk calls, so it's mostly a new adapter class plus configuration. Files would be served through presigned URLs with a 15-minute expiry instead of through Nginx, which also lets us drop the `location /uploads` block.

Migrating the existing 180 GB of files is the slow part. A background job can copy them over in batches and flip each record's `storage_key` once its copy is verified by checksum. At the throughput we measured, that's about 9 hours, so it can run overnight while the app keeps reading from whichever location each record points to.

There are two things I can't decide for you, though. First, which provider: AWS S3 is the default choice and integrates with our existing IAM setup, but Cloudflare R2 has no egress fees, which matters because about 70% of our upload traffic is downloads of large PDFs. Second, whether to keep the local copies after the migration as a fallback for 30 days, which costs disk space but makes rollback trivial, or delete them as soon as each checksum verifies. I'd lean toward R2 and keeping the 30-day fallback, but both depend on budget and how risk-averse you want this to be.
