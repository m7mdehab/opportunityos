"""Make the Founder activity state view self-contained for hosted PostgREST."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Sequence, Union
from alembic import op
revision: str = "0019_activity_view_access"
down_revision: Union[str, None] = "0018_activity_live_fix"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
def upgrade() -> None:
    path = Path(__file__).with_name("0017_founder_activity_correction.py")
    spec = spec_from_file_location("_fr007_0017_access", path)
    if spec is None or spec.loader is None: raise RuntimeError("cannot load activity correction")
    module = module_from_spec(spec); spec.loader.exec_module(module); module._apply_correction()
def downgrade() -> None: pass
