from integration.production_overlay.run_opening_search_probe import parse_analysis_stdout


def test_parse_production_depth2_summary():
    text = (
        "我会走 h4 (h2h4)。当前搜索评价约 -35cp，搜索认为它在当前深度下保留了最好的综合局面评价。"
        "搜索深度 2，访问 867 个节点；候选：h4 -35cp, d4 -49cp, Na3 -49cp, Nc3 -52cp；主变化：h4 Nf6。"
    )
    parsed = parse_analysis_stdout(text)
    assert parsed["move"] == "h2h4"
    assert parsed["score_cp"] == -35.0
    assert parsed["depth"] == 2
    assert parsed["nodes"] == 867


def test_parse_production_depth3_summary():
    text = (
        "我会走 Nf3 (g1f3)。当前搜索评价约 +51cp，搜索认为它在当前深度下保留了最好的综合局面评价。"
        "搜索深度 3，访问 6657 个节点；候选：Nf3 +51cp, e4 +51cp, c3 +43cp, Nc3 +42cp；主变化：Nf3 e6 c3。"
    )
    parsed = parse_analysis_stdout(text)
    assert parsed["move"] == "g1f3"
    assert parsed["score_cp"] == 51.0
    assert parsed["depth"] == 3
    assert parsed["nodes"] == 6657


def test_parse_fullwidth_parentheses_and_spacing():
    text = (
        "棋盘...\n"
        "我会走 h4 （ h2h4 ） 。 当前搜索评价约 -35cp，搜索认为它在当前深度下保留了最好的综合局面评价。 "
        "搜索深度 2，访问 867 个节点；候选： h4 -35cp，d4 -49cp；主要变化： h4 Nf6。"
    )
    parsed = parse_analysis_stdout(text)
    assert parsed["move"] == "h2h4"
    assert parsed["score_cp"] == -35.0
    assert parsed["depth"] == 2
    assert parsed["nodes"] == 867


def test_parse_ansi_wrapped_summary():
    text = (
        "r n b q k b n r\n"
        "\x1b[32m我会走 Nf3\x1b[0m \x1b[1m(g1f3)\x1b[0m。"
        "当前搜索评价约 +51cp，搜索深度 3，访问 6657 个节点。"
    )
    parsed = parse_analysis_stdout(text)
    assert parsed["move"] == "g1f3"
    assert parsed["score_cp"] == 51.0
    assert parsed["depth"] == 3
    assert parsed["nodes"] == 6657


def test_json_remains_preferred_when_available():
    parsed = parse_analysis_stdout(
        'prefix {"best_move":"e2e4","score_cp":22,"depth":4,"elapsed_seconds":1.5} suffix'
    )
    assert parsed["move"] == "e2e4"
    assert parsed["score_cp"] == 22.0
    assert parsed["depth"] == 4
    assert parsed["elapsed_s"] == 1.5
