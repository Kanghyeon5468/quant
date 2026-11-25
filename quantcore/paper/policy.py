"""User-authorized cash-only paper limits; the journal stores the active budget."""
from decimal import Decimal

INITIAL_BUDGET = Decimal('5000')
MAX_BUDGET = Decimal('100000')
MAX_SYMBOL_BUY = Decimal('20000')
