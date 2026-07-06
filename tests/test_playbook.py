from journal import playbook


def test_empty_playbook_is_empty_string(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYBOOK_PATH", str(tmp_path / "pb.md"))
    assert playbook.lessons_text() == ""


def test_add_and_read_newest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYBOOK_PATH", str(tmp_path / "pb.md"))
    playbook.add_lesson("[2026-06-01 AAA hit_target +21%] first lesson")
    playbook.add_lesson("[2026-07-01 BBB thesis_broken -12%] second lesson")
    text = playbook.lessons_text()
    assert "2 lessons" in text
    assert text.index("second lesson") < text.index("first lesson")


def test_compaction_keeps_newest(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYBOOK_PATH", str(tmp_path / "pb.md"))
    for i in range(50):
        playbook.add_lesson(f"lesson {i}")
    text = playbook.lessons_text()
    assert "40 lessons" in text        # config playbook.max_lessons
    assert "lesson 49" in text
    assert "lesson 0\n" not in text and not text.endswith("lesson 0")
