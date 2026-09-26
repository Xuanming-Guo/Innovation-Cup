# Authored synthetic replay fixtures

`tiny-no-impact.v1.json` is an authored example of an unchanged starting schedule
for seed 17, generated once by `scripts/generate_replay_example.py`. It was **not
captured from Coordination Engine**. The replay adapter reads those stored blocks
verbatim and refuses any different canonical input digest. It never constructs,
repairs or chooses a product schedule. Changing seed without matching versioned
evidence is an explicit failed run.

Always display **REPLAY — NOT A PRODUCT RESULT**. The observation has evidence
class `recorded_replay` to match specification 0.5.0, and a more precise provenance
field `authored_synthetic_example_not_product_capture` to avoid implying that a
real product recording exists. Product-result cells remain `NOT_RUN`.

This is one smoke case; it does not establish realistic Change A/B behavior,
privacy, fair product mapping or a hand-reviewed golden benchmark suite.

## Connected benchmark-2 development replay

`tiny-connected.v2.json` is the current immutable A → B recording for tiny,
seed 17. `scripts/author_benchmark_replay.py` authors explicit stored outcomes,
actor requests and manager/Security/Delivery projections; it imports no scheduler
or scorer. The adapter binds exact initial, event, canonical import and previous
result hashes, requires the issued responses, and exports the stored evidence
verbatim. Product workflow stages are `NOT_AVAILABLE`.

`tiny-connected.v1.json` is retained historical evidence. Version 2 binds the new
source-confirmed deadline records; earlier artifacts are not relabelled. Other
seeds/presets have no matching connected replay and report that absence. Neither
recording can enter product headline cells. See `evals/golden-review.md` for the
manual arithmetic/trace review and its limits; no real product capture exists.
