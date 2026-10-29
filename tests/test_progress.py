from progress import BUILD, PLAN, READ, REVIEW, ProgressTracker, classify


def test_classify_basic():
    assert classify("Read", None, False) == READ
    assert classify("TodoWrite", None, False) == PLAN
    assert classify("Edit", None, False) == BUILD
    assert classify("Agent", None, False) is None


def test_look_only_bash_is_reading():
    assert classify("Bash", "ls -la", edited=False) == READ
    assert classify("Bash", "cd bridge && cat config.py | head -20", edited=False) == READ
    assert classify("Bash", "git status; git diff", edited=True) == READ
    assert classify("PowerShell", "Get-ChildItem | Select-Object Name", edited=False) == READ


def test_bash_that_runs_something_is_building_even_before_edit():
    assert classify("Bash", "python tools/serial_test.py COM5", edited=False) == BUILD
    assert classify("Bash", "cd arduino && arduino-cli upload -p COM5 notifier", edited=False) == BUILD
    assert classify("Bash", "ls && python main.py", edited=False) == BUILD
    # 수정 전 테스트는 검토로 건너뛰지 않음
    assert classify("Bash", "python -m pytest", edited=False) == BUILD


def test_bash_after_edit_test_is_review_other_is_build():
    assert classify("Bash", "python -m pytest -q", edited=True) == REVIEW
    assert classify("Bash", "npm run build", edited=True) == REVIEW
    assert classify("Bash", "mkdir out", edited=True) == BUILD


def test_ranges_follow_spec():
    t = ProgressTracker(0, tau=45)
    assert t.percent(0) == 0
    assert 0 < t.percent(60) < 20            # 파악 0–20
    t.on_tool("TodoWrite", None, 60)
    assert 20 <= t.percent(61) <= 30          # 정리 20–30
    t.on_tool("Edit", None, 100)
    assert 50 <= t.percent(101) <= 60         # 만드는 중 50–60
    t.on_tool("Bash", "pytest", 150)
    assert 80 <= t.percent(151) <= 90         # 검토 80–90
    assert t.percent(10_000) <= 90


def test_never_goes_backwards():
    t = ProgressTracker(0)
    t.on_tool("Edit", None, 10)
    before = t.percent(30)
    assert t.on_tool("Read", None, 30) is False
    assert t.phase.key == "build"
    assert t.percent(30) >= before
