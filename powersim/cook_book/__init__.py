from .sizing import Sizing
from .reports import Reports
# from .sizing_export import sizing_export_pv_bess
# from .trese_like import trese_like_study

class CookBook(
    Sizing,
    Reports,
):
    """
    Container for common recipes / system configurations / studies.
    A recipe can be added to the CookBook using the decorator @recipie
    """
    pass