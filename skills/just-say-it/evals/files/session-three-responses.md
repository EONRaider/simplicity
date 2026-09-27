# Prior session transcript (seeded for eval)

**User:** Our CI takes 25 minutes. Where does the time go?

**Assistant:** I pulled the timings from the last 20 runs of `.github/workflows/ci.yml`. The breakdown is roughly: dependency install 6 minutes (no caching configured for `~/.cache/pip`), the test suite 14 minutes (run serially in one job), the Docker image build 4 minutes (rebuilt from scratch every time because the `COPY . .` line sits above the `pip install` layer, invalidating the cache on every commit), and about 1 minute of checkout and setup. So the test suite is the biggest chunk, but the install step and the Docker layer ordering are pure waste that's cheap to fix.

**User:** What would you change first?

**Assistant:** I'd start with the two cheap wins, since they need no test changes at all. One: add `actions/setup-python`'s built-in pip cache (`cache: pip`), which should bring install down from 6 minutes to under 1 on a warm cache. Two: reorder the Dockerfile so `COPY requirements.txt` and `pip install` come before `COPY . .`, which lets Docker reuse the dependency layer unless requirements actually change — that should take the image build from 4 minutes to about 1. Together that's roughly 8 minutes saved with a very low risk of breaking anything. After that, I'd look at the test suite, which is the bigger but riskier project.

**User:** And the tests?

**Assistant:** For the tests, the main lever is parallelism. The suite is 1,900 tests, and the slowest 5% account for about 40% of the runtime — mostly integration tests that spin up a real Postgres container per test module. Two changes would help: first, run `pytest -n auto` with `pytest-xdist` to use all 4 runner cores, which typically gives a 2.5–3× speedup on a suite like this, though we'd need to make sure tests don't share a database name (they currently all use `test_app`, so we'd switch to a per-worker name like `test_app_gw0`). Second, split the job into a matrix of 3 shards with `pytest-split`, using stored durations so each shard gets balanced work. Combined, the test stage could drop from 14 minutes to around 4. The risk is flaky tests surfacing once they run concurrently — I'd expect a few ordering bugs to show up, which is honestly a good thing to find.
