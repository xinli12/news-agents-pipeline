from main import build_parser


def test_cli_analysis_mode_defaults_to_balanced() -> None:
    args = build_parser().parse_args(["--topic", "Example topic"])

    assert args.analysis_mode == "balanced"


def test_cli_accepts_analysis_mode_choices() -> None:
    args = build_parser().parse_args(
        ["--topic", "Example topic", "--analysis-mode", "fast"]
    )

    assert args.analysis_mode == "fast"
