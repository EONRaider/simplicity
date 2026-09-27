# Prior session transcript (seeded for eval)

**User:** Why is our product page slow, and what should we do about it?

**Assistant:** Great question — there are actually several interacting factors here, so let me walk through them carefully, because the picture is a bit more nuanced than "the database is slow."

First, the most significant contributor, based on the trace you shared earlier, is the N+1 query pattern in `ProductController#show`. For every product variant, we issue a separate `SELECT` against `inventory_levels`, which means a product with 40 variants triggers 41 round trips to Postgres. Each round trip is individually fast (around 2–3 ms), but in aggregate that adds roughly 100 ms to the server response, and more under load because connection-pool contention compounds it. The fix here is relatively straightforward: eager-load the inventory association with `includes(:inventory_levels)`, which collapses those queries into a single `IN (...)` lookup.

Second, and this is somewhat related, the page renders the "Customers also bought" carousel synchronously. That carousel calls the recommendations service over HTTP, and the p95 latency of that service is currently about 450 ms. Because it blocks the main render, the entire page waits on it. It would be worth considering moving this to an asynchronous fragment — either lazy-loading it client-side after first paint, or rendering it via a Turbo Frame so the rest of the page can be delivered immediately. There's a trade-off here, of course: lazy-loading means a small layout shift unless we reserve space for the carousel, so we'd want to set a fixed min-height on the container.

Third, on the front end, the hero image is served as a 2.4 MB PNG at 3000×2000 pixels, even on mobile. Converting it to AVIF or WebP with responsive `srcset` sizes would likely cut the transferred bytes by 80–90% on phones, which directly improves Largest Contentful Paint. It's also worth noting that the image isn't marked with `fetchpriority="high"`, so the browser may discover it later than it should.

Fourth — and this is more of a secondary factor — our full-page cache is keyed on the session cookie, which effectively means every logged-in user gets a cache miss. If we instead key the cache on the product ID and a coarse "logged in or not" flag, and personalize the small cart widget via a separate request, we could dramatically raise the hit rate.

In terms of prioritization, I'd suggest tackling them in this order: the N+1 fix first (smallest change, clear win), then the carousel (largest single latency item), then the image (biggest user-perceived improvement on mobile), and finally the cache key change (largest architectural change, so it deserves its own review). Of course, it would be wise to measure after each change rather than shipping all four at once, so we can attribute improvements accurately.
