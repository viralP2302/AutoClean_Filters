"""Filter-pack loading (the annotate stage's internals).

A pack is a directory: thresholds.yaml (authoritative numbers) + rules.yaml
(the rule-chain declaration) + rules/ (the executable rule code, byte-pinned
to the QF main repo — see the pack's PROVENANCE.md). Annotation only needs the
two yaml files: declarations + thresholds turn into vectorized predicates over
stored measurements.
"""

from pathlib import Path

import pandas as pd
import yaml

from .rules import build_rules


class Pack:
    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.name
        self.thresholds = yaml.safe_load((self.path / "thresholds.yaml").read_text())
        self.declarations = yaml.safe_load((self.path / "rules.yaml").read_text())
        self.rules = build_rules(self.declarations, self.thresholds)
        self.rule_names = [rule_name for rule_name, _ in self.rules]
        # a document reached the signal stage iff its measurements were computed;
        # the first declared per-signal column marks that (null = never computed)
        self.stage_marker = next(declaration["signal"] for declaration in self.declarations
                                 if "signal" in declaration)

    def required_columns(self):
        """Measurement columns the declared rules read — checked against the data."""
        columns = []
        for declaration in self.declarations:
            if "signal" in declaration:
                columns.append(declaration["signal"])
            elif "signal_prefix" in declaration:
                pairs = self.thresholds[declaration["threshold"]]
                columns.extend(f"{declaration['signal_prefix']}_{n}" for n, _ in pairs)
        return columns

    def verdicts(self, frame):
        """Per-rule violation columns: nullable-bool `viol_<rule>` per document.

        Null for documents that never reached the signal stage (their
        measurements were never computed: lang/url/empty/oversize rejects) —
        for those, the stored rejection reason is all we know.
        """
        signal_stage_mask = frame[self.stage_marker].notna()
        signal_stage_frame = frame.loc[signal_stage_mask]
        result = pd.DataFrame(index=frame.index)
        for rule_name, predicate in self.rules:
            column = pd.Series(pd.NA, index=frame.index, dtype="boolean")
            column.loc[signal_stage_mask] = predicate(signal_stage_frame).astype(bool).to_numpy()
            result[f"viol_{rule_name}"] = column
        return result

    def first_blocking(self, verdicts):
        """Reproduce the production chain outcome from the violation columns:
        the first violated rule in declared order, 'kept' if none, null off-stage."""
        signal_stage_mask = verdicts[f"viol_{self.rule_names[0]}"].notna()
        result = pd.Series(pd.NA, index=verdicts.index, dtype="object")
        already_blocked = pd.Series(False, index=verdicts.index)
        for rule_name in self.rule_names:
            blocked_here = (verdicts[f"viol_{rule_name}"].fillna(False).astype(bool)
                            & signal_stage_mask & ~already_blocked)
            result[blocked_here] = rule_name
            already_blocked |= blocked_here
        result[signal_stage_mask & ~already_blocked] = "kept"
        return result
