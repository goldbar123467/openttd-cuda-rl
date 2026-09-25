# Progress illustration provenance

The three historical illustrations below were generated with the built-in imagegen tool on September 24, 2026. They are explanatory illustrations, not measured plots or actual gameplay screenshots. Their queued-replication wording reflects that earlier snapshot; the current progress log records subsequent failures. The measured MCP chart at the end of this document is separate. Results come from ../PROGRESS.md. No image implies a completion percentage or general full-game competence.

## Image 1

Create a clean, polished educational infographic, landscape 1536x1024 style, with restrained OpenTTD-inspired isometric buses and small town details, mostly clean cream background, navy type, teal successes and amber cautions. Large legible text, no decorative filler slogans. Title 'OpenTTD PPO: What the experiments actually show'. Four equally sized experiment cards, not proportional charts. Card 1 'MORE EXPERIENCE' / '8,192 training decisions' / '9/9 evaluations sustained service' / 'Still failed economic comparisons'. Card 2 'LOWER ENTROPY' / 'Less encouragement for random choices' / '5/9 sustained service' / 'Performance regressed'. Card 3 'FROZEN POLICY + BORROWING' / 'Same weights, new recovery option' / '9/9 sustained service' / 'Promising development lead'. Card 4 'RETRAIN WITH BORROWING' / 'Fresh 8,192-decision training' / '1/9 sustained service' / 'Retraining regressed'. Draw an illustrative bus stopped before purchase then a small loan recovery arrow only near card 3; clearly depicts mechanism, not actual screenshot. Bottom wide note 'All V2 results use a public route planner.' Second note 'Frozen-policy sampled profit: 4,009 vs uniform 3,682. Advantage is uncertain; independent training-seed replication is queued.' Footer 'September 24, 2026 • One trained model is not proof of generalization'. Do not label whole project completed or solved. Exact numbers and distinctions must be accurate. Design highly readable, elegant presentation graphic.

Final correction prompt:

Correct this infographic without changing its main title, four result cards, result numbers, bottom caveats or layout. Remove every invented currency amount, cost and balance sign from the illustrations. Replace illustrations in cards 1 and 2 with neutral bus-and-town scenes without any claim of insufficient funds. In card 3 only, show 'Bus unaffordable' then 'Optional borrowing' then 'Service restored', with no currency values. In card 4 show a stopped bus and a WAIT sign; remove 'Bus purchased!' and borrowing-success imagery because retraining failed. Replace the green check icon for the 5/9 and 1/9 service counts with neutral navy circles, retaining those exact numbers. Keep 9/9 result check icons. Remove decorative extra slogans. Preserve all accurate result text and caveats. Crisp legible white/cream infographic.

## Image 2

Create an educational technical infographic with beautiful restrained isometric transport-game illustration, cream background navy typography teal arrows amber warning accents. Title 'Why more GPU time is not enough'. Three big clearly separated panels, extremely legible text. LEFT panel title 'THE GAME' shows two distinct labeled action cards 'Borrow money' and 'Repay debt', opposite directional arrows around bank, and two distinct road placement icons. MIDDLE panel title 'WHAT THE NETWORK RECEIVES' shows those two money cards feeding identical small arrays, label 'Borrow and repay have identical candidate features in one inspected state.' Below 'Some different road, stop and depot choices also share features.' This is an illustrative feature diagram, not a plotted measurement; do not invent numeric vectors. RIGHT panel title 'WHAT THE GUIDE DOES' shows a road map with one highlighted legal planned step and label 'A public planner selects route geometry and filters choices.' Then 'Guided success does not prove independent route planning.' BOTTOM horizontal process three labeled blocks 'Represent distinct actions clearly' arrow 'Verify the game interface' arrow 'Then measure learning across seeds'. Small side note 'The borrowing recovery lets a frozen policy recover service; retraining still regressed.' Footer 'Observed limitation, not proof of the cause of every failure • September 24, 2026'. No invented currency amounts, no fake metrics, no whole-project percentage, no extra decorative slogans. Professional research explainer with readable concise text.

Final correction prompt:

Edit this infographic for accuracy and legibility. Remove ALL dark blue gradients/vignettes; background must be white or very pale cream with high-contrast navy type, including title and footer. In left panel remove the entire 'Upgrade road' section and any reference to a higher tier. Replace the two road examples with 'Road placement A' and 'Road placement B', depicting two different tile positions, no invented mechanics. In middle panel remove the four road/stop/depot icon arrays and their claim that different families share identical vectors. Replace that bottom area with just a simple text callout: 'Within each construction family, many different candidate rows also have identical features.' The upper borrow/repay identical feature example remains, both arrays must have same number of blocks. In right panel replace 'A human-style planner adds structure and filters the action space.' with 'A public route planner supplies geometry and filters choices.' Preserve title and main facts, bottom three-step process, one-state limitation footer. No new data or numbers. Professional bright readable infographic.

## Image 3

Create a refined landscape educational roadmap infographic on clean white background, highly legible navy typography, teal completed markers amber current marker gray future markers, charming small OpenTTD-inspired isometric town and transportation illustrations. Title 'From a trained bus agent to a full-game player'. Subtitle 'Engineering is established. General playing strength is still a research goal.' Four large sequential milestone panels joined by a winding route. Panel 1 'ESTABLISHED' / 'Training and deployment' / 'C++ / CUDA PPO' / 'Checkpoints, ONNX and visible play' / 'MCP company control'. Panel 2 'DEMONSTRATED' / 'Narrow bus skills' / 'V1: 18/18 sampled held-out service cases' / 'V2: planner-assisted service' / 'Cash efficiency remains weak'. Panel 3 emphasized pin 'YOU ARE HERE' / 'Reliable decisions' / 'Replicate borrowing recovery across training seeds' / 'Resolve indistinguishable action features' / 'Fix shared construction conflicts'. Panel 4 'STILL AHEAD' / 'Full-game competence' / 'Learn trucks, trains, ships and aircraft' / 'Generalize across varied maps' / 'Compete profitably against other agents'. Below small clear legend 'Established infrastructure is not the same as learned gameplay.' Footer 'September 24, 2026 • Milestones are not equal effort • No completion percentage implied'. Illustrate progression with computer GPU and bus depot, operating bus village, decision junction, future mixed transport city. No fake percentages, no invented statistics, no extra slogans, no learning curves. Crisp readable graphic suitable for GitHub README.

## Measured MCP comparison

`mcp-matched-guide-results-2026-09-24.png` is a Matplotlib plot of completed
native-game results, with its exact numeric input in the adjacent `.json` file.
All twelve full matches are included: two development maps, swapped MCP roles,
and actual LLM, uniform and proposal-priority controllers. The fixed neural
opponent sustains service in four LLM matches; the LLM chooses 1,024 WAIT actions.
Both actors fail service in all eight scripted matches because of shared-plan
construction conflicts. This is not a general model ranking.

The independent review checks all 24 company totals and 96 economic windows.
The PNG was visually inspected for labels, sign conventions and crowding.
Original run: `v2-mcp-matched-guide-economics-01`; read-only review and plotting
source: `runs/2026-09-24/v2-mcp-matched-guide-01/review_complete.py` (local artifact).

- PNG SHA-256: `98d5c4381b7fa955f4919a9bcb37c9537e35bd014e5306fea5d504e093e68620`.
- Data SHA-256: `4a7a7f64e731a0e7396d76969af9a133fcae0f7f2f84bafedaa21bf203d6ea5a`.
- Original comparison SHA-256: `40cc679d5fe20beb8b0a35ba2f5b8027c87c6a763056c703a3b54c1101f40554`.
