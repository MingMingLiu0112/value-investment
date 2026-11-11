"""Private source-bound account observations, separate from the trading ledger."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from ...private_portfolio_intake import require_private_data_path


def load_account_observations(*, private_root: Path, repository_root: Path) -> dict:
    root = Path(private_root).resolve()
    accounts = root / 'accounts'
    result = dict(action='no_order', scope='PRIVATE_ACCOUNT_OBSERVATIONS_NOT_TRADING_LEDGER',
        accounts=[], unavailable_count=0, trade_eligible=False)
    if not accounts.exists():
        return result
    require_private_data_path(accounts, private_root=root, repository_root=repository_root)
    pointers = sorted(accounts.glob('*/current-observation.json'))
    if len(pointers) > 50:
        raise ValueError('Account observation limit exceeded')
    for pointer in pointers:
        try:
            account = pointer.parent.resolve()
            def bound_path(name):
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Observation path must be account-relative')
                path = require_private_data_path(account / relative, private_root=root,
                    repository_root=repository_root, must_exist=True)
                if not path.is_relative_to(account):
                    raise ValueError('Cross-account observation path')
                return path
            require_private_data_path(pointer, private_root=root, repository_root=repository_root, must_exist=True)
            if pointer.stat().st_size > 16384:
                raise ValueError('Oversized pointer')
            pin = json.loads(pointer.read_bytes())
            if pin.get('schema_version') != 'private-account-current-observation-v1' or pin.get('action') != 'no_order':
                raise ValueError('Invalid observation pointer')
            path = bound_path(pin['snapshot_path'])
            if path.stat().st_size > 2_000_000:
                raise ValueError('Oversized observation')
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != pin['snapshot_sha256']:
                raise ValueError('Observation fingerprint changed')
            value = json.loads(raw)
            if (value.get('schema_version') != 'private-account-screenshot-observation-v1'
                    or value.get('namespace') != 'ACTUAL_USER_PROVIDED' or value.get('action') != 'no_order'
                    or value.get('trade_eligible') is not False or value.get('formal_eligibility') is not False
                    or value.get('active_portfolio_journal_written') is not False):
                raise ValueError('Observation cannot grant trading authority')
            date.fromisoformat(value['snapshot_date'])
            image = bound_path(str(path.parent.relative_to(account) / value['evidence']['image']))
            if image.stat().st_size > 20_000_000 or sha256(image.read_bytes()).hexdigest() != value['evidence']['sha256']:
                raise ValueError('Screenshot changed')
            rows = value['holdings']
            if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
                raise ValueError('Invalid holdings')
            seen = set()
            for row in rows:
                symbol = row['symbol']
                if (not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isascii()
                        or not symbol.isdigit() or symbol in seen or row.get('sleeve') != 'UNASSIGNED'
                        or row.get('sellable_quantity') is not None):
                    raise ValueError('Invalid observation security or invented classification')
                seen.add(symbol)
                numbers = [Decimal(row[key]) for key in ('quantity_inferred', 'displayed_price_cny', 'market_value_cny')]
                if any(not number.is_finite() or number <= 0 for number in numbers):
                    raise ValueError('Invalid observed number')
                quantity, price, market_value = numbers
                if quantity != quantity.to_integral_value() or quantity * price != market_value:
                    raise ValueError('Inferred quantity does not reconcile')
            result['accounts'].append(dict(account_label=value['account_label'],
                snapshot_date=value['snapshot_date'], displayed_clock_time=value['displayed_clock_time'],
                observed_totals=value['observed_totals'], holdings=rows,
                reconciliation=value['reconciliation'], snapshot_sha256=pin['snapshot_sha256'],
                source='USER_PROVIDED_SCREENSHOT_NOT_LIVE_QUOTES',
                action='no_order', trade_eligible=False, active_trading_ledger=False))
        except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
            result['unavailable_count'] += 1
    return result
