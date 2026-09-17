import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="qf_tuner",
        description="LLM-judge-driven tuning of quality filters (docs/DESIGN.md).",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    sample_parser = subcommands.add_parser(
        "sample", help="pure stratified sampling over a labeled corpus")
    sample_parser.add_argument("--dataset", required=True,
                               help="dataset yaml (configs/datasets/*.yaml)")
    sample_parser.add_argument("--out", required=True,
                               help="output directory (sample.parquet + meta.json)")
    sample_parser.add_argument("--pool-shards", type=int, default=1200,
                               help="shards in the random pool")
    sample_parser.add_argument("--target-default", type=int, default=1500,
                               help="documents to draw per label")
    sample_parser.add_argument("--target", action="append", metavar="LABEL=COUNT",
                               default=["kept=10000"],
                               help="per-label override, repeatable "
                                    "(default includes kept=10000)")
    sample_parser.add_argument("--seed", type=int, default=7)
    sample_parser.add_argument("--processes", type=int, default=32)

    annotate_parser = subcommands.add_parser(
        "annotate", help="add per-rule verdict columns to a drawn sample")
    annotate_parser.add_argument("--sample", required=True,
                                 help="sample directory (from qf_tuner sample)")
    annotate_parser.add_argument("--pack", default="filter_packs/cc_baseline",
                                 help="the filter pack that produced this corpus's labels")

    args = parser.parse_args()
    if args.command == "sample":
        from . import sampler
        sampler.run(args)
    else:
        from . import annotate
        annotate.run(args)


if __name__ == "__main__":
    main()
