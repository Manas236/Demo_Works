"""
Tests for GST_STATE_CODES duplication guard.
"""

import pipeline
import invoice

def test_gst_state_codes_match():
    """
    The GST_STATE_CODES table is duplicated in pipeline.py and invoice.py
    because ra.py may not import invoice.py. This test asserts they are identical
    to prevent silent statutory errors from drift.
    """
    assert pipeline.GST_STATE_CODES == invoice.GST_STATE_CODES
