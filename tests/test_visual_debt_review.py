import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('visual_review', Path(__file__).parents[1] / 'scripts/register_visual_debt_candidate.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def review(image):
    return dict(scope='consolidated', unit='CNY', field_name='current_portion_long_term_debt',
                status='candidate_pending_automated_verification', same_pdf_is_not_independent_source=True,
                page_number=172, value='10', note_total_cny='10', note_components_cny=['6', '4'],
                image_sha256=hashlib.sha256(image.read_bytes()).hexdigest())


@pytest.mark.parametrize('key,value', [('scope', 'parent'), ('page_number', True),
    ('value', '11'), ('note_components_cny', ['NaN']), ('same_pdf_is_not_independent_source', False),
    ('status', 'automatically_verified')])
def test_unsafe_review_rejected(tmp_path, key, value):
    image = tmp_path / 'page.png'
    image.write_bytes(b'reviewed image')
    record = review(image)
    record[key] = value
    with pytest.raises(ValueError):
        module.validate(record, image)


def test_changed_image_rejected(tmp_path):
    image = tmp_path / 'page.png'
    image.write_bytes(b'reviewed image')
    record = review(image)
    module.validate(record, image)
    image.write_bytes(b'changed')
    with pytest.raises(ValueError, match='image changed'):
        module.validate(record, image)
