"""Classify structured Codex capacity errors."""
import re

def is_capacity_error(error):
    if not isinstance(error, dict): return False
    # Match structured error fields only. Usage limits/auth/cancellation are excluded.
    code = error.get('codexErrorInfo')
    if code == 'serverOverloaded': return True
    if code is not None and code != 'other': return False
    if error.get('code') in {'authentication_error', 'unauthorized', 'usage_limit_exceeded', 'rate_limit_exceeded', 'safety_refusal', 'cancelled'}: return False
    text = str(error.get('message', '')) + ' ' + str(error.get('code', ''))
    return bool(re.search(r'selected model is at capacity|server_overloaded|server_is_overloaded|model.{0,30}(?:at capacity|temporarily overloaded)', text, re.I))
