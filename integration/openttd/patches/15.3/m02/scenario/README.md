# M02 native scenario/reset delta

This nested series starts from the accepted M02 feasibility result tree
`eba8f4bd3c37042c184d968d2f038864184e3132`. It intentionally does not modify
the accepted parent `m02/series` or its pinned `0002` patch.

`0003` adds the native fixed passenger-bus scenario materializer, complete reset
projection, clean-process oracle CLI, same-process reset comparison, and the
non-learning scripted bus acceptance trajectory. All runtime behavior is gated
by the existing default-off `OPTION_RL_ENVIRONMENT`. The delta does not implement
the RL bridge, action interface, PPO trainer, ONNX inference, or neural in-game
control.
