"""Local integration checks; all data, scheduler stubs and HTTP responses are synthetic.

Run: python -m unittest discover -s tests -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
SAMPLER = ROOT / "pipeline/01_sampling/sample.py"
CLIENT = ROOT / "pipeline/02_llm_labeling/run_inference.py"
sys.path.insert(0, str(ROOT / "pipeline"))
from filter_provenance import describe_pack


class PipelineBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="autoclean boundary ")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                    "PIPELINE_PYTHON": sys.executable}

    def command(self, *args, success=True, cwd=ROOT, env=None):
        result = subprocess.run([str(arg) for arg in args], cwd=cwd,
                                env=env or self.env, capture_output=True,
                                text=True, timeout=60)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def dataset(self, verdicts=False):
        qf, raw = self.work / "qf", self.work / "raw"
        qf.mkdir()
        raw.mkdir()
        rows = []
        for shard in range(3):
            frame = pd.DataFrame({
                "uid": [f"doc-{shard}-{i}" for i in range(6)],
                "url": ["https://example.test"] * 6,
                "language": ["en"] * 6,
                "text": [f"Document {shard}-{i} contains readable content." for i in range(6)],
                "qf_reason": ["kept", "short_doc"] * 3,
                "word_count": [100, 30] * 3,
                "custom_signal": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            })
            if verdicts:
                frame["viol_short_doc"] = frame.qf_reason == "short_doc"
                frame["n_violations"] = frame.viol_short_doc.astype("int32")
                frame["sole_blocker"] = frame.qf_reason.where(frame.viol_short_doc)
                frame["first_blocking"] = frame.qf_reason
            name = f"part-{shard}.parquet"
            frame.to_parquet(qf / name, index=False, row_group_size=2)
            # Deliberately reorder every raw shard to exercise the ID-join fallback.
            mirror = pd.DataFrame({"uid": frame.uid, "text": "raw:" + frame.uid})
            mirror.iloc[::-1].to_parquet(raw / name, index=False, row_group_size=2)
            rows.append(frame)
        manifest = self.work / "shards.txt"
        manifest.write_text("".join(f"part-{i}.parquet\n" for i in range(3)))
        config = {"name": "toy", "kind": "qf_output_parquet", "qf_root": str(qf),
                  "raw_root": str(raw), "manifest": str(manifest),
                  "reason_column": "qf_reason",
                  "columns": {"id": "uid", "url": "url", "vendor_lang": "language",
                              "text_raw": "text"}}
        path = self.work / "dataset.yaml"
        path.write_text(yaml.safe_dump(config))
        return path, pd.concat(rows, ignore_index=True)

    def sample(self, config, name):
        output = self.work / name
        self.command(sys.executable, SAMPLER, "--dataset", config, "--out", output,
                     "--filter-pack", "cc_baseline",
                     "--pool-shards", "3", "--target-default", "3",
                     "--target", "kept=2", "--processes", "2", "--seed", "7")
        return output

    def test_sampling_preserves_prepared_columns_and_seeded_draw(self):
        config, source = self.dataset(verdicts=True)
        first = self.sample(config, "first")
        second = self.sample(config, "second")
        frame = pd.read_parquet(first / "sample.parquet")
        self.assertEqual(frame.qf_reason.value_counts().to_dict(), {"short_doc": 3, "kept": 2})
        self.assertEqual(set(frame.uid), set(pd.read_parquet(second / "sample.parquet").uid))
        expected = source.set_index("uid").loc[frame.uid]
        pd.testing.assert_frame_equal(frame[source.columns].reset_index(drop=True),
                                      expected.reset_index()[source.columns])
        self.assertEqual(frame.text_raw.tolist(), ["raw:" + uid for uid in frame.uid])
        self.assertEqual(frame.strat.tolist(), frame.qf_reason.tolist())
        meta = json.loads((first / "meta.json").read_text())
        self.assertTrue(meta["verdicts_present"])
        self.assertEqual(meta["filter_pack"], describe_pack("cc_baseline"))
        self.assertTrue(meta["tool"]["git"], "sample metadata must record the producing revision")
        self.assertGreater(meta["fetch"]["raw_join_fallbacks"], 0)
        self.assertEqual(meta["errors"]["fetch_pass_total"], 0)
        original = (first / "sample.parquet").read_bytes()
        self.command(sys.executable, SAMPLER, "--dataset", config, "--out", first,
                     "--filter-pack", "cc_baseline", success=False)
        self.assertEqual((first / "sample.parquet").read_bytes(), original)

    def test_unprepared_input_is_rejected_without_generating_columns(self):
        config, _ = self.dataset()
        dataset = yaml.safe_load(config.read_text())
        for shard in Path(dataset["qf_root"]).glob("*.parquet"):
            pd.read_parquet(shard).drop(columns="qf_reason").to_parquet(shard, index=False)
        result = self.command(sys.executable, SAMPLER, "--dataset", config,
                              "--filter-pack", "cc_baseline",
                              "--out", self.work / "invalid", success=False)
        self.assertIn("qf_reason", result.stderr)
        self.assertFalse((self.work / "invalid/sample.parquet").exists())
        dataset["kind"] = "raw"
        config.write_text(yaml.safe_dump(dataset))
        result = self.command(sys.executable, SAMPLER, "--dataset", config,
                              "--filter-pack", "cc_baseline",
                              "--out", self.work / "raw-output", success=False)
        self.assertIn("prepared upstream", result.stderr)

    def test_filter_pack_is_required_and_checked_before_sampling(self):
        output = self.work / "sample"
        command = (sys.executable, SAMPLER, "--dataset", self.work / "absent.yaml",
                   "--out", output)
        result = self.command(*command, success=False)
        self.assertIn("--filter-pack", result.stderr)
        result = self.command(*command, "--filter-pack", "nonexistent_version", success=False)
        self.assertIn("Unknown or incomplete filter pack", result.stderr)
        self.assertFalse(output.exists())

    def test_pack_fingerprint_tracks_contents_without_executing_filter_code(self):
        packs = self.work / "packs"
        pack = packs / "test_version"
        (pack / "rules").mkdir(parents=True)
        rule = pack / "rules/rule.py"
        rule.write_text("raise RuntimeError('filter code must never run here')\n")
        parameters = pack / "thresholds.yaml"
        parameters.write_text("word_count: [50, 100000]\n")
        (pack / "PROVENANCE.md").write_text("Test filter snapshot\n")
        with patch("filter_provenance.PACKS_ROOT", packs):
            first = describe_pack("test_version")
            self.assertEqual(first, describe_pack("test_version"))
            rule.write_text(rule.read_text() + "# New rule implementation\n")
            changed_code = describe_pack("test_version")
            self.assertNotEqual(first["sha256"], changed_code["sha256"])
            parameters.write_text("word_count: [100, 100000]\n")
            changed_parameters = describe_pack("test_version")
            self.assertNotEqual(changed_code["sha256"], changed_parameters["sha256"])
            (pack / "rules/__pycache__").mkdir()
            (pack / "rules/__pycache__/rule.pyc").write_bytes(b"cache")
            self.assertEqual(changed_parameters, describe_pack("test_version"))

    def test_reuse_rejects_wrong_changed_and_missing_filter_records(self):
        config, _ = self.dataset()
        sample = self.sample(config, "sample")
        meta_path = sample / "meta.json"
        metadata = json.loads(meta_path.read_text())
        run = self.work / "run"
        command = ("bash", ROOT / "pipeline/run_pipeline.sh", run, "--sample-dir", sample)
        result = self.command(*command, "--filter-pack", "keenable_shortok_v0", success=False)
        self.assertIn("does not match --filter-pack", result.stderr)
        self.assertFalse(run.exists(), "mismatches must fail before creating a run or submitting jobs")

        for invalid_record in ({**metadata["filter_pack"], "sha256": "0" * 64}, None):
            with self.subTest(filter_pack=invalid_record):
                meta_path.write_text(json.dumps({**metadata, "filter_pack": invalid_record}))
                result = self.command(*command, "--filter-pack", "cc_baseline", success=False)
                self.assertIn("filter", result.stderr.lower())
                self.assertFalse(run.exists())
                output = self.work / "invalid-labels.jsonl"
                result = self.command(sys.executable, CLIENT, self.work / "unused.jsonl", output,
                                      "--sample-meta", meta_path, "--base-url", "http://127.0.0.1:1/v1",
                                      success=False)
                self.assertIn("filter", result.stderr.lower())
                self.assertFalse(output.exists())

        meta_path.write_text(json.dumps(metadata))
        run.mkdir()
        (run / "blind_input.jsonl").write_text("legacy input\n")
        result = self.command(*command, "--filter-pack", "cc_baseline", success=False)
        self.assertIn("without filter provenance", result.stderr)
        self.assertFalse((run / "meta.json").exists())

    def test_imported_filter_snapshot_and_parameters_are_preserved(self):
        filters = self.work / "filters"
        shutil.copytree(ROOT / "filters/scripts", filters / "scripts")
        upstream = self.work / "upstream"
        shutil.copytree(ROOT / "filters/packs/cc_baseline/rules", upstream)
        # Import a changed rule set into an empty pack directory, without a template.
        thresholds = upstream / "threshold.py"
        thresholds.write_text(thresholds.read_text().replace(
            "word_count: Tuple = (50, 100000)", "word_count: Tuple = (100, 100000)")
            + "\n    max_symbol_run: int = 8\n")
        (upstream / "symbol_run.py").write_text(
            "def reject_symbol_run(longest_run, thresholds):\n"
            "    return longest_run > thresholds.max_symbol_run\n")
        self.command("git", "init", "-q", upstream)
        self.command("git", "add", ".", cwd=upstream)
        self.command("git", "-c", "user.name=Local Test", "-c", "user.email=test@example.test",
                     "-c", "commit.gpgsign=false", "commit", "-qm", "fixture", cwd=upstream)
        self.command("bash", filters / "scripts/new_baseline.sh", "test_version", upstream)
        imported = filters / "packs/test_version"
        self.assertEqual({path.name for path in imported.iterdir()},
                         {"rules", "thresholds.yaml", "PROVENANCE.md"})
        for source in upstream.glob("*.py"):
            self.assertEqual((imported / "rules" / source.name).read_bytes(), source.read_bytes())
        self.command(sys.executable, filters / "scripts/pack_thresholds.py", imported)
        parameters = yaml.safe_load((imported / "thresholds.yaml").read_text())
        self.assertEqual(parameters["word_count"], [100, 100000])
        self.assertEqual(parameters["max_symbol_run"], 8)
        commit = self.command("git", "rev-parse", "--short", "HEAD", cwd=upstream).stdout.strip()
        self.assertIn(commit, (imported / "PROVENANCE.md").read_text())
        self.command("bash", filters / "scripts/new_baseline.sh", "test_version", upstream,
                     success=False)

    def test_two_stage_runner_uses_prepared_data_and_resumes(self):
        config, _ = self.dataset()
        requests = []

        class Judge(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                document = json.loads(payload["messages"][1]["content"])
                requests.append(document)
                answer = {"content_share": "most", "coherence": "clear", "verdict": "keep",
                          "reason_codes": ["content_present"], "reason": "Readable content.",
                          "evidence": [document["text"]]}
                body = json.dumps({"choices": [{"message": {"content": json.dumps(answer)},
                                                 "finish_reason": "stop"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Judge)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        run = self.work / "run"
        (run / "serve").mkdir(parents=True)
        (run / "serve/jobid").write_text("202\n")
        (run / "serve/endpoints.txt").write_text(f"http://127.0.0.1:{server.server_port}/v1\n")
        targets = self.work / "targets.conf"
        targets.write_text("--target-default 2 --target kept=2\n")
        scheduler = self.work / "scheduler"
        scheduler.mkdir()
        scripts = {
            "sbatch": '''#!/usr/bin/env python3
import os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
start = next(i for i, arg in enumerate(args) if not arg.startswith('-'))
assert args[start].endswith('/pipeline/scripts/run_sample.sbatch'), args
log = Path(os.environ['TEST_SUBMIT_LOG'])
assert not log.exists(), 'sampling was unexpectedly submitted again'
env = {**os.environ, 'SLURM_CPUS_PER_TASK': '2', 'SLURM_SUBMIT_DIR': os.getcwd()}
with log.open('w') as handle:
    subprocess.run(['bash', *args[start:]], env=env, stdout=handle, stderr=handle, check=True)
print('101')
''',
            "squeue": '''#!/usr/bin/env python3
import sys
if sys.argv[sys.argv.index('-j') + 1] == '202':
    print('202 test-serving-job')
''',
            "scancel": "#!/bin/sh\nexit 99\n",
        }
        for name, script in scripts.items():
            path = scheduler / name
            path.write_text(script)
            path.chmod(0o755)
        env = {**self.env, "PATH": str(scheduler) + os.pathsep + self.env["PATH"],
               "TEST_SUBMIT_LOG": str(self.work / "sample-job.log")}
        sample = self.work / "new sample"
        command = ("bash", ROOT / "pipeline/run_pipeline.sh", run, "--sample-dir", sample,
                   "--filter-pack", "cc_baseline", "--dataset", config,
                   "--sampling-targets", targets, "--keep-server")
        self.command(*command, env=env)
        frame = pd.read_parquet(sample / "sample.parquet")
        self.assertEqual(len(frame), 4)
        self.assertFalse(any(c.startswith("viol_") for c in frame))
        blind = [json.loads(line) for line in (run / "blind_input.jsonl").read_text().splitlines()]
        self.assertTrue(all(set(row) == {"id", "text", "coverage"} for row in blind))
        labels = [json.loads(line) for line in
                  (run / "labels/raw_llm_responses.jsonl").read_text().splitlines()]
        self.assertEqual({row["id"] for row in labels}, set(frame.uid))
        self.assertTrue(all(row["decision"] == "keep" for row in labels))
        filter_pack = json.loads((sample / "meta.json").read_text())["filter_pack"]
        self.assertTrue(all(row["run"]["filter_pack"] == filter_pack for row in labels))
        self.assertEqual(json.loads((run / "meta.json").read_text())["filter_pack"], filter_pack)
        self.assertEqual((run / "labels/missing_ids.txt").read_text(), "")
        self.assertTrue((run / "labels/stats.md").is_file())
        self.assertEqual(json.loads((run / "labels/stats.json").read_text())["filter_pack"], filter_pack)
        self.assertIn(filter_pack["sha256"], (run / "labels/stats.md").read_text())
        self.assertEqual(len(requests), 4)
        self.assertTrue(all(set(row) == {"text", "coverage"} for row in requests))
        self.command(*command, env=env)
        self.assertEqual(len(requests), 4, "resume should reuse completed IDs")

        standalone = self.work / "standalone.jsonl"
        self.command(sys.executable, CLIENT, run / "blind_input.jsonl", standalone,
                     "--sample-meta", sample / "meta.json",
                     "--base-url", f"http://127.0.0.1:{server.server_port}/v1", "--limit", "1")
        self.assertEqual(json.loads(standalone.read_text())["run"]["filter_pack"], filter_pack)
        self.assertEqual(len(requests), 5)
        self.assertEqual(set(requests[-1]), {"text", "coverage"})

        # A different valid sample/pack cannot reuse this run's blind input or decisions.
        other_sample = self.work / "other sample"
        shutil.copytree(sample, other_sample)
        other_meta = json.loads((other_sample / "meta.json").read_text())
        other_meta["filter_pack"] = describe_pack("keenable_shortok_v0")
        (other_sample / "meta.json").write_text(json.dumps(other_meta))
        existing_results = (run / "labels/raw_llm_responses.jsonl").read_bytes()
        result = self.command("bash", ROOT / "pipeline/run_pipeline.sh", run,
                              "--sample-dir", other_sample, "--filter-pack", "keenable_shortok_v0",
                              env=env, success=False)
        self.assertIn("use a new workdir", result.stderr)
        self.assertEqual((run / "labels/raw_llm_responses.jsonl").read_bytes(), existing_results)
        self.assertEqual(len(requests), 5)


if __name__ == "__main__":
    unittest.main()
