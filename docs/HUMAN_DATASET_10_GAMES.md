# Ten human games: passenger buses and money management

Planned October 5, 2026. The owner selected passenger buses and money management.
Progress: **10/10 games captured, preserved and verified**. Games 01–07 supply
18, 24, 22, 15, 39, 39 and 29 training choices respectively (**186 total**).
Game 08 supplies **34 development choices** and games 09–10 **64 test choices**
(31 and 33), giving **284 across the three partitions**.
The seven-game assembler passes, and a new 256-update CUDA fit matches 128/186
training choices and 41/64 held-out choices. Repayments explain 20 of the 22
additional correct test choices relative to the four-game model: other actions
improve from 19/44 to 21/44. Station insertions remain 6/43 on training examples.
An independent audit clears all 43 insertion targets for aliases, row alignment
and shuffled-row invariance. Separate insertion-only fits reach 12/43 at 256
updates and 21/43 at 1,000; both remain below memorization.
The completed 50-attempt-per-actor saved comparison covers four frozen neural
policies and a script: 250 final native saves, 247 full budgets and three
explicit interface failures. The new policy delivers in 24/25 sampled and
0/25 greedy cases, with mean operating profit -9,484.7 and no sustained
profitable service. The script delivers in 48/50, averages +3,623.16 and sustains
profitable service in 44/50. All native ledgers and save hashes pass independent
verification. See [the final comparison](DEVELOPMENT.md#ten-game-training-and-saved-benchmark-october-5).
The owner earlier requested a pilot
training run on the first four games while waiting to play games 05–10. Compare a fresh four-game
CUDA fit with an equal-update original one-game control and the preserved
1,000-update model. This does not change the proposed whole-game splits below.
The completed pilot fits 53/79 exact choices, but live route setup and finance
remain unresolved. See the pilot results in [the development guide](DEVELOPMENT.md#four-game-pilot-requested-before-the-next-six-recordings).

The owner clarified the protocol after game 01: **two routes per game; add more
than one bus when it makes sense**. Fleet size is a management choice, not a fixed
one-bus restriction. Preserve the decision context for additional buses.

## What this campaign should answer

Can varied human demonstrations improve route setup and financial choices beyond
the current single-recording bus fit, and reduce repeated purchases and route edits
in live play? Ten games are an initial experiment, not a promised sufficient
dataset. Count usable decisions and state diversity alongside game count.

The October 2 bus recording remains a separate regression fixture: 12 supported
training decisions, correct initial route sequences, followed by overbuying and
negative operating profit in four short supplied-context continuations. Preserve
the original recording, failed fits and selected weights.

## Collection design

Use ten independent fresh starts with distinct recorded seeds, the existing isolated
64x64 temperate recorder, six towns and a 1950 start. Keep the capture engine and
settings consistent. Vary route choices, demand, costs and financial state through
normal play. Build exactly two passenger routes per game. Choose when to add buses
to those routes from actual service, demand and available cash; route expansion in
this campaign means additional capacity on the two routes. Use simple two-stop
independent orders initially. Notes should describe why a decision made sense at
the time, especially why another bus was needed or a purchase was deferred.

The focuses below are opportunities to observe, not instructions to borrow,
repay, buy extra buses or manufacture mistakes when they are unnecessary.

| Game | Actual/planned seed | Split | Focus |
| --- | --- | --- | --- |
| 01 | 1268495509 (verified) | Training | Two-route setup and three running buses; 18 choices, all 11 checks pass. |
| 02 | 212758682 (verified) | Training | Two routes, four buses; 24 supported choices and all 11 replay checks pass. |
| 03 | 476793754 (verified) | Training | Avoided the isolated largest town; two separate routes, two buses each and two repayments; 22 supported choices. |
| 04 | 392546014 (verified) | Training | Simple grouping of nearby major towns; two routes, three buses and 15 supported choices. |
| 05 | 2057442348 (verified) | Training | Two largest cities, two stops in the largest; six buses and ten repayments; 39 supported choices. |
| 06 | 2020301813 (verified) | Training | Reassigned a running bus between routes, balancing two buses per route; ten repayments and 39 supported choices. |
| 07 | 1652481928 (verified) | Training | Delayed further investment, three running buses and full repayment; 29 supported choices. |
| 08 | 1070616272 (verified) | Development | Scaled fleet using passenger queues; five buses with a 3/2 route allocation and 34 supported choices. |
| 09 | 1846900543 (verified) | Test | Scaled five-bus network across three stops; 31 supported choices, excluded from training and selection. |
| 10 | 1836455473 (verified) | Test | Two stops in the larger city and scaled fleet; 33 supported choices, excluded from training and selection. |

All seeds above are the actual recorded values, preserved in the campaign ledger
and checked for independence before dataset assembly. The existing shortcut used
automatic random seeds; no manual seed entry was needed.

Treat every checkpoint, prefix and continuation from a game as belonging to that
game's split. Never randomly split individual commands across training and test.
Repeated map seeds or overlapping recordings cannot count as independent games.
Qualify capture/replay integrity for test games, but do not use their decisions
or economic outcomes to choose features, rewards, epochs or model weights.

Game 01 took about five minutes of recorded wall time. There is no fixed session
length requirement: favor coherent service and management decisions over long
idle sessions or clicking to meet a quota. A final save should follow
observed deliveries and a fleet/finance review, not merely initial construction.

## Batch workflow

1. Check the installed recorder still targets OpenTTD 15.3; a version change needs
   requalification. Use the existing isolated session paths.
2. The owner wants to play all ten games consecutively. Complete one fresh recorder
   session per game, saving and quitting normally before launching the next.
3. Preserve each completed capture. The default plan is to audit after the batch;
   perform earlier verification when the owner requests it, as for game 02 before
   game 03. Report accepted labels and exclusions by operation for all ten games.
4. Resolve missing representations before training from the affected commands.
   Road/stop construction and chosen waiting may require interface extensions;
   keep their raw evidence so collected work can be used after qualification.
5. Assign the proposed whole-game splits before model training. Freeze the model
   selection protocol and evaluation budget before using the test games. A partial
   or failed capture is preserved and reported separately from verified games.

## What the current tools capture

The recorder retains an initial save, native command log, periodic/manual/exit
saves, seed, executable/configuration identities and optional rationale notes.
It creates a unique session directory per launch. Opening windows, mouse movement,
reasoning and video are not captured automatically.

The exact `orders-v1` label importer currently recognizes bus purchases, starts,
station-order insertion, loading changes, independent order copying/deletion,
ordinary 10,000 loan changes and certain road-depot construction commands.
Recognition does not guarantee a label: the exact command must match an exposed
legal candidate and succeed with verified accounting. Some depots fall outside
the retained candidate quota. Road building and bus-stop construction currently
replay as evidence without exact policy labels.

Stay within the initial bus model and simple ordinary station orders while
qualifying this slice. Shared orders, vehicle cloning, unsupported flags and
long/complex order lists need separate support. The current order interface has
a four-order limit. Start commands are supported; stopping a running vehicle is
not the same supported label. Do not assume every fleet-management click trains
the network. Preserve useful unsupported actions for future interface work.

**Chosen waiting needs an explicit recording mechanism.** Inter-command silence
can include thinking, inspecting windows or doing nothing. It cannot become a
WAIT label by inference. Before treating waiting as trainable, capture the human's
explicit decision, its tick and chosen horizon, and replay its public observation,
legal mask and resulting step under versioned semantics. Ordinary notes and
checkpoint names can record intent now, but are not model-ready WAIT labels.

The existing `bus-routes` lesson fixes Full load any cargo at both endpoints.
Use it for initial route setup. Games about broader management need a campaign
guide rather than pretending that this setting is always optimal. Changing load
settings can be logged, but each variant still needs exact replay qualification.

## Human session routine

Launch one fresh recording from the checkout. With an automatically selected seed:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/dev/record_human.ps1
```

1. Keep the initial snapshot intact and use one map for the session.
2. For each initial route, save a unique `route-1-ready`/`route-2-ready` checkpoint
   before starting its bus, then `route-1-service`/`route-2-service` after delivery.
3. At meaningful fleet or finance reviews, note the game date and bus/route:
   cash, debt, queues, vehicle load/profit, alternatives, choice and reason.
   Capture what was available at the time; later outcomes belong in a separate note.
4. Save uniquely named checkpoints around meaningful bus additions, repayment or
   corrective decisions. Keep natural mistakes and their corrections in the log.
5. Save `final` once, then quit normally so the recorder finalizes its inventory.
   Use a fresh name instead of overwriting checkpoints; never reload or restart
   using the same session configuration because startup truncates the command log.

Add `-Seed` to use a proposed fixed seed. This general-session launch does not
create the bus lesson's notes template; keep brief dated management notes in a
separate text file or chat. The existing recording shortcut is also suitable.
Do not run the ten launches automatically: each requires human play and review.

## Collection progress

Game 01 is session `20261005-100753-human-7a080369`, seed 1268495509, OpenTTD 15.3,
captured October 5 from 10:07:53 to 10:12:53 EDT. The recorder completed with exit
code zero. Its raw log contains 36 command records (including setup/control) and
seven failed/estimate records; these are not verified training-label counts.

All 14 allowlisted files, including five saves, were preserved byte-for-byte in
`%LOCALAPPDATA%/OpenTTD-RL/demonstrations/completed/20261005-100753-human-7a080369-campaign-game-01/`.
The final manual checkpoint is `Garfingburg Transport, 1954-01-07.sav`, marker 44;
its saved state now matches native replay on all 11 checks. The separate exit save
is retained. The immutable `preservation.json` retains the capture-time pending
status and file hashes; the campaign ledger records the later replay result.
The runtime ledger is
`%LOCALAPPDATA%/OpenTTD-RL/demonstrations/campaigns/human-bus-finance-20261005/campaign.json`.
Original captures remain intact.

The owner's retrospective game 01 route-selection rationale: "On game 1 i looked
for the biggest towns closest to each other to build my first route then the
closest town to either of those cities". This reports prioritizing large nearby
towns for the first route, then the closest additional town to either endpoint.
The verbatim statement and interpretation are attached to game 01 in the runtime
ledger, under `annotations/game-01-route-selection.json`. Native town identities
remain unestablished; exact supported commands are now replay-verified. The note is rationale rather
than an inferred policy label or captured GUI activity.

Game 02 is session `20261005-101658-human-2eeb36f1`, seed 212758682, captured
October 5 from 10:16:58 to 10:21:04 EDT. All 14 capture files were hash-preserved;
the Linux transfer was also verified. Native replay matches the final manual save
`Brunston Transport, 1954-08-23.sav`, log marker 48, on all 11 state/accounting
checks. All 36 replayed commands succeeded. The consumer accepts **24 examples**:
four purchases, eight station insertions, eight Full load any changes and four
starts. Eighteen records remain explicitly excluded; no WAIT labels are inferred.

The final checkpoint has four running buses: three on stations 0/1 and one on
stations 1/2, with Full load any cargo at all eight endpoints. Cash is 100,745 and
loan principal remains 100,000. Game 02 contains no borrowing/repayment labels.
No model training ran. Dataset and native reports are under
`/home/imsa/.local/share/openttd-rl/runs/human-campaign-20261005/game-02/`.
The human-readable verification report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-02/verification.md`.

The owner's retrospective game 02 explanation: "on game two i focus on closest
cities next to each other and focused on making the most popular route have more
then 1 bus". This reports proximity-based route selection and assigning extra
buses to the route judged most popular. The verified final fleet has three buses
on one route and one on the other; the signal used to judge popularity is pending
clarification. The verbatim note is attached through the runtime ledger at
`annotations/game-02-route-selection-and-capacity.json`, separate from the exact
command labels and replay evidence.

Game 03 is session `20261005-113936-human-24383522`, seed 476793754, captured
October 5 from 11:39:36 to 11:43:58 EDT. The recorder completed with exit code
zero, 44 command records and eight failed/estimate records. All 14 capture files,
including five saves, were preserved and the 15-file Linux transfer matches its
hashes. The final manual checkpoint is `Ginthill Transport, 1956-03-08.sav`,
log marker 56. All 11 native equality/accounting checks pass; all 42 replayed
commands succeeded. There are **22 supported choices**: four purchases, five
station insertions, four Full load any changes, two independent order copies,
one deletion, four starts and two repayments of 10,000 each. Twenty-eight records
are excluded: 17 replayed commands without exact policy actions, eight failed or
estimate records and three depot commands outside the retained legal candidates.

The checkpoint confirms two depots and two disjoint station pairs, 0/1 and 2/3,
with two running buses per route. All eight endpoints use Full load any cargo.
Cash is 101,020 and loan principal is 80,000, down from 100,000. No WAIT labels
are inferred. Reports and the dataset are under the runtime's
`runs/human-campaign-20261005/game-03/`; the successful replay is
`replay-manual-linkgraph-v2/`. The existing consumer accepts all 22 examples with
`signed-log-orders-v2`, without fitting a model. The Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-03/verification.md`.

The first two replay attempts are preserved as failures. The isolated replay
engine was repaired to let upstream `StateGameLoop` poll its own link-graph
pause, with or without the command-during-pause marker. It never clears pauses
itself. Native controls prove that a human pause, including one combined with a
link-graph pause, still fails when a future event requires time. Game 02 also
passes all 11 checks with the repaired engine and retains its original 24 labels.

The owner's retrospective game 03 explanation: "On three i avoided the largest
city because it was the furthest away from other towns. I did two bus depos and
two seperate routes with 2 buses running on each route this time. this shows that
you have to evaluate whats on the map first before laying down routes". This
reports weighing town population against proximity before construction, rather
than choosing the largest town automatically. The note reports two depots and
two separate routes with two buses each, confirmed by native replay. Its verbatim
text is hash-bound in the runtime ledger at
`annotations/game-03-map-selection-and-fleet.json`; native
verification of the fleet is separate from the human explanation. Town matching
and any numeric selection rule remain unestablished. The rationale does not
create construction or policy labels that the current interface cannot represent.

Game 04 is session `20261005-123821-human-71704373`, seed 392546014, captured
October 5 from 12:38:22 to 12:41:37 EDT, with exit code zero. All 14 capture files
and the 15-file Linux transfer match their hashes. Its raw log has 33 command
records and six failed/estimate records. Native replay matches the final manual
save `Plontford Transport, 1952-10-26.sav`, marker 43, on all 11 checks; all 31
replayed commands succeeded. The consumer accepts **15 choices**: three purchases,
four inserts, four Full load any changes, one independent copy and three starts.
Twenty-two records are excluded (15 without exact policy actions, six failed or
estimate entries and one depot outside the retained legal candidates).

The checkpoint confirms one depot, two buses on stations 0/1 and one on 1/2.
All three buses are running with Full load any at all six endpoints. Cash is
100,890 and loan principal stays at 100,000; there are no finance or WAIT labels.
Reports and the dataset are under the runtime's
`runs/human-campaign-20261005/game-04/`. The Windows verification report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-04/verification.md`.

The owner's retrospective game 04 explanation: "game 4 is done, I have completed
it, These routes were very simple closest major towns grouped together". This
records grouping nearby major towns into simple routes. The exact annotation is
hash-bound in the runtime ledger at `annotations/game-04-nearby-major-towns.json`.
Its meaning of "major", native town matching and any numeric selection rule remain
unestablished; the explanation is separate from the native command labels.

Game 05 is session `20261005-152914-human-b8b97f37`, seed 2057442348, captured
October 5 from 15:29:14 to 15:40:31 EDT on OpenTTD 15.3, with exit code zero.
Its 17 allowlisted files include eight saves; all 18 runtime transfer files match
their hashes. The raw log has 55 commands and seven failed/estimate records.
Native replay matches `Kinborough Transport, 1967-02-10.sav`, marker 69, on all
11 checks; all 53 replayed commands succeed. The existing consumer accepts
**39 choices**: five buys, five inserts, five Full load any changes, six starts,
four independent copies, three deletions, one loading-mode-0 change and ten
repayments of 10,000. Twenty-one records are excluded, including one successful
vehicle clone without an exact policy action. No waiting or construction is
invented as supervision.

The final save has three distinct stops, one depot and six running buses: four
on stations 0/1 and two on 0/2 (direction can differ). All lists are independent
and have two station orders. One endpoint on bus 5 uses loading mode 0; the
other eleven endpoints use Full load any. Cash is 110,424 and loan principal is
zero. Ten verified repayments decrease cash and loan by 10,000 each with zero
command cost. These are human outcomes over the recorded game's 462,474 ticks,
not outcomes of a neural run; finance/cargo counters remain checkpoint snapshots.

The owner's exact retrospective explanation: "game 5 is done. I used the two
largest cities I built 2 stops in the largest city not just one". The annotation
is hash-bound at `annotations/game-05-two-largest-towns-two-stops.json`. Initial
public populations rank town 4 first (2,539) and town 0 second (973). Stations
1/2 are nearest town 4's public center; station 0 is nearest town 0. This supports
the description geometrically, not through a direct station-town lookup or a
numeric policy label. The reason for the additional stop is not inferred.

Reports and dataset are under the runtime's
`runs/human-campaign-20261005/game-05/`; the Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-05/verification.md`.
The five-game training-only assembler passes with 118 exact examples (twelve
repayments total) at `runs/human-campaign-20261005/datasets/train-games-01-05/`.
No game-05 training or PPO updates ran. The four-game pilot is preserved.

Game 06 is session `20261005-154603-human-5745f1c6`, seed 2020301813, captured
October 5 from 15:46:04 to 15:58:16 EDT on OpenTTD 15.3, with exit code zero.
Its 17 allowlisted files include eight saves; all 18 runtime transfer files match
hashes. All 49 native commands succeed and all 11 checks match the final manual
save `Trendhattan Ridge Transport, 1972-05-06.sav`, marker 65. The consumer accepts
**39 choices**: four buys, nine inserts, ten Full load any changes, four starts,
one deletion, one loading-mode-4 change and ten repayments of 10,000. Seventeen
records are excluded: nine without exact policy actions, seven failed/estimate
records and one depot outside legal candidates. Waiting is not inferred.

The route edit at log lines 49–54 changes native vehicle 5 from stations 2/1 to
0/1. Fleet allocation changes from three buses on 1/2 and one on 0/1 to two on
each route. Five supported edits are retained with their exact pre-command states:
delete, insert, a temporary loading mode 4 and two Full load any changes. Line 50
also changes unloading to mode 1. It executes successfully but is excluded from
policy supervision; following examples retain the resulting native state.
Native IDs differ later, so vehicle 5 is identified at the edit only.

The final save has three stops, one depot and four running buses, two per route.
All eight endpoints use Full load any; one has unloading mode 1. Cash is 103,214
and debt zero. Ten repayments each reduce cash and principal by 10,000 with zero
command cost. The replay spans 603,942 ticks; financial and passenger counters
remain checkpoint snapshots rather than asserted lifetime totals.

The owner's exact retrospective explanation: "game 6 is done i had bought a few
more buses then the past and changed which route one of the buses was running for
the first time during the game because it increased profitablity". The annotation
is hash-bound at `annotations/game-06-fleet-expansion-route-reassignment.json`.
It records the reported profitability reason, separately from exact action labels.
Replay confirms reassignment; causal profit improvement is unmeasured.

Reports and dataset are under the runtime's `runs/human-campaign-20261005/game-06/`;
the Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-06/verification.md`.
The six-game training-only assembler passes with 157 exact examples, including
22 repayments, at `runs/human-campaign-20261005/datasets/train-games-01-06/`.
No game-06 training or PPO updates ran. The four-game pilot is preserved.

Game 07 is session `20261005-165039-human-b595e313`, seed 1652481928, captured
October 5 from 16:50:39 to 17:06:55 EDT on OpenTTD 15.3, with exit code zero.
Its 19 allowlisted files include ten saves; all 20 runtime transfer files match
hashes. All 55 replayed commands succeed and all 11 native checks match the final
manual save `Lathill Transport, 1979-01-02.sav`, marker 72. The consumer accepts
**29 choices**: two buys, six inserts, six Full load any changes, five starts or
restarts and ten repayments of 10,000. Thirty-two records are excluded: 25
without exact policy actions, six failed/estimate records and one depot outside
legal candidates. Later depot/replacement commands and the bus purchase at line
60 replay successfully but have no exact current policy action. The later
purchase costs 5,742; its subsequent supported decisions use the actual state.

The second initial bus departs at tick 4,053; the next logged command is the
first repayment at tick 567,056, a gap of 563,003 ticks with intervening autosaves.
It starts with cash 150,468 and debt 100,000. Five repayments reduce debt to
50,000, followed by later maintenance, two repayments, the later purchase and
three final repayments. All ten repayments reduce cash and principal by 10,000
each with zero command cost. The final repayment leaves cash 102,481 and debt
zero. The manual checkpoint has cash 103,852, three stops, one depot and three
running buses: two on 1/2 and one on 0/1, with independent two-order lists and
Full load any at all six endpoints. The replay spans 783,884 ticks; financial
and passenger counters remain checkpoint snapshots.

The owner's exact retrospective explanation: "game 7 is done and it took longer
to repay but instead of rushing to invest i waited till later on during the game
and fully repayed the loan". It is hash-bound at
`annotations/game-07-delayed-investment-full-repayment.json`. This records intent
to delay investment; it provides no exact WAIT decision boundary or duration.
The interval is retained as timing evidence without creating supervised WAIT.

Reports/dataset are under the runtime's `runs/human-campaign-20261005/game-07/`;
the Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-07/verification.md`.
The seven-game training-only assembler passes with 186 choices, including 32
repayments, at `runs/human-campaign-20261005/datasets/train-games-01-07/`.
This qualifies the proposed games 01–07 training partition. Games 08–10 remain
excluded from this dataset and model fitting. No game-07 training or PPO updates
ran; the four-game pilot is preserved.

The owner reported game 08 complete: "game 8 is done this one i scaled the amount
of buses per route based on passengers waiting". Its annotation is hash-bound at
`annotations/game-08-passenger-queue-capacity.json`. The recorder completed
normally at 17:55:10 EDT, after starting at 17:07:21. All 17 capture files,
including eight saves, and all 18 runtime transfer files match hashes. All 11
native checks pass against `Invenwell Transport, 1969-11-28.sav`, marker 66,
with 51 successful commands. The read-only development audit accepts 34 choices:
five buys, six inserts, six Full load any changes, five starts, two independent
copies and ten repayments. Twenty-three records are excluded. Earlier frozen
manual snapshots and the failed locked-log copy attempt remain preserved.

The checkpoint has three stops, one depot and five running buses: three on 1/2
and two on 0/1, with independent two-order lists and Full load any at all endpoints.
Cash is 109,219 and debt zero. The pre-purchase public observations retain waiting
passengers at every station. Shared station 1 has 228 waiting before line 34,
1,173 before line 41 and 553 before line 47. These are station totals, without
per-passenger route destinations. Keep the human's rationale separate; no numeric
threshold, route-specific queue or causal reduction is inferred.

The final replay and read-only development export are under the runtime's
`runs/human-campaign-20261005/game-08/replay-manual/` and `development-integrity/`.
The Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-08/verification.md`.
Game 08 remains development data; training stays at 186 choices. Both direct
imitation and the campaign CLI reject this actual completed capture as training
input. The seven-game training regression still passes. No model training or
scoring ran on game 08.

Game 09 is session `20261005-175528-human-8877f4a7`, seed 1846900543, completed
normally from 17:55:29 to 18:03:40 EDT on OpenTTD 15.3. All 16 capture files,
including seven saves, and 17 runtime transfer files match hashes. All 11 native
checks pass against `Wruningley Market Transport, 1961-04-16.sav`, marker 60,
with 46 successful commands. The read-only test audit accepts 31 choices: five
buys, four inserts, four Full load any changes, five starts, three independent
copies and ten repayments. Twenty-one records are excluded.

The owner's statement is "game 9 is done buses were scalled and the three city
loop was done perfectly", hash-bound at
`annotations/game-09-scaled-fleet-three-city-loop.json`. The saved network has
three stops and five running buses. Exact orders are two independent two-stop
routes: two buses on 0/1 and three on 0/2, with Full load any at all endpoints.
No three-station bus order cycle is present in the final save. Preserve the
human's description without inventing a different order list or an objective
score of perfect service.

The final replay and test export are under
`runs/human-campaign-20261005/game-09/replay-manual/` and `test-integrity/`;
the Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-09/verification.md`.
Both training input paths reject this actual completed test capture. Its choices
and outcomes are not used for model selection, feature/reward tuning or fitting;
no model scores are computed. Current counts are 186 training, 34 development
and 31 test choices at that stage.

Game 10 is session `20261005-180413-human-56fc8908`, seed 1836455473, completed
normally from 18:04:14 to 18:11:34 EDT on OpenTTD 15.3. All 15 capture files,
including six saves, and 16 transfer files match hashes. All 11 native checks
match `Flardington Transport, 1961-12-12.sav`, marker 60; all 47 commands succeed.
The read-only test audit accepts 33 choices: four buys, six inserts, six Full
load any changes, six starts/restarts, one copy and ten repayments. Twenty
records are excluded. Six running buses have independent two-order lists across
three stops: four on 0/2 and two on 0/1, all endpoints Full load any.

The owner's exact note is "game 10 is done i used 2 stations in 1 city since it
was above 2k population to start and then scaled the buses", hash-bound at
`annotations/game-10-large-city-two-stops-scaled-fleet.json`. It remains separate
from exact labels; stop construction is unsupported and no station-town lookup
or numeric population rule is invented. Reports are under
`runs/human-campaign-20261005/game-10/replay-manual/` and `test-integrity/`; the
Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-10/verification.md`.
Both training paths reject this actual test capture. The completed campaign has
186 training, 34 development and 64 test choices; all ten captures are preserved.

The owner subsequently requested a new training run, comparison with prior runs,
a saved 50-game evaluation and all evidence, without further questions or stopping.
The seven-game CUDA fit uses the same 256-update budget as the four-game pilot,
seed 20261002, learning rate 0.0003 and unchanged signed-log-orders-v2 C++ training.
`runs/human-ten-game-training-20261005-01/training-protocol.json` freezes the final
archive choice before model scores. A separate gameplay protocol records identical
seeded scenarios and budgets for each model, with supplied infrastructure and
greedy/sampled modes disclosed. Gameplay is evaluation only; no PPO updates occur.

Game 01's replay now passes all 11 checks at final manual marker 44, with 31
successful replayed commands, 18 exact labels and 20 exclusions. Three running
buses serve 1/0 and 0/2, with Full load any at all endpoints; cash is 103,186 and
loan 100,000. Its replay is `replay-manual/` under the runtime's
`runs/human-campaign-20261005/game-01/`; the four-game assembler accepts all 18
labels. The Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-01/verification.md`.

## Turn raw captures into a dataset

For each game, preserve an allowlisted, hash-verified capture, transfer it to the
Linux runtime, replay the authoritative final manual checkpoint, and require
native equality for roads, full orders, vehicles/stations/depots, finance, cash,
loan, date, tick and command-cost accounting. Export only successful exact choices
at their pre-command public state. Keep failed/estimate, setup and unsupported
events as counted exclusions. See [the recording workflow](DEVELOPMENT.md#local-human-command-recording-october-2)
and [exact bus-order replay](DEVELOPMENT.md#exact-bus-order-imitation-october-2).

Maintain a campaign ledger for every game: session/seed/split, capture protocol,
final save and log marker, capture hashes, replay report, verified/excluded counts
by action, explicit WAIT coverage, duplicate states and economic outcomes. Count
borrowing and repayments separately. Report delivered passengers, operating
profit, capital spending, cash change excluding loan-principal flows, final debt,
invalid actions and bankruptcy over clearly stated simulation horizons.

`scripts/dev/human_campaign_v2.py` now assembles whole training games through the
existing single-recording replay consumer. It checks each dataset, original log,
manual checkpoint and tensor mask, binds the capture/transfer hashes and seed,
and rejects duplicate recordings, changed inputs and development/test entries.
`imitate_v2.py` accepts its explicit campaign schema without changing the native
C++ objective. Development/test exports need a separate evaluation workflow;
this assembler intentionally accepts only training games. Its consumer now checks
the whole-game partition hash-bound into preservation metadata, including when
called through the CLI or the individual imitation path. Development/test captures
cannot be relabelled by a training CLI argument.

Use `scripts/dev/audit_human_evaluation_v2.py` to qualify completed development/test
captures without creating trainer input. It validates the original native replay,
command packets/accounting, public tensors and legal masks, and exports a separate
evaluation schema with actual whole-game split assignments. It produces no trainer
TSV, model fit or prediction scores. Native source artifacts remain immutable.

The loader and C++ reader still cap a run at 512 examples; all seven games' 186 fit.
Recheck the total when importing additional action families before extending or
batching that bound. Never
discard good decisions or pad the count with repeated clicks to fit a limit.

The October 5 pilot uses 256 full-dataset Adam updates for both fresh models,
seed 20261002, learning rate 0.0003 and signed-log-orders-v2 on CUDA. The original
12-example recording is a separate control, not a fifth game added to the new
dataset. Fit and transfer are labelled relative to each model's training games.
Live checks use the same two disclosed October 2 contexts, greedy and sampled,
24 decisions of 128 ticks, CPU inference and complete legal masks. The four-game
model has not trained on those contexts. Infrastructure is supplied. No outcome
from future games 08–10 is used for this pilot or model selection.

## First training and evaluation experiment

Use the existing separate C++/LibTorch imitation objective on CUDA. Compare the
new seven-game fit with the preserved single-recording model on game 08 and the
old regression fixture. Track each action type and borrow/repay direction, target
identity, loading mode, unique-choice margins and input aliases. Report training
accuracy separately from development/test behavior. Check sample and game balance
so frequent route edits do not overwhelm rarer finance or explicit WAIT choices.

Freeze the selected model and evaluation protocol before examining games 09–10.
Evaluate both greedy and sampled choices with the same documented tick budgets
and contexts. Where construction labels remain unsupported, use supplied
infrastructure and state that task boundary. Compare against a simple one-bus
script and human outcomes; two test games provide an initial check, not a reliable
estimate of general OpenTTD strength.

Measure initial buys, unnecessary extra buys, route correctness before start,
delivery/service retention, route damage, profit, cash/debt and invalid actions.
Only then attempt bounded PPO refinement and measure imitation retention again.

Longer-term, collect human corrections in states visited by the learned policy.
Sequential imitation can fail when its own actions move it away from demonstration
states; the [DAgger paper](https://proceedings.mlr.press/v15/ross11a.html) motivates
this follow-up. The ten-game campaign is an initial human dataset, not a completed
DAgger implementation.
