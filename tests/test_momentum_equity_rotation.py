"""momentum_equity.jsonl rotasyonu: 10MB tavanında arşive taşı, veri kaybı sıfır."""

from __future__ import annotations

import json

from hibrit_trader import panel


def test_rotation_archives_without_data_loss(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "_MOM_EQ_ROTATE_BYTES", 200)  # test için küçük tavan
    monkeypatch.setattr(panel, "_mom_eq_last_write", 0.0)
    p = tmp_path / "momentum_equity.jsonl"
    old_lines = [json.dumps({"ts": 1000.0 + i, "eq": 900.0 + i}) for i in range(20)]
    p.write_text("\n".join(old_lines) + "\n")
    assert p.stat().st_size > 200

    panel._mom_equity_append(tmp_path, 999.99)

    archives = list(tmp_path.glob("momentum_equity_arsiv_*.jsonl"))
    assert len(archives) == 1
    # Eski veri arşivde birebir duruyor, aktif dosya taze devam ediyor
    assert archives[0].read_text().splitlines() == old_lines
    active = p.read_text().splitlines()
    assert len(active) == 1
    assert json.loads(active[0])["eq"] == 999.99


def test_same_day_second_rotation_does_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "_MOM_EQ_ROTATE_BYTES", 50)
    monkeypatch.setattr(panel, "_mom_eq_last_write", 0.0)
    p = tmp_path / "momentum_equity.jsonl"
    p.write_text("x" * 100 + "\n")
    panel._mom_equity_append(tmp_path, 1.0)
    monkeypatch.setattr(panel, "_mom_eq_last_write", 0.0)
    p.write_text("y" * 100 + "\n")  # aktif dosya yine tavanı aştı (aynı gün)
    panel._mom_equity_append(tmp_path, 2.0)
    archives = sorted(tmp_path.glob("momentum_equity_arsiv_*"))
    assert len(archives) == 2  # ikincisi sayaçlı isim aldı, üzerine yazılmadı
    contents = "".join(a.read_text() for a in archives)
    assert "x" in contents and "y" in contents


def test_below_threshold_no_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "_mom_eq_last_write", 0.0)
    p = tmp_path / "momentum_equity.jsonl"
    p.write_text(json.dumps({"ts": 1.0, "eq": 1.0}) + "\n")
    panel._mom_equity_append(tmp_path, 2.0)
    assert list(tmp_path.glob("momentum_equity_arsiv_*")) == []
    assert len(p.read_text().splitlines()) == 2
