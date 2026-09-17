"""Interpreter for a pack's rules.yaml: declarations -> vectorized predicates.

Each pack declares its rule chain as data (rules.yaml: name, kind, signal
column, thresholds key, in production chain order). This module turns those
declarations into pandas predicates over stored measurements — evaluated per
rule, without chain short-circuiting.

There is deliberately NO hand-written per-version rule list here: a new filter
version ships its own rules.yaml inside its own pack, and this interpreter
stays untouched unless a genuinely new rule SHAPE appears (then add a kind
below). Correctness is enforced by the sampling invariant: the first violation
in declared order must reproduce the stored qf_reason on every sampled
document.
"""


def _predicate_for(declaration, thresholds):
    kind = declaration["kind"]
    if kind == "greater_than":
        signal, threshold_value = declaration["signal"], thresholds[declaration["threshold"]]
        return lambda frame: frame[signal] > threshold_value
    if kind == "less_than":
        signal, threshold_value = declaration["signal"], thresholds[declaration["threshold"]]
        return lambda frame: frame[signal] < threshold_value
    if kind == "outside_range":
        signal = declaration["signal"]
        lower, upper = thresholds[declaration["threshold"]]
        return lambda frame: (frame[signal] < lower) | (frame[signal] > upper)
    if kind == "any_ngram_over":
        prefix = declaration["signal_prefix"]
        pairs = thresholds[declaration["threshold"]]

        def predicate(frame):
            combined = None
            for n, threshold_value in pairs:
                over = frame[f"{prefix}_{n}"] > threshold_value
                combined = over if combined is None else (combined | over)
            return combined
        return predicate
    if kind == "flag":
        signal = declaration["signal"]
        return lambda frame: frame[signal].astype(bool)
    raise ValueError(f"unknown rule kind {kind!r} in rules.yaml — "
                     "extend the interpreter in src/qf_tuner/rules.py")


def build_rules(declarations, thresholds):
    """[(rule_name, predicate)] in declared (= production chain) order.

    A `flag` rule whose `enabled_by` thresholds key is false is skipped —
    declared structure, deactivated by configuration (matches production).
    """
    rules = []
    for declaration in declarations:
        if declaration["kind"] == "flag" and not thresholds.get(declaration["enabled_by"]):
            continue
        rules.append((declaration["name"], _predicate_for(declaration, thresholds)))
    return rules
