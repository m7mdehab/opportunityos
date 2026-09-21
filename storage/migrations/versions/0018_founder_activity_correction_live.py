"""Apply the W25.1 correction body after the live 0017 table-only rollout."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Sequence, Union
from alembic import op

revision: str = "0018_founder_activity_correction_live"
down_revision: Union[str, None] = "0017_founder_activity_correction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    path = Path(__file__).with_name("0017_founder_activity_correction.py")
    spec = spec_from_file_location("_fr007_0017", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load 0017 correction implementation")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module._apply_correction()

def downgrade() -> None:
    # The live correction is intentionally retained when rolling back the
    # bookkeeping revision; a clean rollback must use 0017's downgrade.
    pass
