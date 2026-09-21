"""Offline regression tests for missing artifacts and fresh thumbnail builds."""
import contextlib
import io
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
from boydclips import pipeline, publish, render
from boydclips.artifacts import require_thumbnail
from boydclips.config import Config, load_config
from boydclips.discover import Docket
from boydclips.transcribe import Transcript
import check_thumb_grade


@pytest.mark.parametrize('content', [None, b'', b'not an image'])
def test_invalid_thumbnail_rejected(tmp_path, content):
    target = tmp_path / 'thumbnail.jpg'
    if content is not None:
        target.write_bytes(content)
    with pytest.raises(RuntimeError):
        require_thumbnail(target)


def test_valid_thumbnail_accepted(tmp_path):
    target = tmp_path / 'thumbnail.jpg'
    Image.new('RGB', (1280, 720), 'blue').save(target)
    assert require_thumbnail(target) == target


@pytest.mark.parametrize('failure', ['exception', 'missing', 'corrupt'])
def test_failed_rebuild_preserves_previous_but_does_not_pass(tmp_path, monkeypatch, failure):
    target = tmp_path / 'thumbnail_quote.jpg'
    Image.new('RGB', (32, 18), 'red').save(target)
    before = target.read_bytes()
    def build(source, at, white, yellow, out, cfg):
        if failure == 'exception':
            raise RuntimeError('builder failed')
        if failure == 'corrupt':
            out.write_bytes(b'bad JPEG')
    monkeypatch.setattr(pipeline.thumbnail, 'build', build)
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = Config({})
    with pytest.raises(RuntimeError):
        pipe._produce_thumbnail(tmp_path/'source.mp4', 0, {'hook_start_s': 2},
                                {'thumbnail_quote': 'REAL WORDS', 'thumbnail_quote_yellow': 'WORDS'}, tmp_path)
    assert target.read_bytes() == before


def test_successful_rebuild_replaces_old_image(tmp_path, monkeypatch):
    target = tmp_path / 'thumbnail_quote.jpg'
    target.write_bytes(b'old invalid output')
    def build(source, at, white, yellow, out, cfg):
        assert not out.exists()
        Image.new('RGB', (1280, 720), 'blue').save(out)
    monkeypatch.setattr(pipeline.thumbnail, 'build', build)
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = Config({})
    result = pipe._produce_thumbnail(tmp_path/'source.mp4', 0, {'hook_start_s': 2},
                                   {'thumbnail_quote': 'REAL WORDS', 'thumbnail_quote_yellow': 'WORDS'}, tmp_path)
    assert result['status'] == 'candidate'
    assert require_thumbnail(target) == target


def _production(tmp_path, monkeypatch):
    (tmp_path / 'source.mp4').write_bytes(b'source fixture; rendering is mocked')
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = load_config()
    pipe.cfg._data['analysis']['producer_brain']['enabled'] = False
    pipe.cfg._data['output']['longform'].update(intro_enabled=False, trim_dead_air=False)
    pipe.cfg._data['output']['short']['autocrop'] = False
    pipe.work = tmp_path / 'work'
    pipe.out = tmp_path / 'out'
    pipe.store = Mock()
    pipe.store.conn = sqlite3.connect(':memory:')   # the story ledger reads this
    pipe.store.case_key.return_value = 'test:10'
    pipe.store.case_windows.return_value = [(10, 610)]
    pipe.store.next_case_start.return_value = None
    pipe.store.save_clip.return_value = 1
    pipe._analyzer = Mock()
    pipe._analyzer.package.return_value = {
        'hook_verified': True, 'summary': 'summary', 'longform_title': 'title',
        'thumbnail_quote': 'REAL WORDS', 'thumbnail_quote_yellow': 'WORDS'}
    monkeypatch.setattr(pipeline, 'get_transcript', lambda *a, **kw: Transcript('test'))
    monkeypatch.setattr(render, 'download_section', lambda *a, **kw: (tmp_path/'source.mp4', 0))
    monkeypatch.setattr(render, 'render_longform', lambda *a, **kw: 600)
    monkeypatch.setattr(render, 'plan_short_segments', lambda *a, **kw: None)
    pipe._write_manifest = Mock()
    docket = Docket('test', 'test docket', 3600, '2026-09-06', 'morning')
    case = {'start_s': 10, 'end_s': 610, 'hook_start_s': 20, 'proceeding_type':'plea', 'shortable':False}
    return pipe, docket, case


def test_longform_without_short_still_builds_thumbnail(tmp_path, monkeypatch):
    pipe, docket, case = _production(tmp_path, monkeypatch)
    pipe._produce_thumbnail = Mock(return_value={'status':'candidate'})
    result = pipe.produce(docket, case)
    pipe._produce_thumbnail.assert_called_once()
    pipe._write_manifest.assert_called_once()
    assert result['short'] is None
    assert result['thumbnail']['status'] == 'candidate'


def test_thumbnail_failure_prevents_success_manifest(tmp_path, monkeypatch):
    pipe, docket, case = _production(tmp_path, monkeypatch)
    pipe._produce_thumbnail = Mock(side_effect=RuntimeError('missing thumbnail'))
    with pytest.raises(RuntimeError, match='missing thumbnail'):
        pipe.produce(docket, case)
    pipe._write_manifest.assert_not_called()


def test_missing_enabled_intro_fails(tmp_path, monkeypatch):
    pipe, docket, case = _production(tmp_path, monkeypatch)
    pipe.cfg._data['output']['longform']['intro_enabled'] = True
    monkeypatch.setattr(render, 'resolve_intro', lambda *a: None)
    with pytest.raises(RuntimeError, match='intro is enabled'):
        pipe.produce(docket, case)
    pipe._write_manifest.assert_not_called()


def test_watermark_missing_fails_but_explicit_disable_works(tmp_path):
    with pytest.raises(FileNotFoundError):
        render._watermark_chain({'watermark':str(tmp_path/'missing.png')}, 1280,720,'in','out',0.06)
    assert render._watermark_chain({'watermark':False},1280,720,'in','out',0.06) == ([], '[in]null[out]')


@pytest.mark.parametrize('valid', [False, True])
def test_incomplete_pair_preflight_stops_before_network(tmp_path, monkeypatch, valid):
    cfg = load_config()
    cfg._data['autonomy']['mode'] = 'assisted'
    cfg._data['publish']['youtube']['api_audited'] = True
    video = tmp_path/'longform.mp4'
    video.write_bytes(b'fixture: file existence only, not video decode')
    if valid:
        Image.new('RGB', (1280,720)).save(tmp_path/'thumbnail_quote.jpg')
    factory = Mock(return_value={})
    monkeypatch.setattr(publish, 'build_publishers', factory)
    store = Mock()
    store.publication_url.return_value = None
    kwargs = dict(longform={'clip_id':1,'file_path':str(video),'title':'title','description':'desc'},short=None,context={})
    with pytest.raises(RuntimeError):
        publish.publish_pair(cfg,store,**kwargs)
    factory.assert_not_called()


@pytest.mark.parametrize('present', [False, True])
def test_grade_selftest_requires_positive_control(tmp_path, monkeypatch, present):
    accepted = tmp_path/'accepted.jpg'
    if present:
        accepted.write_bytes(b'fixture for control presence; measurement mocked')
    floor = tmp_path/'floor.json'
    floor.write_text(json.dumps({'files':{'ACCEPTED':str(accepted)}}))
    bad = tmp_path/'bad'
    bad.mkdir()
    for name in ['A','B','C']:
        (bad/(name+'_thumb.jpg')).write_bytes(b'bad')
    monkeypatch.setattr(check_thumb_grade,'FLOOR',str(floor))
    monkeypatch.setattr(check_thumb_grade,'FIX',str(bad))
    monkeypatch.setattr(check_thumb_grade,'check',lambda case,*a,**kw: [] if case=='ACCEPTED' else ['bad'])
    with contextlib.redirect_stdout(io.StringIO()):
        assert check_thumb_grade.selftest() == (0 if present else 1)
