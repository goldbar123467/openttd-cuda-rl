# M09 evaluation-only OpenTTD delta

This patch applies after the accepted M06 composed source. It preserves the
default reset behavior byte-for-byte at the protocol level and adds a strictly
bounded M09 reset form. The extended form requires the frozen M09 compatibility
identity and accepts only the preregistered starting balances and aligned action
and tick horizons.

Training clients never send these fields. The independent evaluator uses them
only for the frozen final and robustness matrix. Unsupported values, partial
overrides, and compatibility drift fail before scenario use.
